# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

Chipmunk records calls, transcribes them (Google STT or Deepgram streaming), summarizes with OpenAI, and saves to Google Drive. A background worker embeds recordings into ChromaDB for semantic similarity ("topic chains").

## Commands

### Backend
```bash
cd backend
python3.12 -m venv venv          # Python 3.12 required — ChromaDB breaks on 3.14+
source venv/bin/activate
pip install -r requirements.txt
python run.py                      # API server on :8000
python run_worker.py               # Embedding worker (separate terminal)
python run_worker.py --once        # Process pending jobs once and exit
chroma run --path ./chroma_data --port 8100 --host localhost  # Chroma server (multi-process only)
```

### Frontend
```bash
cd frontend
npm install
npm run dev      # Dev server on :5173
npm run build
npm run lint
```

### Environment
Copy `backend/.env.example` → `backend/.env`. Required vars:
- `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` — OAuth Web Client
- `GOOGLE_APPLICATION_CREDENTIALS` — path to service account JSON (local)
- `GOOGLE_APPLICATION_CREDENTIALS_JSON` — full JSON contents (Railway/production)
- `OPENAI_API_KEY`
- `DEEPGRAM_API_KEY` — needed when `TRANSCRIPTION_MODE=stream` (current default)
- `BACKEND_URL`, `FRONTEND_URL`, `SECRET_KEY`
- `GCS_BUCKET` — optional; required for Google STT on recordings > ~1 min
- `CHROMA_HTTP_URL` — e.g. `http://localhost:8100`; set when running the embedding worker alongside the API to avoid SQLite corruption

Frontend env: `VITE_API_URL` (defaults to same origin).

## Architecture

### Backend (`backend/app/`)
FastAPI app with SQLite primary store and ChromaDB vector store.

- **`main.py`** — all HTTP/WebSocket routes. Auth via `require_auth` dependency (reads `Authorization: Bearer <token>`, validates against session store).
- **`auth.py`** — Google OAuth flow (`/auth/google` → Google → `/auth/google/callback` → frontend with `?token=`).
- **`session.py`** — itsdangerous-signed session tokens stored in memory.
- **`db.py`** — SQLite schema and all queries. Tables: `users`, `recordings` (with FTS5 virtual table + triggers), `topics`, `embedding_jobs`, `topic_chains_cache`. Schema migrations run inline in `init_db()`.
- **`services.py`** — transcription (Google STT batch or Deepgram stream), OpenAI summarization/extraction (`extract_structured_data` returns `{summary, topics, decisions}`), Google Drive upload, topic chain computation, and `embed_text` (OpenAI `text-embedding-3-large`).
- **`chromadb_store.py`** — thin wrapper around ChromaDB. Uses `HttpClient` when `CHROMA_HTTP_URL` is set, `PersistentClient` otherwise.
- **`worker.py`** — polls `embedding_jobs` table, embeds `summary + topics` as a combined vector, upserts to ChromaDB.
- **`deepgram_stream.py`** — WebSocket proxy to Deepgram for live transcription.
- **`config.py`** — all env var loading. Production uses `GOOGLE_APPLICATION_CREDENTIALS_JSON` (writes to a temp file).

### Transcription modes
Controlled by `TRANSCRIPTION_MODE` in `services.py` (currently `"stream"`):
- `batch` — uploads audio to Google STT; uses GCS for files > ~1 min.
- `stream` — Deepgram WebSocket (`/api/recordings/stream-transcribe`); client streams audio chunks, backend proxies to Deepgram, final transcript sent to `/api/recordings/save-transcript`.

### Frontend (`frontend/src/`)
React 19 + Vite SPA with `react-router-dom` v7.

- **`main.jsx`** → **`App.jsx`** — root. Handles OAuth token capture from `?token=` query param on load, routes authenticated users to `AppShell` + child routes.
- **`AppShell.jsx`** — persistent nav shell (header with links to All Recordings, Topic Chains, DB).
- **`useAuth.js`** — auth state hook; stores session token in `localStorage`, fetches `/auth/me`.
- **`api.js`** — all `fetch` calls to backend, attaches `Authorization: Bearer` header.
- **`AllRecordings.jsx`** — main page: recording list + search + recording modal trigger.
- **`AudioRecorder.jsx`** — `MediaRecorder` or WebSocket streaming to backend.
- **`RecordingModal.jsx`** — shows transcript, summary, topics, decisions; triggers Drive save via `DrivePicker.jsx`.
- **`TopicChains.jsx`** — renders semantically grouped recordings from `/api/topic-chains`.
- **`DbSnapshot.jsx`** — admin debug view of SQLite + ChromaDB state.

### Data flow (stream mode)
1. `AudioRecorder` opens WebSocket to `/api/recordings/stream-transcribe?token=...`
2. Audio chunks streamed → backend proxies to Deepgram → interim transcripts sent back
3. On stop: client POSTs full transcript to `/api/recordings/save-transcript`
4. Backend runs `extract_structured_data` (OpenAI) → stores recording in SQLite → creates `embedding_job`
5. Worker picks up job → embeds with OpenAI → upserts to ChromaDB
6. `/api/topic-chains` queries ChromaDB for similar recordings, caches result in `topic_chains_cache`
