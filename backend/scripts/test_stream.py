#!/usr/bin/env python3
"""
Stream transcription test harness.

Feeds a pre-recorded audio file through the backend WebSocket pipeline,
simulating the frontend's behavior including WS reconnects. No UI or mic needed.

Requirements:
  - ffmpeg + ffprobe in PATH
  - Backend running locally (or set BACKEND_URL)
  - A session token from the browser:
      DevTools > Console > localStorage.getItem('chipmunk_token')

Usage:
  # Simple run (no reconnects):
  TEST_TOKEN=<token> python scripts/test_stream.py path/to/audio.mp3

  # Simulate 3 WS reconnects (splits audio into 4 segments):
  TEST_TOKEN=<token> python scripts/test_stream.py path/to/audio.mp3 --reconnects 3

  # Custom name and base URL:
  TEST_TOKEN=<token> python scripts/test_stream.py audio.mp3 --name "Eng standup" --base-url http://localhost:8000
"""

import argparse
import asyncio
import json
import os
import subprocess
import sys
import tempfile

import requests
import websockets

CHUNK_SIZE = 4096   # bytes per WS send — matches a ~250ms chunk at 128kbps
CHUNK_DELAY = 0.05  # 50ms between sends (10x real-time; fast but Deepgram handles it)


# ---------------------------------------------------------------------------
# Audio helpers
# ---------------------------------------------------------------------------

def get_duration(path: str) -> float:
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", path],
        capture_output=True, text=True, check=True,
    )
    return float(result.stdout.strip())


def split_to_webm_segments(input_path: str, n: int) -> list[str]:
    """
    Convert input audio → n WebM/Opus segments of equal duration.
    Each segment is a self-contained WebM file (proper header) so
    Deepgram can decode it independently — same as what MediaRecorder
    produces when the WS reconnects and a new session starts.
    """
    duration = get_duration(input_path)
    seg_dur = duration / n
    paths = []
    for i in range(n):
        tmp = tempfile.NamedTemporaryFile(suffix=".webm", delete=False)
        tmp.close()
        subprocess.run(
            [
                "ffmpeg", "-y",
                "-i", input_path,
                "-ss", str(i * seg_dur),
                "-t", str(seg_dur),
                "-c:a", "libopus", "-b:a", "32k",
                "-f", "webm", tmp.name,
            ],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        paths.append(tmp.name)
    return paths


# ---------------------------------------------------------------------------
# WebSocket session
# ---------------------------------------------------------------------------

async def _receive_messages(ws, transcript_parts: list, wait_for_done: bool) -> None:
    """
    Collect is_final transcript fragments and optionally wait for the 'done' message.
    Mirrors what makeOnMessage() does in RecordingModal.jsx.
    """
    async for raw in ws:
        try:
            msg = json.loads(raw)
        except Exception:
            continue

        if msg.get("transcript") and msg.get("is_final"):
            transcript_parts.append(msg["transcript"])
            preview = msg["transcript"][:70].replace("\n", " ")
            print(f"    [final] {preview}{'…' if len(msg['transcript']) > 70 else ''}")

        if msg.get("type") == "done":
            if wait_for_done:
                print(f"    [done]  session complete")
            break

        if msg.get("type") == "error":
            print(f"    [error] {msg.get('error')}")
            break


async def stream_segment(
    ws_url: str,
    segment_path: str,
    transcript_parts: list,
    session_num: int,
    total_sessions: int,
) -> None:
    """
    Stream one audio segment over a single WS session.
    Mirrors one lifecycle of the WebSocket in RecordingModal.jsx:
      open → send chunks → send CloseStream → (wait for done if last session)
    """
    is_last = session_num == total_sessions

    with open(segment_path, "rb") as f:
        audio = f.read()

    chunks = [audio[i : i + CHUNK_SIZE] for i in range(0, len(audio), CHUNK_SIZE)]
    label = "(final)" if is_last else "(reconnect)"
    print(f"\n  [Session {session_num}/{total_sessions}] {label}  {len(audio):,} bytes → {len(chunks)} chunks")

    async with websockets.connect(ws_url) as ws:
        # Receive concurrently while sending — same as the frontend's onmessage handler
        recv_task = asyncio.create_task(
            _receive_messages(ws, transcript_parts, wait_for_done=is_last)
        )

        for chunk in chunks:
            await ws.send(chunk)
            await asyncio.sleep(CHUNK_DELAY)

        # Mirror: frontend sends CloseStream on stop / reconnect
        await ws.send(json.dumps({"type": "CloseStream"}))
        print(f"    [CloseStream sent]")

        if is_last:
            # Wait for backend to flush Deepgram's final response
            await recv_task
        else:
            # Non-final session: collect any remaining is_final messages for up to 3s,
            # then move on — exactly what the frontend does by silencing the old WS.
            try:
                await asyncio.wait_for(recv_task, timeout=3.0)
            except asyncio.TimeoutError:
                recv_task.cancel()
                try:
                    await recv_task
                except asyncio.CancelledError:
                    pass


# ---------------------------------------------------------------------------
# Main test flow
# ---------------------------------------------------------------------------

async def run(token: str, audio_file: str, n_reconnects: int, name: str, base_url: str) -> None:
    ws_base = base_url.replace("http://", "ws://").replace("https://", "wss://")
    ws_url = f"{ws_base}/api/recordings/stream-transcribe?token={token}"

    n_segments = n_reconnects + 1
    print(f"Splitting '{audio_file}' → {n_segments} WebM segment(s)…")
    segment_paths = split_to_webm_segments(audio_file, n_segments)

    transcript_parts: list[str] = []

    try:
        for i, seg_path in enumerate(segment_paths, start=1):
            await stream_segment(ws_url, seg_path, transcript_parts, i, n_segments)
    finally:
        for p in segment_paths:
            try:
                os.unlink(p)
            except OSError:
                pass

    full_transcript = " ".join(transcript_parts)

    if not full_transcript.strip():
        print("\n[WARN] No transcript collected.")
        print("       Check: Deepgram API key is set, audio has speech, backend is running.")
        return

    total_secs = get_duration(audio_file)
    duration_str = f"{int(total_secs // 60)}:{int(total_secs % 60):02d}"

    print(f"\nSaving recording ({len(full_transcript)} chars, {duration_str})…")
    resp = requests.post(
        f"{base_url}/api/recordings/save-transcript",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": name, "duration": duration_str, "transcript": full_transcript},
        timeout=60,
    )
    resp.raise_for_status()
    data = resp.json()

    print("\n=== RESULT ===")
    print(f"ID       : {data['id']}")
    print(f"Topics   : {', '.join(data.get('topics', [])) or 'none'}")
    print(f"Summary  :\n{data.get('summary', '')}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Chipmunk stream transcription test harness")
    parser.add_argument("audio", help="Audio file to stream (mp3, wav, m4a, webm, …)")
    parser.add_argument(
        "--reconnects", type=int, default=0,
        help="Number of WS reconnects to simulate (default: 0 = single session)",
    )
    parser.add_argument("--name", default="Test Stream Recording", help="Recording name")
    parser.add_argument(
        "--base-url", default=os.getenv("BACKEND_URL", "http://localhost:8000"),
        help="Backend base URL",
    )
    parser.add_argument(
        "--token", default=os.getenv("TEST_TOKEN"),
        help="Session token (or set TEST_TOKEN env var)",
    )
    args = parser.parse_args()

    if not args.token:
        print("Error: session token required.")
        print("  Get it from the browser console: localStorage.getItem('chipmunk_token')")
        print("  Then run: TEST_TOKEN=<token> python scripts/test_stream.py audio.mp3")
        sys.exit(1)

    if not os.path.exists(args.audio):
        print(f"Error: file not found: {args.audio}")
        sys.exit(1)

    asyncio.run(run(args.token, args.audio, args.reconnects, args.name, args.base_url))


if __name__ == "__main__":
    main()
