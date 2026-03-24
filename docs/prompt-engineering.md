# Prompt Engineering Playbook

How the transcript generation prompts are structured and why.

## System Prompt Architecture

The system prompt is assembled from four layers:

1. **Core role** — Sets the podcast scriptwriter identity and show name
2. **Style prompt** — Genre-specific guidance (from `STYLE_PROMPTS` dict)
3. **Audience prompt** — Vocabulary and depth calibration (from `AUDIENCE_PROMPTS` dict)
4. **Dialogue quality rules** — Universal pacing and format rules
5. **Output format** — JSON schema instructions

These layers compose — style defines *what kind* of conversation, audience defines *how* to express it.

## Style Prompts — Design Rationale

Each style encodes specific conversational patterns that Gemini produces well:

| Style | Key Design Choices |
|-------|-------------------|
| **scientific** | Host asks probing questions; guest explains with analogies and cites findings naturally. Uses "what the data actually shows" and "here's what surprised us" to build credibility. |
| **technical_deep_dive** | Host guides through architecture decisions. Guest shares war stories and lessons learned. Uses "under the hood", "the gotcha here is" — practitioner-to-practitioner language. |
| **topic_explainer** | Host is the curious learner asking "why" and "how". Guest builds understanding progressively — starts simple, adds layers. Heavy on analogies and "imagine if" scenarios. |
| **interview** | Open-ended questions, personal experiences, humor. The goal is letting the guest's personality come through. |
| **news_briefing** | Brisk pace, key-points-first structure. Uses "the key takeaway here" and "what this means going forward." Concise analysis over deep exploration. |
| **casual_chat** | Natural tangents that circle back, light humor, speakers building on each other's ideas. "Two smart friends chatting over coffee" vibe. |
| **debate** | Respectful pushback, steel-manning opposing views, areas of consensus. Host moderates balance. |
| **storytelling** | Narrative arc — setup, rising tension, climax, resolution. Uses vivid language, pacing variations, and cliffhangers. |

## Audience Adaptation

The audience layer modifies how deeply and technically the style prompt is expressed:

| Audience | Effect on Output |
|----------|-----------------|
| **general** | No jargon. Every concept explained from first principles. Everyday analogies. |
| **technical** | Industry terms are okay but niche terms get brief definitions. Focus on how and why. |
| **expert** | Basics are skipped. Nuance, trade-offs, and cutting-edge details dominate. |
| **executive** | Strategic framing — ROI, competitive landscape, actionable insights. Minimal technical detail. |

**Style × Audience interaction example:**
- `scientific` + `general` = "Imagine your immune system as a well-organized army..."
- `scientific` + `expert` = "The CRISPR-Cas9 off-target binding rates in the Zhang et al. study suggest..."

## Dialogue Quality Rules

Applied universally to all styles. These were empirically tuned for natural-sounding Gemini output:

- **Turn length:** 1–4 sentences per turn. Avoids monologues.
- **Conversational markers:** "Right", "Exactly", "That's a great point", "So what you're saying is..." — these make dialogue sound human rather than scripted.
- **Rhythm variation:** Mix short punchy exchanges with longer explanatory turns.
- **Segment transitions:** "Let's shift gears", "Speaking of which", "Now here's the really interesting part"
- **No stage directions:** Never include `[laughs]`, `[pause]`, or `(sound effect)` — TTS models render these literally.
- **Hook opening:** First 10 seconds must grab attention.
- **Clear wrap-up:** End with a forward-looking takeaway.

## Generation Parameters

| Parameter | Value | Reason |
|-----------|-------|--------|
| `temperature` | 1.0 | High creativity for natural-sounding, varied dialogue |
| `topP` | 0.95 | Diverse word choice while avoiding incoherence |
| `maxOutputTokens` | 8192 | Enough for LONG podcasts (~3600 words) |
| `responseMimeType` | `application/json` | Forces structured output |
| `responseSchema` | `[{speaker, line}]` | Validates array of dialogue turns |

**Why temperature 1.0?** Lower temperatures produce dialogue that sounds robotic and repetitive. At 1.0, Gemini varies sentence structure, uses more natural filler, and produces better conversational flow. The JSON schema constraint prevents the high temperature from causing structural issues.

## Length Calibration

| Length | Word Target | Turn Target | Approx. Duration |
|--------|------------|-------------|-------------------|
| SHORT | 400–600 | 8–14 | ~2–3 minutes |
| MEDIUM | 1,000–1,600 | 18–30 | ~5–8 minutes |
| LONG | 2,400–3,600 | 35–60 | ~12–18 minutes |

These targets are embedded in the system prompt as explicit guidance. The word-to-duration ratio assumes ~200 words/minute spoken at conversational pace.

## Extending with New Styles

To add a new podcast style:

1. Add the enum value in `config.py` → `PodcastStyle`
2. Add the prompt fragment in `transcript.py` → `STYLE_PROMPTS` dict
3. Update docs (this file, README, SKILL.md voice tables)

The prompt fragment should specify:
- Who the speakers are (roles, expertise, relationship)
- Conversational tone and markers specific to the genre
- What "good" looks like for this style (specific phrases, pacing notes)
- What to avoid (common failure modes for the genre)
