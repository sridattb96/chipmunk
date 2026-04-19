import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, File, Form, HTTPException, UploadFile, Depends, Header, WebSocket, WebSocketDisconnect
from fastapi.responses import RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app.auth import (
    exchange_code_for_tokens,
    get_authorization_url,
    get_user_credentials,
    get_user_info,
    upsert_user,
)
from app.config import FRONTEND_URL, GOOGLE_CLIENT_ID, DEEPGRAM_API_KEY
from app.db import init_db, seed_dummy_recordings
from app.services import save_to_drive, extract_structured_data, transcribe_audio, TRANSCRIPTION_MODE, get_topic_chains
from app.session import create_session, get_session


@asynccontextmanager
async def lifespan(app: FastAPI):
    import logging
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    init_db()
    seed_dummy_recordings()
    print(f"DEEPGRAM_API_KEY: {'SET' if DEEPGRAM_API_KEY else 'EMPTY'}")
    yield


app = FastAPI(title="Chipmunk", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[FRONTEND_URL, "http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def require_auth(authorization: str | None = Header(None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Not authenticated")
    token = authorization.replace("Bearer ", "")
    user_id = get_session(token)
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid or expired session")
    return user_id


# --- Auth ---


@app.get("/auth/google")
def auth_google():
    """Redirect user to Google OAuth."""
    url = get_authorization_url()
    return RedirectResponse(url=url)


@app.get("/auth/google/callback")
async def auth_callback(code: str):
    """Handle OAuth callback, create session, redirect to frontend."""
    import logging
    import traceback

    logger = logging.getLogger("chipmunk.auth")

    if not code:
        logger.error("[auth/callback] Missing OAuth code in request")
        raise HTTPException(status_code=400, detail="Missing code")

    logger.info("[auth/callback] Received OAuth callback — starting token exchange")
    try:
        loop = asyncio.get_event_loop()

        # Step 1: Exchange authorization code for tokens (network call to Google).
        logger.info("[auth/callback] Step 1/4: Exchanging authorization code for tokens")
        try:
            credentials = await asyncio.wait_for(
                loop.run_in_executor(None, lambda: exchange_code_for_tokens(code, timeout=30)),
                timeout=35,
            )
        except asyncio.TimeoutError:
            logger.error("[auth/callback] Step 1/4 TIMED OUT: exchange_code_for_tokens exceeded 35 s")
            raise HTTPException(status_code=504, detail="Token exchange timed out")
        logger.info("[auth/callback] Step 1/4 complete: tokens received")

        # Step 2: Fetch user profile from Google userinfo endpoint.
        logger.info("[auth/callback] Step 2/4: Fetching user info from Google")
        try:
            user_info = await asyncio.wait_for(
                loop.run_in_executor(None, lambda: get_user_info(credentials, timeout=30)),
                timeout=35,
            )
        except asyncio.TimeoutError:
            logger.error("[auth/callback] Step 2/4 TIMED OUT: get_user_info exceeded 35 s")
            raise HTTPException(status_code=504, detail="User info fetch timed out")
        google_id = user_info["id"]
        email = user_info.get("email", "")
        name = user_info.get("name", "") or email
        logger.info("[auth/callback] Step 2/4 complete: user_info fetched (google_id=%s, email=%s)", google_id, email)

        # Step 3: Upsert user record in SQLite.
        logger.info("[auth/callback] Step 3/4: Upserting user in database")
        user_id = upsert_user(google_id, email, name, credentials)
        logger.info("[auth/callback] Step 3/4 complete: user_id=%s", user_id)

        # Step 4: Create a signed session token.
        logger.info("[auth/callback] Step 4/4: Creating session token")
        session_token = create_session(user_id)
        logger.info("[auth/callback] Step 4/4 complete: session created, redirecting to frontend")

        return RedirectResponse(url=f"{FRONTEND_URL}/?token={session_token}")

    except HTTPException:
        raise
    except Exception as exc:
        logger.error(
            "[auth/callback] Unhandled exception during OAuth callback:\n%s",
            traceback.format_exc(),
        )
        raise HTTPException(status_code=500, detail=f"Auth callback failed: {exc}") from exc


@app.get("/auth/me")
def auth_me(user_id: int = Depends(require_auth)):
    """Return current user info."""
    from app.db import get_user_by_id

    user = get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return {"id": user["user_id"], "email": user["email"], "name": user.get("name")}


@app.post("/auth/logout")
def auth_logout():
    """Client discards token; no server-side invalidation for now."""
    return {"ok": True}


@app.get("/api/db/snapshot")
def db_snapshot(user_id: int = Depends(require_auth)):
    """Return snapshot of SQLite and ChromaDB for the /db admin view."""
    from app.db import get_connection
    from app.chromadb_store import get_collection

    sql = {}
    try:
        with get_connection() as conn:
            users_count = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
            recordings_count = conn.execute("SELECT COUNT(*) FROM recordings").fetchone()[0]
            topics_count = conn.execute("SELECT COUNT(*) FROM topics").fetchone()[0]
            sql["users"] = {"count": users_count}
            sql["recordings"] = {
                "count": recordings_count,
                "sample": [
                    dict(row)
                    for row in conn.execute(
                        "SELECT id, name, duration, created_at, substr(summary, 1, 80) || CASE WHEN length(summary) > 80 THEN '...' ELSE '' END as summary_preview FROM recordings ORDER BY created_at DESC LIMIT 5"
                    ).fetchall()
                ],
            }
            sql["topics"] = {
                "count": topics_count,
                "sample": [
                    dict(row)
                    for row in conn.execute(
                        "SELECT id, call_id, label, substr(COALESCE(description, ''), 1, 60) || CASE WHEN length(COALESCE(description, '')) > 60 THEN '...' ELSE '' END as desc_preview FROM topics ORDER BY created_at DESC LIMIT 5"
                    ).fetchall()
                ],
            }
            rows = conn.execute(
                "SELECT status, COUNT(*) as cnt FROM embedding_jobs GROUP BY status"
            ).fetchall()
            total_jobs = sum(r[1] for r in rows)
            by_status = {r[0]: r[1] for r in rows}
            recent = [dict(row) for row in conn.execute(
                "SELECT id, call_id, status, created_at, error FROM embedding_jobs ORDER BY created_at DESC LIMIT 10"
            ).fetchall()]
            sql["embedding_jobs"] = {
                "total": total_jobs,
                "by_status": by_status,
                "recent": recent,
            }
    except Exception as e:
        sql["error"] = str(e)

    chroma = {}
    try:
        coll = get_collection()
        chroma["count"] = coll.count()
        if chroma["count"] > 0:
            result = coll.get(limit=10, include=["metadatas"])
            chroma["sample"] = [
                {"id": id_, "metadata": m}
                for id_, m in zip(result["ids"], result["metadatas"] or [])
            ]
        else:
            chroma["sample"] = []
    except Exception as e:
        chroma["error"] = str(e)

    similar_calls = []
    similar_calls_skipped = False
    try:
        import time
        from app.chromadb_store import get_collection as get_chroma_coll, query as chroma_query

        with get_connection() as conn:
            done_calls = [
                r["call_id"]
                for r in conn.execute(
                    "SELECT call_id FROM embedding_jobs WHERE status = 'done' ORDER BY created_at DESC LIMIT 8"
                ).fetchall()
            ]

        if done_calls:
            def _compute_similar(entity_type: str, id_suffix: str):
                coll = get_chroma_coll()
                get_result = coll.get(where={"entity_type": entity_type}, include=["embeddings", "metadatas"])
                if not get_result["ids"]:
                    return []
                id_to_embedding = dict(zip(get_result["ids"], get_result["embeddings"]))
                id_to_call = {
                    sid: (get_result["metadatas"] or [{}])[i].get("call_id", sid.replace(id_suffix, ""))
                    for i, sid in enumerate(get_result["ids"])
                }
                done_set = set(done_calls)
                raw_similar = []
                for vec_id, embedding in id_to_embedding.items():
                    anchor_call = id_to_call.get(vec_id)
                    if not anchor_call or anchor_call not in done_set:
                        continue
                    q = chroma_query(
                        query_embeddings=[embedding],
                        n_results=6,
                        where={"entity_type": entity_type},
                    )
                    if not q["ids"] or not q["ids"][0]:
                        continue
                    seen = {anchor_call}
                    similar = []
                    for meta, dist in zip(q["metadatas"][0] or [], q["distances"][0] or []):
                        cid = (meta or {}).get("call_id")
                        if cid and cid not in seen:
                            seen.add(cid)
                            similar.append({"call_id": cid, "distance": round(dist, 4)})
                            if len(similar) >= 5:
                                break
                    if similar:
                        raw_similar.append({"anchor_call": anchor_call, "similar": similar})
                all_cids = set(done_calls)
                for item in raw_similar:
                    all_cids.add(item["anchor_call"])
                    for s in item["similar"]:
                        all_cids.add(s["call_id"])
                name_map = {}
                if all_cids:
                    with get_connection() as conn:
                        placeholders = ",".join("?" * len(all_cids))
                        for row in conn.execute(
                            f"SELECT id, name FROM recordings WHERE id IN ({placeholders})",
                            list(all_cids),
                        ).fetchall():
                            name_map[row["id"]] = row["name"]
                return [
                    {
                        "anchor": {"call_id": item["anchor_call"], "name": name_map.get(item["anchor_call"], item["anchor_call"])},
                        "similar": [{"call_id": s["call_id"], "name": name_map.get(s["call_id"], s["call_id"]), "distance": s["distance"]} for s in item["similar"]],
                    }
                    for item in raw_similar
                ]

            def _try_compute():
                for entity_type, id_suffix in [("combined", "_combined"), ("summary", "_summary")]:
                    try:
                        result = _compute_similar(entity_type, id_suffix)
                        if result:
                            return result
                    except Exception as e:
                        err_str = str(e)
                        if "Error finding id" in err_str or "Error executing plan" in err_str:
                            continue
                        raise
                return []

            for delay in [0, 2, 5, 10]:
                if delay > 0:
                    time.sleep(delay)
                try:
                    similar_calls = _try_compute()
                    break
                except Exception as e:
                    if delay == 10:
                        print(f"[DB snapshot] Similar calls failed after retries: {e}")
            else:
                similar_calls_skipped = True
                similar_calls = []
    except Exception as e:
        similar_calls = [{"error": str(e)}]

    return {"sql": sql, "chroma": chroma, "similar_calls": similar_calls, "similar_calls_skipped": similar_calls_skipped}


@app.get("/api/topic-chains")
def topic_chains(user_id: int = Depends(require_auth)):
    """Return topic groups (semantically similar recordings) with chain view data."""
    try:
        return get_topic_chains(user_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/config")
def get_config():
    """Public config for frontend (e.g. Google Client ID for Picker, transcription mode)."""
    return {
        "googleClientId": GOOGLE_CLIENT_ID,
        "transcriptionMode": TRANSCRIPTION_MODE,
    }


# --- Drive token for Picker ---


@app.get("/api/drive/token")
def drive_token(user_id: int = Depends(require_auth)):
    """Return access token for Google Picker (client-side folder selection)."""
    creds = get_user_credentials(user_id)
    if not creds:
        raise HTTPException(status_code=401, detail="Credentials expired")
    return {"access_token": creds.token}


# --- Recordings (All page) ---


@app.get("/api/recordings/all")
def list_all_recordings(user_id: int = Depends(require_auth)):
    """List recordings for the current user, newest first."""
    from app.db import list_recordings

    return list_recordings(user_id)


@app.get("/api/recordings/search")
def search_recordings_endpoint(
    q: str = "",
    user_id: int = Depends(require_auth),
):
    """Search recordings by name, topics, summary, etc. (full-text search)."""
    from app.db import search_recordings

    try:
        return search_recordings(user_id, q or "")
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/recordings/{recording_id}")
def get_recording_detail(
    recording_id: str,
    user_id: int = Depends(require_auth),
):
    """Get full recording details by id."""
    from app.db import get_recording

    rec = get_recording(recording_id, user_id)
    if not rec:
        raise HTTPException(status_code=404, detail="Recording not found")
    return rec


# --- Recordings (streaming transcription - Deepgram) ---


@app.websocket("/api/recordings/stream-transcribe")
async def stream_transcribe_websocket(websocket: WebSocket):
    """
    WebSocket proxy to Deepgram. Client sends binary audio chunks; server forwards
    transcript events. Requires ?token=... for auth. Used when transcriptionMode=stream.
    """
    await websocket.accept()
    token = websocket.query_params.get("token")
    if not token:
        await websocket.close(code=4001, reason="Missing token")
        return
    user_id = get_session(token)
    if not user_id:
        await websocket.close(code=4001, reason="Invalid or expired token")
        return

    from app.deepgram_stream import run_deepgram_proxy

    queue = asyncio.Queue()

    def transcripts_callback(transcript: str, is_final: bool):
        try:
            queue.put_nowait({"transcript": transcript, "is_final": is_final})
        except asyncio.QueueFull:
            pass

    async def client_receive():
        try:
            msg = await websocket.receive()
            if msg.get("type") == "websocket.disconnect":
                return None, "disconnect"
            if "bytes" in msg and msg["bytes"]:
                return msg["bytes"], "bytes"
            if "text" in msg and msg["text"]:
                return msg["text"], "text"
            return None, "disconnect"
        except Exception:
            return None, "disconnect"

    async def send_transcripts_to_client():
        while True:
            try:
                msg = await asyncio.wait_for(queue.get(), timeout=0.5)
                await websocket.send_json(msg)
                if msg.get("type") in ("done", "error"):
                    break
            except asyncio.TimeoutError:
                continue
            except WebSocketDisconnect:
                break
            except Exception:
                break

    send_task = asyncio.create_task(send_transcripts_to_client())
    try:
        import logging
        logging.getLogger("uvicorn.error").info("[Stream] Waiting for Deepgram proxy...")
        transcript = await run_deepgram_proxy(client_receive, transcripts_callback)
        logging.getLogger("uvicorn.error").info("[Stream] Proxy returned, putting done in queue")
        await queue.put({"type": "done", "transcript": transcript})
    except Exception as e:
        await queue.put({"type": "error", "error": str(e)})
    except WebSocketDisconnect:
        pass
    finally:
        # Wait for send_task to finish sending "done" (don't cancel—it needs to deliver the message)
        try:
            await asyncio.wait_for(send_task, timeout=5.0)
        except (asyncio.TimeoutError, asyncio.CancelledError):
            send_task.cancel()
            try:
                await send_task
            except asyncio.CancelledError:
                pass


# --- Recordings (upload / drive) ---


class SaveToDriveRequest(BaseModel):
    folder_id: str
    recording_id: str  # e.g. rec_abc123
    filename: str = "call_notes.md"


class SaveTranscriptRequest(BaseModel):
    """For stream mode: save recording using transcript from WebSocket (no audio file)."""
    name: str = "Recording"
    duration: str = "0:00"
    transcript: str


@app.post("/api/recordings/save-transcript")
async def save_transcript(
    body: SaveTranscriptRequest,
    user_id: int = Depends(require_auth),
):
    """Save a recording from stream mode (transcript only, no audio upload)."""
    from app.db import add_recording, create_embedding_job

    try:
        transcript = (body.transcript or "").strip()
        if not transcript:
            print("[Summary] save-transcript: Empty transcript, skipping extraction")
            structured = {"summary": "No speech detected.", "topics": [], "decisions": []}
        else:
            try:
                structured = extract_structured_data(transcript)
            except Exception as e:
                raise HTTPException(status_code=502, detail=f"Summary extraction failed: {e}")
        summary = structured["summary"]
        topics_data = structured["topics"]
        topic_labels = [t["label"] for t in topics_data]
        decisions = structured.get("decisions") or []
        recording_id = add_recording(
            user_id=user_id,
            name=body.name.strip() or "Recording",
            duration=body.duration or "0:00",
            summary=summary,
            topics=topic_labels,
            tone="",
            transcript=transcript,
            structured_topics=topics_data,
            decisions=decisions,
        )
        create_embedding_job(recording_id)
        return {
            "id": recording_id,
            "transcript": transcript,
            "summary": summary,
            "topics": topic_labels,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/recordings/upload")
async def upload_recording(
    file: UploadFile = File(...),
    name: str = Form("Recording"),
    duration: str = Form("0:00"),
    user_id: int = Depends(require_auth),
):
    """Upload audio, transcribe, summarize, store in DB. Returns recording with transcript and summary."""
    from app.db import add_recording

    audio_bytes = await file.read()
    if len(audio_bytes) == 0:
        raise HTTPException(status_code=400, detail="Empty file")

    content_type = file.content_type or "audio/webm"
    try:
        transcript = transcribe_audio(audio_bytes, content_type)
    except FileNotFoundError as e:
        raise HTTPException(status_code=503, detail=str(e))

    try:
        structured = extract_structured_data(transcript)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Summary extraction failed: {e}")
    summary = structured["summary"]
    topics_data = structured["topics"]
    topic_labels = [t["label"] for t in topics_data]
    decisions = structured.get("decisions") or []

    recording_id = add_recording(
        user_id=user_id,
        name=name.strip() or "Recording",
        duration=duration or "0:00",
        summary=summary,
        topics=topic_labels,
        tone="",
        transcript=transcript,
        structured_topics=topics_data,
        decisions=decisions,
    )

    from app.db import create_embedding_job
    create_embedding_job(recording_id)

    return {
        "id": recording_id,
        "transcript": transcript,
        "summary": summary,
        "topics": topic_labels,
    }


@app.post("/api/drive/save")
def drive_save(
    body: SaveToDriveRequest,
    user_id: int = Depends(require_auth),
):
    """Save a recording's summary + transcript to Google Drive in the selected folder."""
    from app.db import get_recording

    rec = get_recording(body.recording_id, user_id)
    if not rec:
        raise HTTPException(status_code=404, detail="Recording not found")

    result = save_to_drive(
        user_id=user_id,
        folder_id=body.folder_id,
        summary=rec["summary"],
        transcript=rec["transcript"],
        filename=body.filename,
    )
    return result
