"""Queue and run embedding jobs for the last 5 recordings.

Uses the new combined (summary + topics) embedding format.

Run: cd backend && python scripts/embed_last_recordings.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db import get_connection, create_embedding_job
from app.worker import run_once


def main():
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT r.id FROM recordings r
            ORDER BY r.created_at DESC
            LIMIT 5
            """
        ).fetchall()
        call_ids = [r["id"] for r in rows]

    if not call_ids:
        print("No recordings found.")
        return

    # Set all jobs to done, then set last 5 to pending (so only those get processed)
    with get_connection() as conn:
        conn.execute("UPDATE embedding_jobs SET status = 'done' WHERE 1=1")
        for call_id in call_ids:
            existing = conn.execute(
                "SELECT id FROM embedding_jobs WHERE call_id = ?",
                (call_id,),
            ).fetchone()
            if existing:
                conn.execute(
                    "UPDATE embedding_jobs SET status = 'pending', error = NULL WHERE call_id = ?",
                    (call_id,),
                )
            else:
                create_embedding_job(call_id)
        conn.commit()

    print(f"Queued last {len(call_ids)} recording(s): {call_ids}")

    # Run worker until no more pending
    total = 0
    while True:
        n = run_once()
        total += n
        if n > 0:
            print(f"Processed {n} job(s)")
        if n == 0:
            break

    print(f"Done. Embedded {total} recording(s).")


if __name__ == "__main__":
    main()
