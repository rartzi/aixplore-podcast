---
name: podcast
description: >-
  Generate podcast audio from documents, text, or any content using Gemini AI.
  Two-phase pipeline: transcript generation then TTS audio synthesis, exposed as
  MCP tools. Use this skill whenever the user wants to create a podcast, generate
  audio from a document, turn content into a conversation, make an episode, create
  a briefing, or convert text/PDF/markdown into spoken audio. Also use when the user
  mentions podcast styles (scientific, debate, casual chat, interview, news briefing),
  voice selection, or speaker configuration. Triggers on: "create a podcast",
  "make an episode", "turn this into audio", "generate a podcast from",
  "podcast from this PDF", "news briefing", "single speaker", "multi speaker",
  "synthesize audio", "generate transcript".
---

# Podcast Generator

Transform any content into natural-sounding podcast audio via three MCP tools.

## Tool Selection

Choose the right tool based on what the user needs:

| User Intent | Tool | Why |
|-------------|------|-----|
| Quick end-to-end: "create a podcast from this" | `podcast_create` | One call, content → audio |
| Wants to review/edit before audio | `podcast_generate_transcript` first, then `podcast_synthesize_audio` | Two-step gives control |
| Already has a transcript (or edited one) | `podcast_synthesize_audio` | Skip generation, go straight to audio |
| Just wants the script, no audio yet | `podcast_generate_transcript` | Returns JSON + markdown preview |

## Tools

### `podcast_create` — End-to-End

Content → transcript → audio in one call. Use when the user just wants a podcast without reviewing the transcript.

**Key parameters:**
- `content` (string) OR `file_path` (string) — source material (one required)
- `style` — editorial format (default: `topic_explainer`)
- `audience` — depth level (default: `technical`)
- `length` — `short` (~2-3min), `medium` (~5-8min), `long` (~12-18min)
- `speaker_mode` — `single` (monologue) or `multi` (conversation, default)
- `host_name`, `guest_name` — speaker names
- `host_voice`, `guest_voice` — Gemini voice selection
- `output_path` — where to save the WAV file

### `podcast_generate_transcript`

Generate a dialogue transcript only. Returns JSON array of `{speaker, line}` turns plus a markdown preview. Use this when the user wants to review or edit before synthesis.

Same parameters as `podcast_create` except no voice/output_path params.

### `podcast_synthesize_audio`

Convert a transcript to WAV audio. Takes the JSON output from `podcast_generate_transcript`.

**Key parameters:**
- `transcript` (required) — array of `{speaker, line}` objects
- `speaker_mode`, `host_name`, `guest_name` — must match transcript
- `host_voice`, `guest_voice` — voice selection
- `output_path` — where to save the WAV

## Styles

| Style | When to Use |
|-------|-------------|
| `scientific` | Research papers, studies — methodology-focused |
| `technical_deep_dive` | Architecture, implementation — practitioner talk |
| `topic_explainer` | Making complex topics accessible — default choice |
| `interview` | Personal experiences, opinions — conversational |
| `news_briefing` | Recent developments — concise and brisk |
| `casual_chat` | Light, fun — two friends over coffee |
| `debate` | Contrasting perspectives — balanced arguments |
| `storytelling` | Narrative arc — setup, tension, resolution |

## Audience Levels

| Level | Effect |
|-------|--------|
| `general` | No jargon, everyday analogies |
| `technical` | Industry terms OK, focuses on how/why |
| `expert` | Skips basics, nuance and trade-offs |
| `executive` | Strategic framing, ROI, actionable insights |

## Voices

### Male
| Voice | Character | Best For |
|-------|-----------|----------|
| `Puck` | Friendly, conversational | Casual host, explainer |
| `Charon` | Deep, authoritative | Scientific expert, news anchor |
| `Fenrir` | Energetic, dynamic | Tech deep-dive, storytelling |
| `Orus` | Calm, measured | Executive briefing, debate |

### Female
| Voice | Character | Best For |
|-------|-----------|----------|
| `Kore` | Professional, neutral | News host, technical lead |
| `Aoede` | Warm, melodic | Interview host, storytelling |
| `Leda` | Clear, articulate | Scientific, executive |
| `Zephyr` | Light, upbeat | Casual chat, explainer |

### Recommended Pairings
- **Scientific**: Kore (host) + Charon (guest) — professional meets authoritative
- **Technical deep-dive**: Kore + Puck — professional lead, friendly practitioner
- **Casual chat**: Zephyr + Puck — upbeat energy, friendly banter
- **Debate**: Leda + Charon — clear moderator, authoritative debater
- **News briefing**: Kore + Orus — professional anchor, measured analyst

## Tips for Best Results

- **Contrast voices**: pair different energy levels (calm host + energetic guest)
- **Single speaker**: use `Charon` for authoritative monologues, `Aoede` for warm narration
- **Long content**: consider `podcast_generate_transcript` first so the user can trim the transcript before paying for TTS
- **Choppy audio**: TTS chunks at ~1500 chars — shorter content or manual transcript editing helps
- **File types**: supports `.pdf`, `.md`, `.txt`, `.html`, `.rst`
