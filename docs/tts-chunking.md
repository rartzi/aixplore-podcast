# TTS Chunking & Audio Pipeline

How long transcripts are split, synthesized, and reassembled.

## Why Chunking?

Gemini's preview TTS models (`*-preview-tts`) disconnect or produce corrupted audio on large payloads. The chunking strategy keeps each API call small enough for reliable output.

## Chunk Size

**MAX_TTS_CHARS = 1,500 characters** per chunk.

This is a stability heuristic, not an API-documented limit. It was chosen empirically:
- 1,500 chars ≈ 3–5 dialogue turns
- Larger payloads (3,000+) frequently cause disconnects with preview models
- Production models (when released) may support larger payloads — revisit this limit

## Splitting Rules

1. **Never split mid-turn** — chunks break only at speaker turn boundaries
2. **Single oversized turn** — if one turn exceeds 1,500 chars, it gets its own chunk (no truncation)
3. **Greedy packing** — turns are added to the current chunk until adding the next would exceed the limit

## Audio Concatenation

After all chunks are synthesized:

1. Each chunk returns either WAV (with headers) or raw PCM bytes
2. PCM is extracted from each segment (WAV headers stripped if present)
3. All PCM frames are concatenated in order
4. A single WAV header is written around the combined PCM data

**Assumed audio format:**
- Sample rate: 24,000 Hz
- Channels: 1 (mono)
- Sample width: 2 bytes (16-bit signed)

If the API returns WAV, the actual parameters are read from the WAV header. If raw PCM, the defaults above are assumed.

## Rate Limiting

A 2-second pause is inserted between chunk API calls to avoid triggering Gemini's rate limiter (HTTP 429).

## Chunk Boundary Artifacts

When chunks are concatenated, there may be audible seams at boundaries — slight pauses, pitch shifts, or volume changes. This is inherent to chunked TTS. Mitigation strategies:

- Keep chunks larger (fewer seams) — trade-off with reliability
- Use shorter content or edit transcripts to reduce total length
- Use the two-step workflow: generate transcript → manually edit → synthesize

## Sequence Diagram

```
Dialogue (20 turns)
    │
    ├──► Chunk 1 (turns 1-4, ~1200 chars) ──► TTS API ──► audio bytes
    │                                                          │
    ├──► Chunk 2 (turns 5-9, ~1400 chars) ──► TTS API ──► audio bytes
    │                                                          │
    ├──► Chunk 3 (turns 10-14, ~1100 chars) ──► TTS API ──► audio bytes
    │                                                          │
    ├──► Chunk 4 (turns 15-20, ~1300 chars) ──► TTS API ──► audio bytes
    │                                                          │
    └──► Concatenate all segments ──► Write final WAV file
```

Chunks are processed sequentially (not parallel) to respect rate limits.
