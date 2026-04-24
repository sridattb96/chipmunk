"""Business logic: transcription, summarization, Drive, action suggestions."""

import logging

logger = logging.getLogger(__name__)

# -----------------------------------------------------------------------------
# TRANSCRIPTION MODE: "batch" | "stream"
# - batch: Google Speech-to-Text (upload full audio, then transcribe)
# - stream: Deepgram WebSocket (stream audio, transcript on the fly, supports 30+ min)
# -----------------------------------------------------------------------------
TRANSCRIPTION_MODE = "stream"

import base64
from pathlib import Path
import io
import json
import tempfile
import time
import uuid

import requests
from google.auth.transport.requests import Request as AuthRequest
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload, MediaFileUpload
from openai import OpenAI

from app.auth import get_user_credentials
from app.config import (
    GOOGLE_APPLICATION_CREDENTIALS,
    GCS_BUCKET,
    OPENAI_API_KEY,
)


def _upload_to_gcs(audio_bytes: bytes) -> str:
    """Upload audio to GCS and return gs:// URI."""
    import os

    credentials = service_account.Credentials.from_service_account_file(
        GOOGLE_APPLICATION_CREDENTIALS,
        scopes=["https://www.googleapis.com/auth/devstorage.full_control"],
    )
    service = build("storage", "v1", credentials=credentials)
    blob_name = f"chipmunk/{uuid.uuid4()}.webm"
    path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".webm", delete=False) as f:
            f.write(audio_bytes)
            f.flush()
            path = f.name
        media = MediaFileUpload(path, mimetype="audio/webm", resumable=False)
        service.objects().insert(
            bucket=GCS_BUCKET,
            body={"name": blob_name},
            media_body=media,
        ).execute()
        return f"gs://{GCS_BUCKET}/{blob_name}"
    finally:
        if path and os.path.exists(path):
            try:
                os.unlink(path)
            except Exception:
                pass


def transcribe_audio(audio_bytes: bytes, content_type: str = "webm") -> str:
    """Transcribe audio using Google Speech-to-Text REST API. Returns transcript text."""
    from pathlib import Path

    creds_path = Path(GOOGLE_APPLICATION_CREDENTIALS)
    if not creds_path.exists():
        raise FileNotFoundError(
            f"Service account file not found: {creds_path}\n"
            "Download the JSON key from Google Cloud Console > IAM & Admin > Service Accounts, "
            "then save it as backend/credentials/service-account.json"
        )
    credentials = service_account.Credentials.from_service_account_file(
        str(creds_path),
        scopes=["https://www.googleapis.com/auth/cloud-platform"],
    )
    credentials.refresh(AuthRequest())

    # Use long running recognize for audio > 1 min
    # For audio > 1 min, Google requires GCS. For <= 1 min, inline works.
    url = "https://speech.googleapis.com/v1/speech:longrunningrecognize"
    headers = {"Authorization": f"Bearer {credentials.token}"}

    encoding_map = {
        "webm": "WEBM_OPUS",
        "ogg": "OGG_OPUS",
        "mp3": "MP3",
        "flac": "FLAC",
    }
    ct = content_type.lower().replace("audio/", "").split(";")[0].strip()
    encoding = encoding_map.get(ct, "WEBM_OPUS")

    config = {
        "encoding": encoding,
        "sampleRateHertz": 48000,
        "languageCode": "en-US",
        "enableAutomaticPunctuation": True,
    }

    # Sync API limits: 60 sec or 10 MB. Use long-running for anything that might exceed 60s.
    # Webm/opus ~24–64 kbps → 60s ≈ 180–480 KB. Use 400KB threshold to stay under 60s.
    use_sync = len(audio_bytes) <= 400_000
    if use_sync:
        sync_url = "https://speech.googleapis.com/v1/speech:recognize"
        payload = {"config": config, "audio": {"content": base64.b64encode(audio_bytes).decode()}}
        r = requests.post(sync_url, headers=headers, json=payload, timeout=120)
        r.raise_for_status()
        result = r.json()
    else:
        use_gcs = GCS_BUCKET and len(audio_bytes) > 500_000
        if use_gcs:
            audio_uri = _upload_to_gcs(audio_bytes)
            audio_spec = {"uri": audio_uri}
        else:
            audio_spec = {"content": base64.b64encode(audio_bytes).decode()}
        payload = {"config": config, "audio": audio_spec}
        r = requests.post(url, headers=headers, json=payload, timeout=30)
        r.raise_for_status()
        op = r.json()
        op_name = op.get("name")
        if not op_name:
            raise ValueError("No operation name in response")
        # Poll: use operation ID only for status URL
        if not op_name.startswith("projects/"):
            status_url = f"https://speech.googleapis.com/v1/operations/{op_name}"
        else:
            status_url = f"https://speech.googleapis.com/v1/{op_name}"
        for _ in range(600):
            sr = requests.get(status_url, headers=headers, timeout=30)
            sr.raise_for_status()
            status = sr.json()
            if status.get("done"):
                break
            time.sleep(1)
        if not status.get("done"):
            raise TimeoutError("Transcription timed out")
        result = status.get("response", {})
    transcript_parts = []
    for r in result.get("results", []):
        for alt in r.get("alternatives", []):
            transcript_parts.append(alt.get("transcript", ""))
    return " ".join(transcript_parts).strip()


_PROMPTS_DIR = Path(__file__).parent / "prompts"
_SYSTEM_PROMPT = (_PROMPTS_DIR / "system_prompt.txt").read_text()
_USER_PROMPT = (_PROMPTS_DIR / "user_prompt.txt").read_text()


def extract_structured_data(transcript: str) -> dict:
    """Extract summary and structured topics from transcript using system/user prompts.
    Returns {"summary": str, "topics": [{"label": str, "description": str}, ...]}
    """
    if not OPENAI_API_KEY or not OPENAI_API_KEY.strip():
        raise ValueError(
            "OPENAI_API_KEY is not set. Add it to backend/.env from https://platform.openai.com/api-keys"
        )

    transcript_preview = (transcript or "")[:500] + ("..." if len(transcript or "") > 500 else "")
    logger.info("[Summary] Input transcript length=%d, preview: %s", len(transcript or ""), transcript_preview)
    print(f"[Summary] Input transcript length={len(transcript or '')}, preview: {transcript_preview[:200]}...")

    client = OpenAI(api_key=OPENAI_API_KEY.strip())
    user_content = f"{_USER_PROMPT}\n\nTranscript:\n\n{transcript}"
    messages = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            max_tokens=1000,
            temperature=0,
        )
    except Exception as e:
        logger.exception("[Summary] OpenAI API call failed: %s", e)
        print(f"[Summary] OpenAI API call failed: {type(e).__name__}: {e}")
        raise

    if not response.choices:
        logger.error("[Summary] OpenAI returned no choices. full_response=%s", response)
        raise ValueError("OpenAI returned no choices; the model may be overloaded or the request invalid")

    raw_text = (response.choices[0].message.content or "").strip()
    logger.info("[Summary] Raw model output (len=%d): %s", len(raw_text), raw_text[:1500])
    print(f"[Summary] Raw model output (len={len(raw_text)}): {raw_text[:800]}")

    text = raw_text
    if "```" in text:
        parts = text.split("```")
        for p in parts:
            p = p.strip()
            if p.startswith("json"):
                p = p[4:].strip()
            if p.startswith("{"):
                text = p
                break

    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        logger.error("[Summary] JSON parse failed. error=%s, raw_text=%s", e, raw_text)
        print(f"[Summary] JSON parse failed: {e}. Raw output: {raw_text[:600]}")
        raise ValueError(f"Model returned invalid JSON: {e}. Raw output: {raw_text[:500]}") from e

    summary = (data.get("summary") or "").strip()
    raw_topics = data.get("topics") or []
    topics = []
    for t in raw_topics:
        if isinstance(t, dict):
            label = (t.get("label") or "").strip()
            if label:
                topics.append({
                    "label": label,
                    "description": (t.get("description") or "").strip(),
                })
        elif isinstance(t, str) and t.strip():
            topics.append({"label": t.strip(), "description": ""})

    raw_decisions = data.get("decisions")
    if not isinstance(raw_decisions, list):
        decisions = []
    else:
        decisions = [str(d).strip() for d in raw_decisions if isinstance(d, str) and str(d).strip()]

    # Retry with simpler prompt if model returned empty despite having content
    if (not summary or not topics) and transcript and len(transcript.strip()) > 50:
        logger.info("[Summary] Empty result for non-empty transcript, retrying with fallback prompt")
        try:
            fallback = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{
                    "role": "user",
                    "content": f"Summarize this conversation in 1-3 sentences. Extract 1-3 topic labels (2-5 words each). "
                    f"Reply as JSON: {{\"summary\": \"...\", \"topics\": [{{\"label\": \"...\", \"description\": \"...\"}}], \"decisions\": []}}\n\nTranscript:\n{transcript}",
                }],
                max_tokens=500,
                temperature=0,
            )
            if fallback.choices:
                ft = (fallback.choices[0].message.content or "").strip()
                if "```" in ft:
                    for p in ft.split("```"):
                        p = p.strip()
                        if p.startswith("json"):
                            p = p[4:].strip()
                        if p.startswith("{"):
                            ft = p
                            break
                fd = json.loads(ft)
                summary = (fd.get("summary") or "").strip() or summary
                if not topics and isinstance(fd.get("topics"), list):
                    for t in fd["topics"]:
                        if isinstance(t, dict):
                            label = (t.get("label") or t.get("description") or "").strip()
                            if label:
                                topics.append({"label": label, "description": (t.get("description") or "").strip()})
                        elif isinstance(t, str) and t.strip():
                            topics.append({"label": t.strip(), "description": ""})
        except Exception as e:
            logger.warning("[Summary] Fallback extraction failed: %s", e)

    result = {"summary": summary or "No summary.", "topics": topics, "decisions": decisions}
    logger.info("[Summary] Parsed result: summary_len=%d, topics_count=%d, decisions_count=%d", len(result["summary"]), len(result["topics"]), len(result["decisions"]))
    return result


def embed_recording(recording_id: str) -> None:
    """Embed a recording's summary+topics and store in ChromaDB. Designed for BackgroundTasks."""
    from app.db import get_recording_with_topics_for_embedding
    from app.chromadb_store import add_records
    try:
        rec = get_recording_with_topics_for_embedding(recording_id)
        if not rec:
            return
        summary_text = (rec["summary"] or "").strip()
        topic_lines = [f"- {t['label']}" for t in rec["topics"] if (t.get("label") or "").strip()]
        topics_block = "\n".join(topic_lines) if topic_lines else "- (none)"
        combined_text = f"Summary: {summary_text or '(none)'}\n\nTopics:\n{topics_block}"
        if not combined_text.strip():
            return
        vec = embed_text(combined_text)
        add_records(
            ids=[f"{recording_id}_combined"],
            vectors=[vec],
            metadatas=[{
                "entity_type": "combined",
                "call_id": recording_id,
                "topic_id": "",
                "canonical_topic_id": "",
                "org_id": f"user_{rec['user_id']}",
                "created_at": rec["created_at"],
            }],
        )
    except Exception as e:
        logger.error("[embed_recording] Failed to embed %s: %s", recording_id, e)


def embed_text(text: str) -> list[float]:
    """Generate embedding for text using OpenAI text-embedding-3-large."""
    if not text or not text.strip():
        raise ValueError("Text cannot be empty for embedding")
    client = OpenAI(api_key=OPENAI_API_KEY)
    resp = client.embeddings.create(
        model="text-embedding-3-large",
        input=text.strip(),
    )
    return resp.data[0].embedding


def summaries_to_group_title(summaries: list[str]) -> str:
    """Use LLM to generate a short title for a group of meeting summaries."""
    if not summaries or not OPENAI_API_KEY or not OPENAI_API_KEY.strip():
        return "Untitled topic"
    client = OpenAI(api_key=OPENAI_API_KEY.strip())
    combined = "\n\n".join(f"Meeting {i+1}:\n{s}" for i, s in enumerate(summaries))
    prompt = f"What is the overall topic of these {len(summaries)} meetings? Reply with a short phrase (2-6 words), no quotes or punctuation.\n\n{combined}"
    try:
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=50,
        )
        if resp.choices:
            title = (resp.choices[0].message.content or "").strip()
            return title or "Untitled topic"
    except Exception:
        pass
    return "Untitled topic"


def get_topic_chains(user_id: int) -> dict:
    """Return topic chains, using a SQLite cache keyed by completed-embedding version."""
    import json as _json
    from app.db import get_embedding_version, get_topic_chains_cache, set_topic_chains_cache

    current_version = get_embedding_version(user_id)
    cached = get_topic_chains_cache(user_id)
    if cached and cached[0] == current_version:
        return _json.loads(cached[1])

    result = _compute_topic_chains(user_id)
    set_topic_chains_cache(user_id, current_version, _json.dumps(result))
    return result


def _compute_topic_chains(user_id: int) -> dict:
    """
    Cluster recordings by semantic similarity (distance < 1), name groups via LLM.
    Returns { groups: [...], recordingsById: {...} }.
    """
    from app.db import get_connection, get_recordings_by_ids
    from app.chromadb_store import get_collection, query as chroma_query

    org_id = f"user_{user_id}"
    coll = get_collection()

    if coll.count() == 0:
        return {"groups": [], "recordingsById": {}}

    # Try combined first, fallback to summary
    # ChromaDB requires single top-level operator; use $and for multiple conditions
    for entity_type, id_suffix in [("combined", "_combined"), ("summary", "_summary")]:
        try:
            where_filter = {"$and": [{"entity_type": {"$eq": entity_type}}, {"org_id": {"$eq": org_id}}]}
            result = coll.get(
                where=where_filter,
                include=["embeddings", "metadatas"],
            )
            if result["ids"]:
                break
        except Exception:
            continue
    else:
        return {"groups": [], "recordingsById": {}}

    if not result["ids"]:
        return {"groups": [], "recordingsById": {}}

    id_to_embedding = dict(zip(result["ids"], result["embeddings"]))
    id_to_call = {
        sid: (result["metadatas"] or [{}])[i].get("call_id", sid.replace(id_suffix, ""))
        for i, sid in enumerate(result["ids"])
    }

    # Union-Find for connected components (distance < 1)
    parent = {}

    def find(x):
        if x not in parent:
            parent[x] = x
        if parent[x] != x:
            parent[x] = find(parent[x])
        return parent[x]

    def union(a, b):
        parent[find(a)] = find(b)

    call_ids = [id_to_call[sid] for sid in result["ids"]]
    for cid in call_ids:
        find(cid)

    for vec_id, embedding in id_to_embedding.items():
        call_id = id_to_call.get(vec_id)
        if not call_id:
            continue
        try:
            q = chroma_query(
                query_embeddings=[embedding],
                n_results=20,
                where=where_filter,
            )
            if not q["ids"] or not q["ids"][0]:
                continue
            for meta, dist in zip(q["metadatas"][0] or [], q["distances"][0] or []):
                other = (meta or {}).get("call_id")
                if other and other != call_id and dist < 1:
                    union(call_id, other)
        except Exception:
            continue

    components: dict[str, list[str]] = {}
    for cid in call_ids:
        root = find(cid)
        if root not in components:
            components[root] = []
        components[root].append(cid)

    # Only groups with 2+ recordings
    groups = []
    all_rec_ids = set()
    for rec_ids in components.values():
        if len(rec_ids) >= 2:
            all_rec_ids.update(rec_ids)

    recordings = get_recordings_by_ids(user_id, list(all_rec_ids))
    recordings_by_id = {r["id"]: r for r in recordings}

    for rec_ids in components.values():
        if len(rec_ids) < 2:
            continue
        recs = [recordings_by_id[rid] for rid in rec_ids if rid in recordings_by_id]
        if len(recs) < 2:
            continue
        recs.sort(key=lambda r: r["created_at"] or "", reverse=True)
        summaries = [r["summary"] or "" for r in recs]
        title = summaries_to_group_title(summaries)
        created = max(r["created_at"] or "" for r in recs)
        group_id = f"group_{abs(hash(tuple(sorted(rec_ids)))) % (10**8):08x}"
        groups.append({
            "id": group_id,
            "title": title,
            "recordingIds": [r["id"] for r in recs],
            "createdAt": created,
        })

    groups.sort(key=lambda g: g["createdAt"] or "", reverse=True)
    return {"groups": groups, "recordingsById": recordings_by_id}


def save_to_drive(
    user_id: int,
    folder_id: str,
    summary: str,
    transcript: str,
    filename: str = "call_notes.md",
) -> dict:
    """Save summary + transcript as a single file to the user's Drive folder."""
    creds = get_user_credentials(user_id)
    if not creds:
        raise ValueError("User credentials not found or expired")

    content = f"""# Call Summary\n{summary}\n\n---\n\n# Transcript\n{transcript}"""
    file_metadata = {"name": filename, "parents": [folder_id]}
    media = MediaIoBaseUpload(
        io.BytesIO(content.encode("utf-8")),
        mimetype="text/markdown",
        resumable=False,
    )

    service = build("drive", "v3", credentials=creds)
    file = service.files().create(
        body=file_metadata,
        media_body=media,
        fields="id, name, webViewLink",
    ).execute()

    return {"id": file["id"], "name": file["name"], "webViewLink": file.get("webViewLink", "")}
