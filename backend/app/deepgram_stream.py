"""Deepgram WebSocket streaming proxy. Used when TRANSCRIPTION_MODE='stream'."""

import asyncio
import json
import logging

import websockets
from websockets.exceptions import ConnectionClosed, ConnectionClosedError, ConnectionClosedOK
from websockets.frames import CloseCode
from websockets.protocol import State

from app.config import DEEPGRAM_API_KEY

logger = logging.getLogger(__name__)

DEEPGRAM_WS_URL = "wss://api.deepgram.com/v1/listen"
# MediaRecorder produces WebM/Opus container. For containerized audio, omit encoding per Deepgram docs.
DEEPGRAM_PARAMS = "punctuate=true&interim_results=true"
KEEPALIVE_INTERVAL = 4  # seconds; Deepgram times out after ~10s without data


async def proxy_client_to_deepgram(
    client_receive,
    deepgram_ws,
    transcripts_callback,
):
    """
    Relay messages between client and Deepgram.
    - client_receive: async callable that returns (data, msg_type) or (None, 'disconnect')
      where data is bytes or str, msg_type in ('bytes','text','disconnect')
    - Deepgram sends: JSON with transcript results
    - transcripts_callback(transcript, is_final) is called for each result
    """
    full_transcript_parts = []

    async def receive_from_client():
        try:
            while True:
                data, msg_type = await client_receive()
                if msg_type == "disconnect":
                    break
                if msg_type == "bytes" and data:
                    await deepgram_ws.send(data)
                elif msg_type == "text" and data:
                    try:
                        obj = json.loads(data)
                        if obj.get("type") == "CloseStream":
                            logger.info("[Deepgram] Received CloseStream from client, forwarding to Deepgram")
                            await deepgram_ws.send(json.dumps({"type": "CloseStream"}))
                            break
                    except json.JSONDecodeError:
                        pass
        except Exception:
            pass

    async def receive_from_deepgram():
        nonlocal full_transcript_parts
        try:
            async for message in deepgram_ws:
                # Deepgram sends JSON as text; handle bytes if needed (websockets 16)
                text = message.decode("utf-8", errors="ignore") if isinstance(message, bytes) else message
                if not isinstance(text, str):
                    continue
                try:
                    obj = json.loads(text)
                    if obj.get("type") == "Results":
                        channel = obj.get("channel", {})
                        alternatives = channel.get("alternatives", [])
                        if alternatives:
                            transcript = alternatives[0].get("transcript", "").strip()
                            is_final = obj.get("is_final", False)
                            if transcript:
                                if is_final:
                                    full_transcript_parts.append(transcript)
                                transcripts_callback(transcript, is_final)
                    elif obj.get("type") == "UtteranceEnd":
                        pass
                    elif obj.get("type") == "Metadata":
                        # Deepgram sends this after CloseStream; we're done
                        return
                except (json.JSONDecodeError, KeyError):
                    pass
        except (ConnectionClosed, ConnectionClosedError, ConnectionClosedOK):
            pass

    async def keepalive_loop():
        while True:
            await asyncio.sleep(KEEPALIVE_INTERVAL)
            if deepgram_ws.state is State.OPEN:
                try:
                    await deepgram_ws.send(json.dumps({"type": "KeepAlive"}))
                except Exception:
                    break

    recv_client = asyncio.create_task(receive_from_client())
    recv_dg = asyncio.create_task(receive_from_deepgram())
    keepalive = asyncio.create_task(keepalive_loop())

    # Wait for client to finish (sends CloseStream). Then wait for Deepgram with a timeout.
    logger.info("[Deepgram] Waiting for client to send CloseStream...")
    await recv_client
    logger.info("[Deepgram] Client done, waiting for Deepgram response (10s timeout)...")
    keepalive.cancel()
    try:
        await keepalive
    except asyncio.CancelledError:
        pass
    try:
        await asyncio.wait_for(recv_dg, timeout=10.0)
        logger.info("[Deepgram] Got response from Deepgram")
    except asyncio.TimeoutError:
        logger.warning("[Deepgram] Timeout waiting for Deepgram, forcing close")
        if deepgram_ws.state is State.OPEN:
            try:
                await deepgram_ws.close(code=CloseCode.NORMAL_CLOSURE)
            except Exception:
                pass

    return " ".join(full_transcript_parts).strip()


async def run_deepgram_proxy(client_receive, transcripts_callback):
    """
    Connect to Deepgram, proxy client audio via client_receive, invoke transcripts_callback.
    client_receive: async fn that returns (data, msg_type) - data is bytes|str, msg_type in ('bytes','text','disconnect')
    Returns the final concatenated transcript.
    """
    if not DEEPGRAM_API_KEY:
        raise ValueError("DEEPGRAM_API_KEY is not set")

    url = f"{DEEPGRAM_WS_URL}?{DEEPGRAM_PARAMS}"
    headers = {"Authorization": f"Token {DEEPGRAM_API_KEY}"}

    try:
        async with websockets.connect(url, additional_headers=headers) as deepgram_ws:
            transcript = await proxy_client_to_deepgram(
                client_receive, deepgram_ws, transcripts_callback
            )
            return transcript
    except Exception as e:
        logger.exception("Deepgram WebSocket error")
        raise
