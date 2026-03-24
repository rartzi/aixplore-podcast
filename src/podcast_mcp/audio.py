"""Audio synthesizer — converts a podcast transcript into audio using Gemini TTS.

Supports single-speaker and multi-speaker modes via the Gemini 2.5 TTS API.
Handles chunking for long transcripts and retries for flaky preview models.
"""

import asyncio
import base64
import io
import logging
import os
import time
import wave
from pathlib import Path
from typing import Optional

import httpx

from .config import (
    GeminiVoice,
    PodcastSettings,
    SpeakerMode,
    get_settings,
)
from .transcript import format_transcript_for_tts

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Chunking config — keep chunks small for the preview TTS model
# ---------------------------------------------------------------------------

# Max characters per TTS request. The preview TTS models disconnect on
# large payloads, so we keep this conservative. 3-5 dialogue turns each.
MAX_TTS_CHARS = 1500

# Retry config for flaky preview models
MAX_RETRIES = 3
RETRY_DELAY_BASE = 5  # seconds — doubles each retry


# ---------------------------------------------------------------------------
# Build TTS request body
# ---------------------------------------------------------------------------

def _build_tts_request_single(
    text: str,
    voice: GeminiVoice,
) -> dict:
    """Build a single-speaker TTS request body."""
    return {
        "contents": [
            {
                "parts": [{"text": text}],
            }
        ],
        "generationConfig": {
            "responseModalities": ["AUDIO"],
            "speechConfig": {
                "voiceConfig": {
                    "prebuiltVoiceConfig": {
                        "voiceName": voice.value,
                    }
                }
            },
        },
    }


def _build_tts_request_multi(
    text: str,
    host_name: str,
    guest_name: str,
    host_voice: GeminiVoice,
    guest_voice: GeminiVoice,
) -> dict:
    """Build a multi-speaker TTS request body."""
    return {
        "contents": [
            {
                "parts": [
                    {
                        "text": (
                            f"TTS the following conversation between "
                            f"{host_name} and {guest_name}:\n\n{text}"
                        )
                    }
                ],
            }
        ],
        "generationConfig": {
            "responseModalities": ["AUDIO"],
            "speechConfig": {
                "multiSpeakerVoiceConfig": {
                    "speakerVoiceConfigs": [
                        {
                            "speaker": host_name,
                            "voiceConfig": {
                                "prebuiltVoiceConfig": {
                                    "voiceName": host_voice.value,
                                }
                            },
                        },
                        {
                            "speaker": guest_name,
                            "voiceConfig": {
                                "prebuiltVoiceConfig": {
                                    "voiceName": guest_voice.value,
                                }
                            },
                        },
                    ]
                }
            },
        },
    }


# ---------------------------------------------------------------------------
# Chunk dialogue for TTS
# ---------------------------------------------------------------------------

def _chunk_dialogue(
    dialogue: list[dict[str, str]],
    max_chars: int = MAX_TTS_CHARS,
) -> list[list[dict[str, str]]]:
    """Split dialogue into chunks that fit within TTS input limits.

    Preserves speaker-turn boundaries — never splits mid-turn.
    """
    chunks: list[list[dict[str, str]]] = []
    current_chunk: list[dict[str, str]] = []
    current_chars = 0

    for turn in dialogue:
        turn_text = f"{turn['speaker']}: {turn['line']}"
        turn_len = len(turn_text)

        # If a single turn exceeds max_chars, it gets its own chunk
        if current_chars + turn_len > max_chars and current_chunk:
            chunks.append(current_chunk)
            current_chunk = []
            current_chars = 0

        current_chunk.append(turn)
        current_chars += turn_len

    if current_chunk:
        chunks.append(current_chunk)

    return chunks


# ---------------------------------------------------------------------------
# Call Gemini TTS API with retries
# ---------------------------------------------------------------------------

async def _call_tts_api(
    request_body: dict,
    settings: PodcastSettings,
    chunk_label: str = "",
) -> bytes:
    """Send a TTS request to Gemini and return raw audio bytes.

    Retries up to MAX_RETRIES times on connection errors and timeouts.
    """
    url = f"{settings.gemini_base_url}/models/{settings.gemini_tts_model}:generateContent"
    headers, params = settings.get_auth()

    last_error: Optional[Exception] = None

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            logger.info(
                "%s attempt %d/%d — calling TTS API...",
                chunk_label, attempt, MAX_RETRIES,
            )
            async with httpx.AsyncClient(timeout=180.0) as client:
                response = await client.post(
                    url, json=request_body, headers=headers, params=params,
                )
                response.raise_for_status()

            result = response.json()

            # Extract base64-encoded audio from response
            parts = result["candidates"][0]["content"]["parts"]
            for part in parts:
                if "inlineData" in part:
                    audio_b64 = part["inlineData"]["data"]
                    audio_bytes = base64.b64decode(audio_b64)
                    logger.info(
                        "%s success — got %d bytes of audio",
                        chunk_label, len(audio_bytes),
                    )
                    return audio_bytes

            raise KeyError("No inlineData found in response parts")

        except (
            httpx.ConnectError,
            httpx.RemoteProtocolError,
            httpx.ReadTimeout,
            httpx.WriteTimeout,
            httpx.PoolTimeout,
        ) as exc:
            last_error = exc
            delay = RETRY_DELAY_BASE * (2 ** (attempt - 1))
            logger.warning(
                "%s attempt %d failed (connection error: %s). Retrying in %ds...",
                chunk_label, attempt, type(exc).__name__, delay,
            )
            await asyncio.sleep(delay)

        except httpx.HTTPStatusError as exc:
            # 429 = rate limited, 503 = overloaded — retry these
            if exc.response.status_code in (429, 503):
                last_error = exc
                delay = RETRY_DELAY_BASE * (2 ** (attempt - 1))
                logger.warning(
                    "%s attempt %d got HTTP %d. Retrying in %ds...",
                    chunk_label, attempt, exc.response.status_code, delay,
                )
                await asyncio.sleep(delay)
            else:
                raise

        except (KeyError, IndexError) as exc:
            logger.error("%s failed to parse TTS response: %s", chunk_label, exc)
            raise ValueError(
                f"Gemini TTS response did not contain audio data. "
                f"Model: {settings.gemini_tts_model}"
            ) from exc

    # All retries exhausted
    raise ConnectionError(
        f"{chunk_label} TTS API failed after {MAX_RETRIES} attempts. "
        f"Last error: {last_error}"
    )


# ---------------------------------------------------------------------------
# WAV utilities
# ---------------------------------------------------------------------------

def _pcm_to_wav(
    pcm_data: bytes,
    sample_rate: int = 24000,
    channels: int = 1,
    sample_width: int = 2,
) -> bytes:
    """Wrap raw PCM bytes in a WAV header."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(sample_width)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm_data)
    return buf.getvalue()


def _extract_pcm_from_audio(audio_bytes: bytes) -> tuple[bytes, int, int, int]:
    """Extract raw PCM frames from audio data (WAV or raw PCM).

    Returns (pcm_frames, sample_rate, channels, sample_width).
    """
    try:
        buf = io.BytesIO(audio_bytes)
        with wave.open(buf, "rb") as wf:
            return (
                wf.readframes(wf.getnframes()),
                wf.getframerate(),
                wf.getnchannels(),
                wf.getsampwidth(),
            )
    except wave.Error:
        # Assume raw PCM: 24kHz, mono, 16-bit
        return audio_bytes, 24000, 1, 2


def _concatenate_audio_segments(segments: list[bytes]) -> bytes:
    """Concatenate multiple audio segments (WAV or PCM) into one WAV file."""
    if len(segments) == 1:
        data = segments[0]
        if data[:4] == b"RIFF":
            return data
        return _pcm_to_wav(data)

    all_frames = b""
    sample_rate = 24000
    channels = 1
    sample_width = 2

    for segment in segments:
        frames, sr, ch, sw = _extract_pcm_from_audio(segment)
        sample_rate = sr
        channels = ch
        sample_width = sw
        all_frames += frames

    return _pcm_to_wav(all_frames, sample_rate, channels, sample_width)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def synthesize_audio(
    dialogue: list[dict[str, str]],
    *,
    speaker_mode: Optional[SpeakerMode] = None,
    host_name: Optional[str] = None,
    guest_name: Optional[str] = None,
    host_voice: Optional[GeminiVoice] = None,
    guest_voice: Optional[GeminiVoice] = None,
    output_path: Optional[str] = None,
    settings: Optional[PodcastSettings] = None,
) -> str:
    """Synthesize a podcast transcript into an audio file.

    Args:
        dialogue: List of dicts with 'speaker' and 'line' keys.
        speaker_mode: Single or multi-speaker.
        host_name: Name of the host (must match transcript speaker names).
        guest_name: Name of the guest (must match transcript speaker names).
        host_voice: Gemini voice for the host.
        guest_voice: Gemini voice for the guest.
        output_path: Where to save the WAV file. Auto-generated if None.
        settings: Server settings (auto-loaded if None).

    Returns:
        Absolute path to the generated WAV file.
    """
    cfg = settings or get_settings()

    speaker_mode = speaker_mode or SpeakerMode.MULTI
    host_name = host_name or cfg.podcast_host_name
    guest_name = guest_name or cfg.podcast_guest_name
    host_voice = host_voice or cfg.podcast_host_voice
    guest_voice = guest_voice or cfg.podcast_guest_voice

    # Ensure output directory exists
    out_dir = Path(cfg.audio_output_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    if output_path is None:
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        output_path = str(out_dir / f"podcast_{timestamp}.wav")
    else:
        # Validate user-supplied output path
        out_file = Path(output_path).resolve()
        if ".." in Path(output_path).parts:
            raise ValueError(
                f"Path traversal detected in output_path: '{output_path}'. "
                "Use an absolute path or a path relative to the working directory."
            )
        if out_file.suffix.lower() != ".wav":
            raise ValueError(
                f"Output file must be a .wav file, got: '{out_file.suffix}'"
            )
        output_path = str(out_file)

    # Chunk the dialogue into small pieces for reliable TTS
    chunks = _chunk_dialogue(dialogue)
    total_turns = sum(len(c) for c in chunks)
    logger.info(
        "Synthesizing %d turns in %d chunk(s) | mode=%s | host_voice=%s | guest_voice=%s",
        total_turns, len(chunks), speaker_mode.value,
        host_voice.value, guest_voice.value,
    )

    audio_segments: list[bytes] = []
    start_time = time.time()

    for i, chunk in enumerate(chunks):
        chunk_label = f"[Chunk {i + 1}/{len(chunks)}]"
        chunk_text = format_transcript_for_tts(chunk)
        chars = len(chunk_text)

        logger.info(
            "%s %d turns, %d chars",
            chunk_label, len(chunk), chars,
        )

        # Build the TTS request
        if speaker_mode == SpeakerMode.SINGLE:
            request_body = _build_tts_request_single(chunk_text, host_voice)
        else:
            request_body = _build_tts_request_multi(
                chunk_text, host_name, guest_name, host_voice, guest_voice,
            )

        # Call the API with retries
        audio_bytes = await _call_tts_api(request_body, cfg, chunk_label)
        audio_segments.append(audio_bytes)

        # Brief pause between chunks to avoid rate limiting
        if i < len(chunks) - 1:
            await asyncio.sleep(2)

    elapsed = time.time() - start_time

    # Concatenate all segments into one WAV
    final_audio = _concatenate_audio_segments(audio_segments)

    # Write the output file
    output_file = Path(output_path)
    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_file.write_bytes(final_audio)

    file_size_mb = len(final_audio) / 1_048_576
    logger.info(
        "Audio saved: %s | %.2f MB | %d chunks in %.1fs",
        output_path, file_size_mb, len(chunks), elapsed,
    )
    return str(output_file.resolve())
