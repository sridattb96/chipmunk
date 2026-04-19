# Chipmunk

Record calls, get AI-generated summaries and transcripts, and save to Google Drive.

## Prerequisites

- Python 3.10–3.12 (**required** – ChromaDB does not work on Python 3.14+)
- Node.js 18+
- Google Cloud project with OAuth, Speech-to-Text, and Drive enabled
- OpenAI API key
- Service account JSON for Speech-to-Text

## Setup

### 1. Backend

```bash
cd backend
# Use Python 3.12 (ChromaDB incompatible with 3.14+)
python3.12 -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

Create `backend/.env` from the example:

```bash
cp .env.example .env
```

Fill in your values:

- `GOOGLE_CLIENT_ID` - OAuth 2.0 Web Client ID
- `GOOGLE_CLIENT_SECRET` - OAuth client secret
- `GOOGLE_APPLICATION_CREDENTIALS` - Path to service account JSON (e.g. `./credentials/service-account.json`)
- `OPENAI_API_KEY` - Your OpenAI API key
- `BACKEND_URL` - `http://localhost:8000`
- `FRONTEND_URL` - `http://localhost:5173`
- `SECRET_KEY` - Random string for session signing

Place your service account JSON at `backend/credentials/service-account.json`.

### 2. Frontend

```bash
cd frontend
npm install
```

### 3. Run

**ChromaDB (required when using embedding worker):** If you run both the backend and embedding worker, use a separate Chroma HTTP server to avoid data corruption (vectors/similarities disappearing). Otherwise both processes hit the same SQLite file and can corrupt it.

Terminal 1 (ChromaDB server, when using embedding worker):

```bash
cd backend && source venv/bin/activate && chroma run --path ./chroma_data --port 8100 --host localhost
```

Add to `backend/.env`:

```
CHROMA_HTTP_URL=http://localhost:8100
```

Terminal 2 (backend):

```bash
cd backend && source venv/bin/activate && python run.py
```

Terminal 3 (embedding worker, optional):

```bash
cd backend && source venv/bin/activate && python run_worker.py
```

Terminal 4 (frontend):

```bash
cd frontend && npm run dev
```

Open http://localhost:5173

The embedding worker polls for new recordings, generates embeddings (OpenAI text-embedding-3-large), and upserts into ChromaDB. Run it to enable semantic search over summaries and topics. If you skip the embedding worker, you can omit the Chroma server and `CHROMA_HTTP_URL`; ChromaDB will use direct file access (fine for single-process).

## Notes

- **Audio length**: For recordings over ~1 minute, set `GCS_BUCKET` in `.env` and create a bucket. The service account needs Storage write access. Short recordings work with inline audio.
- **Google Picker**: Uses `drive.file` scope; the Picker lets users choose where to save.
## All Recordings Page

Visit `/all` to browse past recordings. Data is stored in SQLite (`backend/chipmunk.db`) with FTS5 full-text search. Dummy recordings are seeded on startup for `user_id=1` if the store is empty.

## Flow

1. Sign in with Google
2. Start recording (uses microphone)
3. Stop recording → backend transcribes (Google STT) and summarizes (OpenAI)
4. View summary, transcript, and suggested actions
5. Click "Save to Google Drive" → choose folder in Google Picker → file is saved
