# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

An MCP server that transforms documents (PDF, markdown, text) into podcast audio using Gemini AI. Two-phase pipeline: transcript generation (Gemini Flash/Pro) → audio synthesis (Gemini TTS). Exposed as three MCP tools: `podcast_generate_transcript`, `podcast_synthesize_audio`, `podcast_create`.

## Commands

```bash
# Install (editable, uv is preferred — much faster than pip)
uv pip install -e .

# Run the MCP server (stdio transport)
uv run podcast-mcp

# Run end-to-end test (requires GEMINI_API_KEY)
uv run python tests/test_e2e.py
uv run python tests/test_e2e.py --style scientific --length medium
uv run python tests/test_e2e.py --transcript-only

# Check available Gemini models
uv run python scripts/check_models.py
```

## Architecture

The package lives in `src/podcast_mcp/` with five modules:

- **server.py** — MCP server entry point. Defines three tools via `FastMCP` with Pydantic input models (`TranscriptInput`, `SynthesizeInput`, `CreateInput`). All tool handlers return JSON strings. Logging goes to stderr (MCP requirement).
- **config.py** — All enums (`PodcastStyle`, `AudienceLevel`, `PodcastLength`, `GeminiVoice`, `SpeakerMode`, `AuthMode`) and `PodcastSettings` (pydantic-settings, loads from env/.env). Auth auto-detection: `googleapis.com` URLs use `?key=` query param, everything else uses `x-api-key` header (Azure AI Gateway).
- **transcript.py** — Builds style-specific system prompts from `STYLE_PROMPTS` and `AUDIENCE_PROMPTS` dicts, calls Gemini `generateContent` with `responseMimeType: application/json` and a response schema to get structured `[{speaker, line}]` dialogue.
- **audio.py** — Chunks dialogue into ≤1500-char segments (TTS preview models disconnect on large payloads), calls Gemini TTS with retry logic (3 attempts, exponential backoff), concatenates WAV/PCM segments. Supports single-speaker (`voiceConfig`) and multi-speaker (`multiSpeakerVoiceConfig`) request formats.
- **content.py** — File extraction: PDF via pypdf, text/markdown/html via direct read. Truncates at 100k chars on sentence boundary.

## Key Design Decisions

- All Gemini API calls use `httpx.AsyncClient` directly (no SDK dependency).
- TTS chunking at 1500 chars is intentionally conservative — preview TTS models are unreliable with larger payloads.
- Settings singleton via `get_settings()` caches a single `PodcastSettings` instance.
- MCP tools accept `Optional` params everywhere and fall back to `PodcastSettings` defaults, so users only need to specify what they want to override.

## MCP Integration

Add to Claude Code config (`~/.claude.json` or project `.mcp.json`):

```json
{
  "mcpServers": {
    "podcast": {
      "command": "uv",
      "args": ["run", "--directory", "/path/to/podcast-mcp", "podcast-mcp"],
      "env": {
        "GEMINI_API_KEY": "your-key",
        "GEMINI_BASE_URL": "https://your-gateway/v1beta"
      }
    }
  }
}
```
