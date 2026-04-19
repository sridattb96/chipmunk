"""Reset ChromaDB (delete all vectors). Use when you see "Error finding id" repeatedly.

Also resets embedding jobs to 'pending' so the worker will re-embed on next run.

Run: cd backend && python scripts/reset_chromadb.py
"""

import sys
import shutil
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import CHROMA_PATH
from app.db import get_connection


def main():
    if CHROMA_PATH.exists():
        shutil.rmtree(CHROMA_PATH)
        print(f"Deleted ChromaDB at {CHROMA_PATH}")
    else:
        print(f"ChromaDB path {CHROMA_PATH} does not exist (already clean)")

    with get_connection() as conn:
        cur = conn.execute(
            "UPDATE embedding_jobs SET status = 'pending', error = NULL WHERE status IN ('done', 'failed')"
        )
        conn.commit()
        print(f"Reset {cur.rowcount} embedding job(s) to pending")

    print("Run the embedding worker to re-embed all recordings.")


if __name__ == "__main__":
    main()
