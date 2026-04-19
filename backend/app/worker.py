"""Background worker: polls embedding jobs, embeds, upserts to ChromaDB."""

import time

from app.db import (
    get_pending_embedding_jobs,
    get_recording_with_topics_for_embedding,
    update_embedding_job,
)
from app.services import embed_text
from app.chromadb_store import add_records


def process_job(job_id: str, call_id: str) -> None:
    """Process a single embedding job: fetch data, embed, upsert to ChromaDB."""
    rec = get_recording_with_topics_for_embedding(call_id)
    if not rec:
        raise ValueError(f"Recording not found: {call_id}")

    call_id = rec["id"]
    user_id = rec["user_id"]
    created_at = rec["created_at"]

    # Build combined text: summary + topics in single string for one embedding
    summary_text = (rec["summary"] or "").strip()
    topic_lines = []
    for t in rec["topics"]:
        label = (t.get("label") or "").strip()
        if label:
            topic_lines.append(f"- {label}")
    topics_block = "\n".join(topic_lines) if topic_lines else "- (none)"

    combined_text = f"Summary: {summary_text or '(none)'}\n\nTopics:\n{topics_block}"
    if not combined_text.strip():
        return

    vec = embed_text(combined_text)
    add_records(
        ids=[f"{call_id}_combined"],
        vectors=[vec],
        metadatas=[{
            "entity_type": "combined",
            "call_id": call_id,
            "topic_id": "",
            "canonical_topic_id": "",
            "org_id": f"user_{user_id}",
            "created_at": created_at,
        }],
    )


def run_once() -> int:
    """Process up to 5 pending jobs. Returns number processed."""
    jobs = get_pending_embedding_jobs(limit=5)
    processed = 0
    for job in jobs:
        job_id = job["id"]
        call_id = job["call_id"]
        try:
            update_embedding_job(job_id, "processing")
            process_job(job_id, call_id)
            update_embedding_job(job_id, "done")
            processed += 1
        except Exception as e:
            update_embedding_job(job_id, "failed", error=str(e))
    return processed


def main() -> None:
    """Poll for jobs until interrupted."""
    poll_interval = 3
    print(f"Worker started. Polling every {poll_interval}s. Ctrl+C to stop.")
    while True:
        try:
            n = run_once()
            if n > 0:
                print(f"Processed {n} job(s)")
        except KeyboardInterrupt:
            print("\nWorker stopped.")
            break
        except Exception as e:
            print(f"Worker error: {e}")
        time.sleep(poll_interval)


if __name__ == "__main__":
    main()
