# Gemini API Integration Reference

How this server interacts with the Gemini API. Keep this updated as the API evolves.

## Endpoints

Both transcript generation and TTS use the same endpoint pattern:

```
{GEMINI_BASE_URL}/models/{model_name}:generateContent
```

- Transcript: `gemini-2.5-flash`, `gemini-2.5-pro`, `gemini-3.1-pro-preview`
- TTS: `gemini-2.5-pro-preview-tts`, `gemini-2.5-flash-preview-tts`

## Authentication

Three modes, configured via `GEMINI_AUTH_MODE` (default: `auto`):

| Mode | When | How |
|------|------|-----|
| `query_param` | Direct Google API (`googleapis.com`) | `?key={GEMINI_API_KEY}` query parameter |
| `header` | Azure AI Gateway / proxies | Both `x-api-key` and `Authorization: Bearer` headers sent (some gateways expect one or the other) |
| `auto` | Default | Detects from base URL — `googleapis.com` → query_param, else → header |

## Transcript Generation Request

```json
{
  "contents": [{"role": "user", "parts": [{"text": "user prompt"}]}],
  "systemInstruction": {"parts": [{"text": "system prompt"}]},
  "generationConfig": {
    "temperature": 1.0,
    "topP": 0.95,
    "maxOutputTokens": 8192,
    "responseMimeType": "application/json",
    "responseSchema": { "type": "array", "items": { ... } }
  }
}
```

**Key parameters:**
- `temperature: 1.0` — High for creative, natural-sounding dialogue
- `topP: 0.95` — Allows diverse word choice
- `maxOutputTokens: 8192` — Limits dialogue length (sufficient for ~3600 words)
- `responseMimeType: "application/json"` + `responseSchema` — Forces structured JSON output

**Response parsing:**
```
result["candidates"][0]["content"]["parts"][0]["text"]  →  JSON string  →  parse to list
```

The response `text` field contains a JSON **string** (not a parsed object). Must `json.loads()` it.

## TTS Request — Single Speaker

```json
{
  "contents": [{"parts": [{"text": "dialogue text"}]}],
  "generationConfig": {
    "responseModalities": ["AUDIO"],
    "speechConfig": {
      "voiceConfig": {
        "prebuiltVoiceConfig": {"voiceName": "Kore"}
      }
    }
  }
}
```

## TTS Request — Multi Speaker

```json
{
  "contents": [{"parts": [{"text": "TTS the following conversation between Host and Guest:\n\nHost: line\nGuest: line"}]}],
  "generationConfig": {
    "responseModalities": ["AUDIO"],
    "speechConfig": {
      "multiSpeakerVoiceConfig": {
        "speakerVoiceConfigs": [
          {"speaker": "Host", "voiceConfig": {"prebuiltVoiceConfig": {"voiceName": "Kore"}}},
          {"speaker": "Guest", "voiceConfig": {"prebuiltVoiceConfig": {"voiceName": "Puck"}}}
        ]
      }
    }
  }
}
```

**Critical:** The text content must use the format `"Speaker Name: dialogue text"` on each line. Speaker names in the text must exactly match the `speaker` field in `speakerVoiceConfigs`. Case-sensitive, colon-space delimited.

The prompt prefix `"TTS the following conversation between {host} and {guest}:"` is a workaround — the API doesn't natively parse speaker names; it learns them from context.

## TTS Response

```
result["candidates"][0]["content"]["parts"][*]["inlineData"]["data"]  →  base64 audio
result["candidates"][0]["content"]["parts"][*]["inlineData"]["mimeType"]  →  audio type
```

Audio is returned as base64-encoded data in the `inlineData` field. Iterate through `parts` to find entries with `inlineData`. The audio is either WAV (with headers) or raw PCM.

**Audio parameters (current):**
- Sample rate: 24,000 Hz
- Channels: 1 (mono)
- Sample width: 2 bytes (16-bit)
- Approximate data rate: ~48 KB/sec

## Retry Behavior

Preview TTS models are flaky. The server retries on:

| Condition | Retries | Backoff |
|-----------|---------|---------|
| Connection errors (ConnectError, RemoteProtocolError, timeouts) | 3 | 5s, 10s, 20s |
| HTTP 429 (rate limited) | 3 | 5s, 10s, 20s |
| HTTP 503 (overloaded) | 3 | 5s, 10s, 20s |
| Other HTTP errors (4xx) | 0 | Fail immediately |

## Known Fragile Assumptions

These are API behaviors we depend on that aren't guaranteed by a versioned contract:

1. URL pattern: `/models/{model}:generateContent`
2. Response path: `candidates[0].content.parts[0].text` for transcript
3. Response path: `candidates[0].content.parts[*].inlineData` for audio
4. Audio encoding: 24kHz, mono, 16-bit PCM
5. Multi-speaker speaker name matching via text pattern
6. Voice names: Puck, Charon, Kore, Fenrir, Aoede, Leda, Orus, Zephyr
