#!/usr/bin/env python3
"""Check which Gemini models are available with your API key.

Usage:
    export GEMINI_API_KEY="your-key"
    python check_models.py
"""

import os
import sys
import json

try:
    import httpx
except ImportError:
    print("httpx not installed. Run: pip install httpx")
    sys.exit(1)

API_KEY = os.environ.get("GEMINI_API_KEY", "")
BASE_URL = os.environ.get("GEMINI_BASE_URL", "https://generativelanguage.googleapis.com/v1beta")

if not API_KEY:
    print("Set GEMINI_API_KEY first")
    sys.exit(1)

print(f"Base URL: {BASE_URL}")
print(f"API Key: {API_KEY[:10]}...")
print()

# List all models
print("=" * 60)
print("Fetching available models...")
print("=" * 60)

try:
    r = httpx.get(f"{BASE_URL}/models", params={"key": API_KEY}, timeout=30)
    r.raise_for_status()
    data = r.json()
except Exception as e:
    print(f"Error listing models: {e}")
    sys.exit(1)

models = data.get("models", [])
print(f"Found {len(models)} models\n")

# Filter for TTS models
tts_models = [m for m in models if "tts" in m.get("name", "").lower()]
audio_models = [m for m in models if "audio" in m.get("name", "").lower() or "audio" in str(m.get("supportedGenerationMethods", [])).lower()]

print("--- TTS Models ---")
if tts_models:
    for m in tts_models:
        name = m.get("name", "")
        display = m.get("displayName", "")
        methods = m.get("supportedGenerationMethods", [])
        print(f"  {name}")
        print(f"    Display: {display}")
        print(f"    Methods: {methods}")
        print()
else:
    print("  None found with 'tts' in name")
    print()

print("--- All models with 'generateContent' support ---")
gc_models = [m for m in models if "generateContent" in m.get("supportedGenerationMethods", [])]
for m in gc_models:
    name = m.get("name", "")
    display = m.get("displayName", "")
    # Only show models that might be relevant
    if any(kw in name.lower() for kw in ["flash", "pro", "tts", "audio", "2.5", "2-5"]):
        print(f"  {name} — {display}")

print()
print("--- Quick TTS test with each TTS model ---")
for m in tts_models:
    model_name = m["name"].replace("models/", "")
    print(f"\nTesting {model_name}...")

    body = {
        "contents": [{"parts": [{"text": "Hello, this is a test."}]}],
        "generationConfig": {
            "responseModalities": ["AUDIO"],
            "speechConfig": {
                "voiceConfig": {
                    "prebuiltVoiceConfig": {
                        "voiceName": "Kore"
                    }
                }
            }
        }
    }

    try:
        url = f"{BASE_URL}/models/{model_name}:generateContent"
        r = httpx.post(url, json=body, params={"key": API_KEY}, timeout=60)
        if r.status_code == 200:
            result = r.json()
            parts = result.get("candidates", [{}])[0].get("content", {}).get("parts", [])
            has_audio = any("inlineData" in p for p in parts)
            print(f"  ✅ Status 200 | Has audio: {has_audio}")
            if has_audio:
                for p in parts:
                    if "inlineData" in p:
                        data_len = len(p["inlineData"].get("data", ""))
                        mime = p["inlineData"].get("mimeType", "unknown")
                        print(f"     Audio: {mime}, base64 length={data_len}")
        else:
            error_msg = r.text[:200]
            print(f"  ❌ Status {r.status_code}: {error_msg}")
    except Exception as e:
        print(f"  ❌ Error: {e}")
