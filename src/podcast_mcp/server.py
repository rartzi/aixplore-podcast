#!/usr/bin/env python3
"""AIXplore Podcast Generator — MCP Server.

Provides three tools for generating engaging podcast audio from content:
  1. podcast_generate_transcript — content → structured dialogue JSON
  2. podcast_synthesize_audio   — transcript → WAV audio file
  3. podcast_create             — content → audio in one shot (end-to-end)

Configuration via environment variables or .env file.
See config.py for all available settings.
"""

import json
import logging
import sys
from typing import Optional

from pydantic import BaseModel, Field, ConfigDict
from mcp.server.fastmcp import FastMCP

from .config import (
    AudienceLevel,
    GeminiVoice,
    PodcastLength,
    PodcastSettings,
    PodcastStyle,
    SpeakerMode,
    get_settings,
)
from .content import extract_content, truncate_content
from .transcript import (
    generate_transcript,
    format_transcript_markdown,
    format_transcript_for_tts,
)
from .audio import synthesize_audio

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    stream=sys.stderr,  # MCP servers must log to stderr, not stdout
)
logger = logging.getLogger("podcast_mcp")


# ---------------------------------------------------------------------------
# Initialize MCP server
# ---------------------------------------------------------------------------

mcp = FastMCP("podcast_mcp")


# ---------------------------------------------------------------------------
# Input models
# ---------------------------------------------------------------------------

class TranscriptInput(BaseModel):
    """Input for generating a podcast transcript from content."""
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    content: Optional[str] = Field(
        default=None,
        description=(
            "Source content as text. Provide either 'content' (raw text/markdown) "
            "or 'file_path' (path to a PDF, .md, or .txt file), not both."
        ),
    )
    file_path: Optional[str] = Field(
        default=None,
        description="Path to a source file (.pdf, .md, .txt, .html). Used if 'content' is not provided.",
    )
    style: Optional[PodcastStyle] = Field(
        default=None,
        description=(
            "Podcast editorial style. Options: scientific, technical_deep_dive, "
            "topic_explainer, interview, news_briefing, casual_chat, debate, storytelling. "
            "Default: from PODCAST_DEFAULT_STYLE env var."
        ),
    )
    audience: Optional[AudienceLevel] = Field(
        default=None,
        description=(
            "Target audience level. Options: general, technical, expert, executive. "
            "Default: from PODCAST_DEFAULT_AUDIENCE env var."
        ),
    )
    length: Optional[PodcastLength] = Field(
        default=None,
        description=(
            "Target podcast length. Options: short (~2-3 min), medium (~5-8 min), "
            "long (~12-18 min). Default: from PODCAST_DEFAULT_LENGTH env var."
        ),
    )
    speaker_mode: Optional[SpeakerMode] = Field(
        default=None,
        description="Speaker mode: 'single' (monologue) or 'multi' (conversation). Default: multi.",
    )
    show_name: Optional[str] = Field(
        default=None,
        description="Name of the podcast show. Default: from PODCAST_SHOW_NAME env var.",
    )
    host_name: Optional[str] = Field(
        default=None,
        description="Name of the host speaker. Default: from PODCAST_HOST_NAME env var.",
    )
    guest_name: Optional[str] = Field(
        default=None,
        description="Name of the guest speaker. Default: from PODCAST_GUEST_NAME env var.",
    )


class SynthesizeInput(BaseModel):
    """Input for synthesizing audio from a transcript."""
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    transcript: list[dict] = Field(
        ...,
        description=(
            'JSON array of dialogue turns. Each element: {"speaker": "Name", "line": "text"}. '
            "This is the output of the podcast_generate_transcript tool."
        ),
    )
    speaker_mode: Optional[SpeakerMode] = Field(
        default=None,
        description="Speaker mode: 'single' or 'multi'. Default: multi.",
    )
    host_name: Optional[str] = Field(
        default=None,
        description="Host speaker name (must match transcript speaker names).",
    )
    guest_name: Optional[str] = Field(
        default=None,
        description="Guest speaker name (must match transcript speaker names).",
    )
    host_voice: Optional[GeminiVoice] = Field(
        default=None,
        description=(
            "Voice for the host. Male: Puck (friendly), Charon (authoritative), "
            "Fenrir (dynamic), Orus (calm). Female: Kore (professional), Aoede (warm), "
            "Leda (clear), Zephyr (upbeat). Default: from PODCAST_HOST_VOICE env var."
        ),
    )
    guest_voice: Optional[GeminiVoice] = Field(
        default=None,
        description="Voice for the guest. Same options as host_voice. Default: from PODCAST_GUEST_VOICE env var.",
    )
    output_path: Optional[str] = Field(
        default=None,
        description="Output file path for the WAV audio. Auto-generated if not provided.",
    )


class CreateInput(BaseModel):
    """Input for end-to-end podcast creation (content → audio)."""
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    # Content source
    content: Optional[str] = Field(
        default=None,
        description="Source content as text. Provide either 'content' or 'file_path'.",
    )
    file_path: Optional[str] = Field(
        default=None,
        description="Path to a source file (.pdf, .md, .txt, .html).",
    )

    # Transcript options
    style: Optional[PodcastStyle] = Field(default=None, description="Podcast style.")
    audience: Optional[AudienceLevel] = Field(default=None, description="Target audience level.")
    length: Optional[PodcastLength] = Field(default=None, description="Target length: short, medium, long.")
    speaker_mode: Optional[SpeakerMode] = Field(default=None, description="single or multi speaker.")
    show_name: Optional[str] = Field(default=None, description="Podcast show name.")
    host_name: Optional[str] = Field(default=None, description="Host speaker name.")
    guest_name: Optional[str] = Field(default=None, description="Guest speaker name.")

    # Audio options
    host_voice: Optional[GeminiVoice] = Field(default=None, description="Host voice.")
    guest_voice: Optional[GeminiVoice] = Field(default=None, description="Guest voice.")
    output_path: Optional[str] = Field(default=None, description="Output WAV file path.")


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _resolve_content(content: Optional[str], file_path: Optional[str]) -> str:
    """Resolve the source content from either raw text or a file path."""
    if content and file_path:
        raise ValueError("Provide either 'content' or 'file_path', not both.")
    if not content and not file_path:
        raise ValueError("You must provide either 'content' (text) or 'file_path' (path to a file).")

    if file_path:
        raw = extract_content(file_path)
    else:
        raw = content  # type: ignore

    return truncate_content(raw)


# ---------------------------------------------------------------------------
# Tool 1: Generate Transcript
# ---------------------------------------------------------------------------

@mcp.tool(
    name="podcast_generate_transcript",
    annotations={
        "title": "Generate Podcast Transcript",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": True,
    },
)
async def podcast_generate_transcript(params: TranscriptInput) -> str:
    """Generate an engaging podcast dialogue transcript from source content.

    Takes text content or a file (PDF, markdown, text) and produces a structured
    JSON dialogue between a host and guest. The transcript can be reviewed and
    edited before audio synthesis.

    The transcript is generated using Gemini and styled according to the chosen
    podcast format (scientific, technical deep-dive, casual chat, etc.).

    Args:
        params (TranscriptInput): Configuration including:
            - content (str): Raw text/markdown source, OR
            - file_path (str): Path to .pdf, .md, .txt file
            - style: Podcast style (scientific, technical_deep_dive, etc.)
            - audience: Target audience (general, technical, expert, executive)
            - length: Duration target (short, medium, long)
            - speaker_mode: single or multi speaker
            - show_name, host_name, guest_name: Speaker configuration

    Returns:
        str: JSON object with 'transcript' (array of {speaker, line} turns)
             and 'transcript_markdown' (human-readable formatted version).

    Examples:
        - "Generate a technical podcast from my research paper" →
          file_path="/path/to/paper.pdf", style="scientific", audience="technical"
        - "Create a casual explainer from this markdown" →
          content="...", style="casual_chat", audience="general"
    """
    try:
        text = _resolve_content(params.content, params.file_path)

        dialogue = await generate_transcript(
            text,
            style=params.style,
            audience=params.audience,
            length=params.length,
            speaker_mode=params.speaker_mode,
            show_name=params.show_name,
            host_name=params.host_name,
            guest_name=params.guest_name,
        )

        markdown = format_transcript_markdown(dialogue)

        result = {
            "status": "success",
            "turn_count": len(dialogue),
            "transcript": dialogue,
            "transcript_markdown": markdown,
        }
        return json.dumps(result, indent=2, ensure_ascii=False)

    except Exception as e:
        logger.error("Transcript generation failed: %s", e, exc_info=True)
        return json.dumps({
            "status": "error",
            "error": str(e),
            "hint": "Check your GEMINI_API_KEY and GEMINI_BASE_URL settings.",
        })


# ---------------------------------------------------------------------------
# Tool 2: Synthesize Audio
# ---------------------------------------------------------------------------

@mcp.tool(
    name="podcast_synthesize_audio",
    annotations={
        "title": "Synthesize Podcast Audio",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": True,
    },
)
async def podcast_synthesize_audio(params: SynthesizeInput) -> str:
    """Convert a podcast transcript into a WAV audio file using Gemini TTS.

    Takes the structured dialogue output from podcast_generate_transcript
    and synthesizes it into natural-sounding audio with distinct speaker voices.

    For long transcripts, the audio is generated in chunks and concatenated.

    Args:
        params (SynthesizeInput): Configuration including:
            - transcript: Array of {speaker, line} dialogue turns (required)
            - speaker_mode: single or multi
            - host_name, guest_name: Must match speaker names in transcript
            - host_voice, guest_voice: Gemini voice selection
            - output_path: Where to save the WAV file

    Returns:
        str: JSON with 'audio_path' (absolute path to generated WAV),
             'duration_estimate' (rough minutes), and 'file_size_mb'.
    """
    try:
        audio_path = await synthesize_audio(
            params.transcript,
            speaker_mode=params.speaker_mode,
            host_name=params.host_name,
            guest_name=params.guest_name,
            host_voice=params.host_voice,
            guest_voice=params.guest_voice,
            output_path=params.output_path,
        )

        import os
        file_size = os.path.getsize(audio_path)
        # Rough estimate: 24kHz, 16-bit mono → ~48KB/sec → ~2.88MB/min
        duration_min = file_size / (48_000 * 60)

        result = {
            "status": "success",
            "audio_path": audio_path,
            "file_size_mb": round(file_size / 1_048_576, 2),
            "duration_estimate_min": round(duration_min, 1),
        }
        return json.dumps(result, indent=2)

    except Exception as e:
        logger.error("Audio synthesis failed: %s", e, exc_info=True)
        return json.dumps({
            "status": "error",
            "error": str(e),
            "hint": "Check your GEMINI_API_KEY, GEMINI_BASE_URL, and that the TTS model is available.",
        })


# ---------------------------------------------------------------------------
# Tool 3: Create Podcast (end-to-end)
# ---------------------------------------------------------------------------

@mcp.tool(
    name="podcast_create",
    annotations={
        "title": "Create Podcast (End-to-End)",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": True,
    },
)
async def podcast_create(params: CreateInput) -> str:
    """Create a complete podcast from content in one step.

    This is the all-in-one tool that takes source content (text or file),
    generates an engaging dialogue transcript, and synthesizes it into audio.

    Combines podcast_generate_transcript + podcast_synthesize_audio into
    a single operation. Use the individual tools if you want to review or
    edit the transcript before synthesis.

    Args:
        params (CreateInput): Full configuration including:
            - content/file_path: Source material
            - style, audience, length: Podcast parameters
            - speaker_mode, show_name, host_name, guest_name: Speaker config
            - host_voice, guest_voice: Voice selection
            - output_path: Output WAV file path

    Returns:
        str: JSON with 'transcript' (the generated dialogue),
             'transcript_markdown' (readable version),
             'audio_path', 'file_size_mb', 'duration_estimate_min'.

    Examples:
        - "Create a podcast from this PDF" →
          file_path="/path/to/doc.pdf"
        - "Make an AIXplore episode about transformers" →
          content="...", show_name="AIXplore", style="technical_deep_dive"
    """
    try:
        # Phase 1: Extract content
        text = _resolve_content(params.content, params.file_path)

        # Phase 2: Generate transcript
        dialogue = await generate_transcript(
            text,
            style=params.style,
            audience=params.audience,
            length=params.length,
            speaker_mode=params.speaker_mode,
            show_name=params.show_name,
            host_name=params.host_name,
            guest_name=params.guest_name,
        )

        markdown = format_transcript_markdown(dialogue)

        # Phase 3: Synthesize audio
        audio_path = await synthesize_audio(
            dialogue,
            speaker_mode=params.speaker_mode,
            host_name=params.host_name,
            guest_name=params.guest_name,
            host_voice=params.host_voice,
            guest_voice=params.guest_voice,
            output_path=params.output_path,
        )

        import os
        file_size = os.path.getsize(audio_path)
        duration_min = file_size / (48_000 * 60)

        result = {
            "status": "success",
            "turn_count": len(dialogue),
            "transcript": dialogue,
            "transcript_markdown": markdown,
            "audio_path": audio_path,
            "file_size_mb": round(file_size / 1_048_576, 2),
            "duration_estimate_min": round(duration_min, 1),
        }
        return json.dumps(result, indent=2, ensure_ascii=False)

    except Exception as e:
        logger.error("Podcast creation failed: %s", e, exc_info=True)
        return json.dumps({
            "status": "error",
            "error": str(e),
            "hint": "Check your GEMINI_API_KEY, GEMINI_BASE_URL, and input content.",
        })


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

def main():
    """Run the MCP server (stdio transport)."""
    settings = get_settings()
    if not settings.gemini_api_key:
        logger.warning(
            "GEMINI_API_KEY is not set. The server will start but API calls will fail. "
            "Set it via environment variable or .env file."
        )
    logger.info(
        "Starting podcast_mcp server | show=%s | host=%s | guest=%s | tts_model=%s",
        settings.podcast_show_name,
        settings.podcast_host_name,
        settings.podcast_guest_name,
        settings.gemini_tts_model,
    )
    mcp.run()


if __name__ == "__main__":
    main()
