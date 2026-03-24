"""Configuration and settings for the Podcast MCP server.

Loads settings from environment variables, .env file, or Azure Key Vault.
Each user provides their own GEMINI_API_KEY.
"""

import os
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, ConfigDict
from pydantic_settings import BaseSettings


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class PodcastStyle(str, Enum):
    """The editorial style / genre of the podcast."""
    SCIENTIFIC = "scientific"
    TECHNICAL_DEEP_DIVE = "technical_deep_dive"
    TOPIC_EXPLAINER = "topic_explainer"
    INTERVIEW = "interview"
    NEWS_BRIEFING = "news_briefing"
    CASUAL_CHAT = "casual_chat"
    DEBATE = "debate"
    STORYTELLING = "storytelling"


class AudienceLevel(str, Enum):
    """Target audience sophistication level."""
    GENERAL = "general"
    TECHNICAL = "technical"
    EXPERT = "expert"
    EXECUTIVE = "executive"


class PodcastLength(str, Enum):
    """Target podcast duration."""
    SHORT = "short"        # ~2-3 min  → ~400-600 words
    MEDIUM = "medium"      # ~5-8 min  → ~1000-1600 words
    LONG = "long"          # ~12-18 min → ~2400-3600 words


class GeminiVoice(str, Enum):
    """Available Gemini TTS prebuilt voices (gender, character)."""
    # Male voices
    PUCK = "Puck"          # Male — conversational, friendly
    CHARON = "Charon"      # Male — deep, authoritative
    FENRIR = "Fenrir"      # Male — energetic, dynamic
    ORUS = "Orus"          # Male — calm, measured
    # Female voices
    KORE = "Kore"          # Female — neutral, professional
    AOEDE = "Aoede"        # Female — warm, melodic
    LEDA = "Leda"          # Female — clear, articulate
    ZEPHYR = "Zephyr"      # Female — light, upbeat


class SpeakerMode(str, Enum):
    """Single or multi-speaker podcast."""
    SINGLE = "single"
    MULTI = "multi"


class AuthMode(str, Enum):
    """How to authenticate with the Gemini API."""
    QUERY_PARAM = "query_param"   # Direct Gemini API: ?key=...
    HEADER = "header"             # Azure AI Gateway: x-api-key header
    AUTO = "auto"                 # Auto-detect based on base URL


# ---------------------------------------------------------------------------
# Word-count targets per length
# ---------------------------------------------------------------------------

LENGTH_WORD_TARGETS: dict[PodcastLength, tuple[int, int]] = {
    PodcastLength.SHORT: (400, 600),
    PodcastLength.MEDIUM: (1000, 1600),
    PodcastLength.LONG: (2400, 3600),
}

# ---------------------------------------------------------------------------
# Turn-count guidance per length (for multi-speaker)
# ---------------------------------------------------------------------------

LENGTH_TURN_TARGETS: dict[PodcastLength, tuple[int, int]] = {
    PodcastLength.SHORT: (8, 14),
    PodcastLength.MEDIUM: (18, 30),
    PodcastLength.LONG: (35, 60),
}


# ---------------------------------------------------------------------------
# Settings (loaded from env / .env)
# ---------------------------------------------------------------------------

class PodcastSettings(BaseSettings):
    """Server-wide settings loaded from environment variables."""

    model_config = ConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Gemini API access (via Azure AI Gateway or direct) ---
    gemini_base_url: str = Field(
        default="https://generativelanguage.googleapis.com/v1beta",
        description="Base URL for Gemini API (your Azure AI Gateway URL)",
    )
    gemini_api_key: str = Field(
        default="",
        description="API key for Gemini (your gateway access key)",
    )
    gemini_auth_mode: AuthMode = Field(
        default=AuthMode.AUTO,
        description=(
            "Auth mode: 'query_param' for direct Gemini API (?key=...), "
            "'header' for Azure AI Gateway (x-api-key header), "
            "'auto' to detect from base URL (googleapis.com → query_param, else header)."
        ),
    )

    # --- LLM model for transcript generation ---
    gemini_transcript_model: str = Field(
        default="gemini-2.5-flash",
        description=(
            "Gemini model for transcript generation. Options: "
            "'gemini-3.1-pro-preview' (best quality — top reasoning & creativity), "
            "'gemini-2.5-pro' (excellent quality), "
            "'gemini-2.5-flash' (fast & cheap, good default)."
        ),
    )

    # --- TTS model for audio synthesis ---
    gemini_tts_model: str = Field(
        default="gemini-2.5-pro-preview-tts",
        description=(
            "Gemini TTS model for audio synthesis. Options: "
            "'gemini-2.5-pro-preview-tts' (higher quality, better for podcasts) or "
            "'gemini-2.5-flash-preview-tts' (faster, cheaper, good for drafts)."
        ),
    )

    # --- Show defaults ---
    podcast_show_name: str = Field(
        default="My Podcast",
        description="Default podcast show name (set to your show via PODCAST_SHOW_NAME env var)",
    )
    podcast_host_name: str = Field(
        default="Host",
        description="Default host speaker name",
    )
    podcast_guest_name: str = Field(
        default="Guest",
        description="Default guest speaker name",
    )

    # --- Voice defaults ---
    podcast_host_voice: GeminiVoice = Field(
        default=GeminiVoice.KORE,
        description="Default voice for the host",
    )
    podcast_guest_voice: GeminiVoice = Field(
        default=GeminiVoice.PUCK,
        description="Default voice for the guest",
    )

    # --- Style defaults ---
    podcast_default_style: PodcastStyle = Field(
        default=PodcastStyle.TOPIC_EXPLAINER,
        description="Default podcast editorial style",
    )
    podcast_default_audience: AudienceLevel = Field(
        default=AudienceLevel.TECHNICAL,
        description="Default target audience",
    )
    podcast_default_length: PodcastLength = Field(
        default=PodcastLength.MEDIUM,
        description="Default podcast length",
    )

    # --- Audio output ---
    audio_output_dir: str = Field(
        default="./podcast_output",
        description="Directory for generated audio files",
    )
    audio_sample_rate: int = Field(
        default=24000,
        description="Audio sample rate in Hz",
    )

    def get_auth(self) -> tuple[dict[str, str], dict[str, str]]:
        """Return (headers, query_params) for Gemini API authentication.

        Auto-detect logic:
        - If base URL contains 'googleapis.com' → use ?key= query param (direct Gemini)
        - Otherwise → use x-api-key header (Azure AI Gateway / proxy)
        """
        headers: dict[str, str] = {"Content-Type": "application/json"}
        params: dict[str, str] = {}

        if not self.gemini_api_key:
            return headers, params

        mode = self.gemini_auth_mode
        if mode == AuthMode.AUTO:
            if "googleapis.com" in self.gemini_base_url:
                mode = AuthMode.QUERY_PARAM
            else:
                mode = AuthMode.HEADER

        if mode == AuthMode.QUERY_PARAM:
            params["key"] = self.gemini_api_key
        else:
            headers["x-api-key"] = self.gemini_api_key
            # Some gateways also accept Authorization: Bearer
            headers["Authorization"] = f"Bearer {self.gemini_api_key}"

        return headers, params


# Singleton – import and use throughout the package
_settings: Optional[PodcastSettings] = None


def get_settings() -> PodcastSettings:
    """Return the cached settings singleton."""
    global _settings
    if _settings is None:
        _settings = PodcastSettings()
    return _settings
