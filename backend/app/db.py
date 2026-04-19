"""SQLite-backed storage for users and recordings."""

import hashlib
import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime

from app.config import DB_PATH


@contextmanager
def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def init_db():
    """Initialize SQLite schema: users, recordings, recordings_fts."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with get_connection() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY AUTOINCREMENT,
                google_id TEXT UNIQUE NOT NULL,
                email TEXT NOT NULL,
                name TEXT,
                access_token TEXT,
                refresh_token TEXT,
                token_expiry REAL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS recordings (
                rowid INTEGER PRIMARY KEY AUTOINCREMENT,
                id TEXT UNIQUE NOT NULL,
                user_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                duration TEXT NOT NULL,
                created_at TEXT NOT NULL,
                summary TEXT NOT NULL,
                topics TEXT NOT NULL,
                tone TEXT NOT NULL,
                transcript TEXT NOT NULL
            );

            CREATE VIRTUAL TABLE IF NOT EXISTS recordings_fts USING fts5(
                name,
                summary,
                topics,
                transcript,
                content='recordings',
                content_rowid='rowid',
                tokenize='porter'
            );

            CREATE TRIGGER IF NOT EXISTS recordings_ai AFTER INSERT ON recordings BEGIN
                INSERT INTO recordings_fts(rowid, name, summary, topics, transcript)
                VALUES (new.rowid, new.name, new.summary, new.topics, new.transcript);
            END;
            CREATE TRIGGER IF NOT EXISTS recordings_ad AFTER DELETE ON recordings BEGIN
                INSERT INTO recordings_fts(recordings_fts, rowid, name, summary, topics, transcript)
                VALUES ('delete', old.rowid, old.name, old.summary, old.topics, old.transcript);
            END;
            CREATE TRIGGER IF NOT EXISTS recordings_au AFTER UPDATE ON recordings BEGIN
                INSERT INTO recordings_fts(recordings_fts, rowid, name, summary, topics, transcript)
                VALUES ('delete', old.rowid, old.name, old.summary, old.topics, old.transcript);
                INSERT INTO recordings_fts(rowid, name, summary, topics, transcript)
                VALUES (new.rowid, new.name, new.summary, new.topics, new.transcript);
            END;

            CREATE TABLE IF NOT EXISTS topics (
                id TEXT PRIMARY KEY,
                call_id TEXT NOT NULL,
                canonical_topic_id TEXT,
                label TEXT NOT NULL,
                description TEXT,
                embedding_version INTEGER NOT NULL DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (call_id) REFERENCES recordings(id)
            );

            CREATE TABLE IF NOT EXISTS embedding_jobs (
                id TEXT PRIMARY KEY,
                call_id TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                error TEXT,
                FOREIGN KEY (call_id) REFERENCES recordings(id)
            );

            CREATE TABLE IF NOT EXISTS topic_chains_cache (
                user_id     INTEGER PRIMARY KEY,
                version     TEXT    NOT NULL,
                groups_json TEXT    NOT NULL,
                computed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        conn.commit()
        # Migration: add decisions column if missing
        try:
            conn.execute("ALTER TABLE recordings ADD COLUMN decisions TEXT NOT NULL DEFAULT '[]'")
            conn.commit()
        except sqlite3.OperationalError:
            pass
        # Migration: add color_index column to topics if missing
        try:
            conn.execute("ALTER TABLE topics ADD COLUMN color_index INTEGER NOT NULL DEFAULT 0")
            conn.commit()
            # Assign sequential color_index per recording for existing rows
            rows = conn.execute(
                "SELECT id, call_id FROM topics ORDER BY call_id, created_at, id"
            ).fetchall()
            counts: dict[str, int] = {}
            for r in rows:
                cid = r["call_id"]
                idx = counts.get(cid, 0)
                conn.execute("UPDATE topics SET color_index = ? WHERE id = ?", (idx, r["id"]))
                counts[cid] = idx + 1
            conn.commit()
        except sqlite3.OperationalError:
            pass
        # Rebuild FTS index from content table (fixes empty index if DB predated FTS)
        try:
            conn.execute("INSERT INTO recordings_fts(recordings_fts) VALUES('rebuild')")
            conn.commit()
        except sqlite3.OperationalError:
            pass


def get_users_collection():
    init_db()
    return None


def get_recordings_collection():
    init_db()
    return None


def seed_dummy_recordings():
    """Seed dummy recordings for user_id=1 (only if store is empty)."""
    with get_connection() as conn:
        if conn.execute("SELECT 1 FROM recordings LIMIT 1").fetchone():
            return

    DUMMY = [
        {"name": "Call with Steve", "duration": "5:36", "summary": "The meeting focused on aligning cross-functional teams around the Q1 product launch timeline, scope, and key risks.", "topics": ["Q1 product launch", "Phase 2"], "tone": "Professional", "transcript": "Steve: Hey, thanks for jumping on..."},
        {"name": "Call with Matt about Landscaping", "duration": "12:24", "summary": "Discussion of backyard landscaping project. Matt provided three quotes for the patio extension.", "topics": ["Landscaping", "Home improvement"], "tone": "Casual", "transcript": "Matt: So I've got the numbers for you..."},
        {"name": "Weekly sync with Engineering", "duration": "22:10", "summary": "Engineering standup covering sprint 12 progress. Blockers: API rate limiting.", "topics": ["Sprint planning", "Engineering"], "tone": "Technical", "transcript": "Dev lead: Let's go around..."},
        {"name": "Interview debrief - Senior Designer", "duration": "18:45", "summary": "Post-interview discussion for the Senior Designer role.", "topics": ["Hiring", "Design"], "tone": "Professional", "transcript": "HR: So what did you think of the presentation?"},
    ]
    for rec in reversed(DUMMY):
        add_recording(user_id=1, name=rec["name"], duration=rec["duration"], summary=rec["summary"], topics=rec["topics"], tone=rec["tone"], transcript=rec["transcript"])


# --- Users ---


def upsert_user(
    google_id: str,
    email: str,
    name: str,
    access_token: str,
    refresh_token: str | None,
    token_expiry: float | None,
) -> int:
    """Insert or update user. Returns user_id."""
    init_db()
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO users (google_id, email, name, access_token, refresh_token, token_expiry)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(google_id) DO UPDATE SET
                email = excluded.email,
                name = excluded.name,
                access_token = excluded.access_token,
                refresh_token = excluded.refresh_token,
                token_expiry = excluded.token_expiry
            """,
            (google_id, email, name or email, access_token, refresh_token or "", token_expiry or 0.0),
        )
        conn.commit()
        row = conn.execute("SELECT user_id FROM users WHERE google_id = ?", (google_id,)).fetchone()
        return row["user_id"]


def get_user_by_id(user_id: int) -> dict | None:
    """Get user metadata by user_id."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT user_id, google_id, email, name FROM users WHERE user_id = ?",
            (user_id,),
        ).fetchone()
        if not row:
            return None
        return {
            "user_id": row["user_id"],
            "google_id": row["google_id"],
            "email": row["email"],
            "name": row["name"] or row["email"],
        }


def get_user_credentials_metadata(user_id: int) -> dict | None:
    """Get OAuth token fields for a user."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT access_token, refresh_token, token_expiry FROM users WHERE user_id = ?",
            (user_id,),
        ).fetchone()
        if not row:
            return None
        return {
            "access_token": row["access_token"],
            "refresh_token": row["refresh_token"] or "",
            "token_expiry": float(row["token_expiry"] or 0),
        }


def update_user_tokens(user_id: int, access_token: str, token_expiry: float | None):
    """Update stored tokens after refresh."""
    with get_connection() as conn:
        conn.execute(
            "UPDATE users SET access_token = ?, token_expiry = ? WHERE user_id = ?",
            (access_token, token_expiry or 0.0, user_id),
        )
        conn.commit()


# --- Recordings ---


def add_recording(
    user_id: int,
    name: str,
    duration: str,
    summary: str,
    topics: list,
    tone: str,
    transcript: str,
    structured_topics: list[dict] | None = None,
    decisions: list[str] | None = None,
) -> str:
    """Add a recording. Returns recording id.
    topics: list of label strings (for recordings.topics JSON, used by FTS/display).
    structured_topics: optional list of {label, description} for topics table.
    decisions: optional list of decision strings from LLM extraction.
    """
    init_db()
    rec_id = f"rec_{uuid.uuid4().hex[:12]}"
    created_at = datetime.utcnow().isoformat()
    topics_json = json.dumps(topics)
    decisions_json = json.dumps(decisions if decisions is not None else [])

    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO recordings (id, user_id, name, duration, created_at, summary, topics, tone, transcript, decisions)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (rec_id, user_id, name, duration, created_at, summary, topics_json, tone, transcript, decisions_json),
        )
        conn.commit()

        if structured_topics:
            _insert_topics(conn, rec_id, structured_topics)

    return rec_id


def _insert_topics(conn: sqlite3.Connection, call_id: str, topics_data: list[dict], embedding_version: int = 0):
    """Insert topic rows for a call, assigning sequential color_index per recording."""
    created_at = datetime.utcnow().isoformat()
    existing = conn.execute(
        "SELECT COUNT(*) FROM topics WHERE call_id = ?", (call_id,)
    ).fetchone()[0]
    for i, t in enumerate(topics_data):
        label = (t.get("label") or "").strip()
        if not label:
            continue
        description = (t.get("description") or "").strip() or None
        topic_id = str(uuid.uuid4())
        conn.execute(
            """
            INSERT INTO topics (id, call_id, canonical_topic_id, label, description, embedding_version, color_index, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (topic_id, call_id, None, label, description, embedding_version, existing + i, created_at),
        )
    conn.commit()


def list_recordings(user_id: int) -> list[dict]:
    """List recordings for a user, newest first."""
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT id, name, duration, created_at
            FROM recordings
            WHERE user_id = ?
            ORDER BY created_at DESC
            """,
            (user_id,),
        ).fetchall()
    return [{"id": r["id"], "name": r["name"], "duration": r["duration"], "created_at": r["created_at"]} for r in rows]


def get_recording(rec_id: str, user_id: int) -> dict | None:
    """Get full recording by id (must belong to user)."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT id, name, duration, created_at, summary, topics, tone, transcript, COALESCE(decisions, '[]') as decisions FROM recordings WHERE id = ? AND user_id = ?",
            (rec_id, user_id),
        ).fetchone()
        if not row:
            return None
        topic_rows = conn.execute(
            "SELECT label, color_index FROM topics WHERE call_id = ? ORDER BY color_index",
            (rec_id,),
        ).fetchall()
    topics = json.loads(row["topics"]) if row["topics"] else []
    decisions = json.loads(row["decisions"]) if row["decisions"] else []
    topic_colors = {t["label"]: t["color_index"] for t in topic_rows}
    return {
        "id": row["id"],
        "name": row["name"],
        "duration": row["duration"],
        "created_at": row["created_at"],
        "summary": row["summary"],
        "topics": topics,
        "topic_colors": topic_colors,
        "tone": row["tone"],
        "transcript": row["transcript"],
        "decisions": decisions,
    }


def _search_recordings_like(conn: sqlite3.Connection, user_id: int, query: str, limit: int) -> list[dict]:
    """Fallback: search using LIKE over name, summary, topics, transcript."""
    words = [w.strip() for w in query.strip().split() if w.strip()]
    if not words:
        return []

    placeholders = []
    params = [user_id]
    for w in words:
        # Escape LIKE wildcards; use ! as escape char
        pattern = f"%{w.replace('!', '!!').replace('%', '!%').replace('_', '!_')}%"
        placeholders.append(
            "(r.name LIKE ? ESCAPE '!' OR r.summary LIKE ? ESCAPE '!' "
            "OR r.topics LIKE ? ESCAPE '!' OR r.transcript LIKE ? ESCAPE '!')"
        )
        params.extend([pattern] * 4)
    params.append(limit)

    sql = f"""
        SELECT r.id, r.name, r.duration, r.created_at
        FROM recordings r
        WHERE r.user_id = ? AND {" AND ".join(placeholders)}
        ORDER BY r.created_at DESC
        LIMIT ?
    """
    rows = conn.execute(sql, params).fetchall()
    return [{"id": r["id"], "name": r["name"], "duration": r["duration"], "created_at": r["created_at"]} for r in rows]


# --- Embedding jobs ---


def create_embedding_job(call_id: str) -> str:
    """Create a pending embedding job. Returns job id."""
    init_db()
    job_id = str(uuid.uuid4())
    now = datetime.utcnow().isoformat()
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO embedding_jobs (id, call_id, status, created_at, updated_at)
            VALUES (?, ?, 'pending', ?, ?)
            """,
            (job_id, call_id, now, now),
        )
        conn.commit()
    return job_id


def get_pending_embedding_jobs(limit: int = 5) -> list[dict]:
    """Get pending jobs for processing, ordered by created_at."""
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT id, call_id, status, created_at
            FROM embedding_jobs
            WHERE status = 'pending'
            ORDER BY created_at ASC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [{"id": r["id"], "call_id": r["call_id"], "status": r["status"], "created_at": r["created_at"]} for r in rows]


def update_embedding_job(job_id: str, status: str, error: str | None = None) -> None:
    """Update job status (processing, done, failed)."""
    now = datetime.utcnow().isoformat()
    with get_connection() as conn:
        conn.execute(
            """
            UPDATE embedding_jobs
            SET status = ?, updated_at = ?, error = ?
            WHERE id = ?
            """,
            (status, now, error or "", job_id),
        )
        conn.commit()


def get_recording_with_topics_for_embedding(call_id: str) -> dict | None:
    """Fetch recording + topics by call_id (for worker; no user_id check)."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT id, user_id, summary, created_at FROM recordings WHERE id = ?",
            (call_id,),
        ).fetchone()
        if not row:
            return None

        topic_rows = conn.execute(
            "SELECT id, label, description, canonical_topic_id FROM topics WHERE call_id = ?",
            (call_id,),
        ).fetchall()

    topics = [
        {
            "id": r["id"],
            "label": r["label"],
            "description": r["description"] or "",
            "canonical_topic_id": r["canonical_topic_id"] or "",
        }
        for r in topic_rows
    ]
    return {
        "id": row["id"],
        "user_id": row["user_id"],
        "summary": row["summary"],
        "created_at": row["created_at"],
        "topics": topics,
    }


def get_recordings_by_ids(user_id: int, rec_ids: list[str]) -> list[dict]:
    """Get recordings by ids (must belong to user). Returns id, name, summary, decisions, created_at."""
    if not rec_ids:
        return []
    with get_connection() as conn:
        placeholders = ",".join("?" * len(rec_ids))
        rows = conn.execute(
            f"SELECT id, name, summary, COALESCE(decisions, '[]') as decisions, created_at FROM recordings WHERE user_id = ? AND id IN ({placeholders})",
            [user_id] + list(rec_ids),
        ).fetchall()
    result = []
    for row in rows:
        decisions = json.loads(row["decisions"]) if row["decisions"] else []
        result.append({
            "id": row["id"],
            "name": row["name"],
            "summary": row["summary"],
            "decisions": decisions,
            "created_at": row["created_at"],
        })
    return result


def search_recordings(user_id: int, query: str, limit: int = 50) -> list[dict]:
    """Search recordings by name, summary, topics, transcript (LIKE-based)."""
    if not query or not query.strip():
        return list_recordings(user_id)

    with get_connection() as conn:
        return _search_recordings_like(conn, user_id, query.strip(), limit)


# --- Topic chain cache ---


def get_embedding_version(user_id: int) -> str:
    """Hash of all call_ids with completed embeddings for this user. Changes when new embeddings land."""
    with get_connection() as conn:
        rows = conn.execute(
            """SELECT DISTINCT r.id FROM recordings r
               JOIN embedding_jobs j ON j.call_id = r.id
               WHERE r.user_id = ? AND j.status = 'done'
               ORDER BY r.id""",
            (user_id,),
        ).fetchall()
    key = ",".join(r[0] for r in rows)
    return hashlib.sha256(key.encode()).hexdigest()


def get_topic_chains_cache(user_id: int) -> tuple[str, str] | None:
    """Returns (version, groups_json) or None if no cache exists."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT version, groups_json FROM topic_chains_cache WHERE user_id = ?",
            (user_id,),
        ).fetchone()
    return (row["version"], row["groups_json"]) if row else None


def set_topic_chains_cache(user_id: int, version: str, groups_json: str) -> None:
    """Upsert the computed topic chains result for a user."""
    with get_connection() as conn:
        conn.execute(
            """INSERT INTO topic_chains_cache (user_id, version, groups_json)
               VALUES (?, ?, ?)
               ON CONFLICT(user_id) DO UPDATE SET
                   version=excluded.version,
                   groups_json=excluded.groups_json,
                   computed_at=CURRENT_TIMESTAMP""",
            (user_id, version, groups_json),
        )
        conn.commit()
