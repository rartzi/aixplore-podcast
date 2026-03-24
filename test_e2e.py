#!/usr/bin/env python3
"""End-to-end test for the AIXplore Podcast Generator.

Usage:
    export GEMINI_API_KEY="your-key-here"

    # Defaults (multi-speaker, topic_explainer, technical, short)
    python test_e2e.py

    # Custom style & length
    python test_e2e.py --style scientific --length medium

    # Single speaker monologue
    python test_e2e.py --mode single --style news_briefing --length short

    # Full customization
    python test_e2e.py --style debate --audience expert --length long \
        --host "Ronen" --guest "Dr. Smith" \
        --host-voice Charon --guest-voice Aoede \
        --show "AIXplore Deep Dive"

    # Use your own content file
    python test_e2e.py --file /path/to/document.pdf --style technical_deep_dive

    # Skip audio (transcript only)
    python test_e2e.py --transcript-only

    # Use Flash TTS (faster, cheaper) instead of Pro
    python test_e2e.py --tts-model gemini-2.5-flash-preview-tts

Available options:
    --style       scientific | technical_deep_dive | topic_explainer | interview |
                  news_briefing | casual_chat | debate | storytelling
    --audience    general | technical | expert | executive
    --length      short (~2-3min) | medium (~5-8min) | long (~12-18min)
    --mode        single | multi
    --host        Host speaker name
    --guest       Guest speaker name
    --host-voice  Puck | Charon | Kore | Fenrir | Aoede | Leda | Orus | Zephyr
    --guest-voice Same options as --host-voice
    --show        Podcast show name
    --file        Path to input file (.pdf, .md, .txt) instead of sample content
    --tts-model   TTS model override
    --output      Output WAV filename (default: test_podcast.wav)
    --transcript-only  Generate transcript without audio
"""

import argparse
import asyncio
import json
import os
import sys
import time

# Ensure the package is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from podcast_mcp.config import (
    PodcastSettings,
    PodcastStyle,
    AudienceLevel,
    PodcastLength,
    SpeakerMode,
    GeminiVoice,
)
from podcast_mcp.content import extract_content, truncate_content
from podcast_mcp.transcript import generate_transcript, format_transcript_markdown
from podcast_mcp.audio import synthesize_audio


SAMPLE_CONTENT = """
Retrieval-Augmented Generation (RAG) is a technique that combines the strengths
of large language models with external knowledge retrieval. Instead of relying
solely on the knowledge encoded in model weights during training, RAG systems
retrieve relevant documents from a knowledge base at inference time and use them
to ground the model's responses in factual, up-to-date information.

The key components of a RAG pipeline are:
1. Document ingestion and chunking — splitting source documents into manageable pieces
2. Embedding generation — converting chunks into vector representations
3. Vector store indexing — storing embeddings for fast similarity search
4. Query processing — embedding the user query and finding relevant chunks
5. Context augmentation — injecting retrieved chunks into the LLM prompt
6. Response generation — the LLM generates a grounded answer

RAG addresses several critical limitations of standalone LLMs: hallucination
(generating plausible but incorrect information), knowledge staleness (training
data cutoff), and lack of domain specificity. By grounding responses in retrieved
evidence, RAG systems can provide more accurate, verifiable, and current answers.

Recent advances include multi-hop RAG (iterative retrieval for complex questions),
hybrid search (combining dense and sparse retrieval for better recall), and
agentic RAG (where the LLM autonomously decides when and what to retrieve).
GraphRAG extends this further by building knowledge graphs from documents,
enabling reasoning over entity relationships rather than just text similarity.
"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="AIXplore Podcast Generator — End-to-End Test",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    # Content source
    parser.add_argument(
        "--file", "-f",
        help="Path to input file (.pdf, .md, .txt). Uses sample RAG content if not provided.",
    )

    # Podcast style
    parser.add_argument(
        "--style", "-s",
        choices=[s.value for s in PodcastStyle],
        default="topic_explainer",
        help="Podcast editorial style (default: topic_explainer)",
    )
    parser.add_argument(
        "--audience", "-a",
        choices=[a.value for a in AudienceLevel],
        default="technical",
        help="Target audience level (default: technical)",
    )
    parser.add_argument(
        "--length", "-l",
        choices=[l.value for l in PodcastLength],
        default="short",
        help="Target duration (default: short)",
    )
    parser.add_argument(
        "--mode", "-m",
        choices=[m.value for m in SpeakerMode],
        default="multi",
        help="Speaker mode: single (monologue) or multi (conversation) (default: multi)",
    )

    # Speaker config
    parser.add_argument("--show", default="AIXplore", help="Podcast show name (default: AIXplore)")
    parser.add_argument("--host", default="Alex", help="Host speaker name (default: Alex)")
    parser.add_argument("--guest", default="Dr. Chen", help="Guest speaker name (default: Dr. Chen)")

    # Voice config
    parser.add_argument(
        "--host-voice",
        choices=[v.value for v in GeminiVoice],
        default="Kore",
        help="Host voice (default: Kore — professional)",
    )
    parser.add_argument(
        "--guest-voice",
        choices=[v.value for v in GeminiVoice],
        default="Puck",
        help="Guest voice (default: Puck — friendly)",
    )

    # Model overrides
    parser.add_argument(
        "--transcript-model",
        default=None,
        help=(
            "Transcript generation model. Options: "
            "gemini-3.1-pro-preview (best quality), "
            "gemini-2.5-pro (excellent), "
            "gemini-2.5-flash (fast, default)"
        ),
    )
    parser.add_argument(
        "--tts-model",
        default=None,
        help=(
            "TTS model. Options: "
            "gemini-2.5-pro-preview-tts (best quality, default), "
            "gemini-2.5-flash-preview-tts (faster)"
        ),
    )

    # Output
    parser.add_argument("--output", "-o", default="test_podcast.wav", help="Output WAV filename")
    parser.add_argument("--transcript-only", action="store_true", help="Generate transcript only, skip audio")

    return parser.parse_args()


async def run(args: argparse.Namespace):
    api_key = os.environ.get("GEMINI_API_KEY", "")
    base_url = os.environ.get(
        "GEMINI_BASE_URL",
        "https://generativelanguage.googleapis.com/v1beta",
    )

    if not api_key:
        print("❌ GEMINI_API_KEY not set. Export it and try again.")
        sys.exit(1)

    # Build settings
    settings_kwargs = dict(
        gemini_api_key=api_key,
        gemini_base_url=base_url,
        podcast_show_name=args.show,
        podcast_host_name=args.host,
        podcast_guest_name=args.guest,
        audio_output_dir=".",
    )
    if args.transcript_model:
        settings_kwargs["gemini_transcript_model"] = args.transcript_model
    if args.tts_model:
        settings_kwargs["gemini_tts_model"] = args.tts_model

    settings = PodcastSettings(**settings_kwargs)

    style = PodcastStyle(args.style)
    audience = AudienceLevel(args.audience)
    length = PodcastLength(args.length)
    speaker_mode = SpeakerMode(args.mode)
    host_voice = GeminiVoice(args.host_voice)
    guest_voice = GeminiVoice(args.guest_voice)

    # Header
    print()
    print("🎙️  AIXplore Podcast Generator")
    print("=" * 60)
    print(f"  Show:       {args.show}")
    print(f"  Style:      {style.value}")
    print(f"  Audience:   {audience.value}")
    print(f"  Length:     {length.value}")
    print(f"  Mode:       {speaker_mode.value}")
    if speaker_mode == SpeakerMode.MULTI:
        print(f"  Host:       {args.host} (voice: {host_voice.value})")
        print(f"  Guest:      {args.guest} (voice: {guest_voice.value})")
    else:
        print(f"  Speaker:    {args.host} (voice: {host_voice.value})")
    print(f"  TTS Model:  {settings.gemini_tts_model}")
    auth_headers, auth_params = settings.get_auth()
    print(f"  Auth:       {'query_param' if auth_params else 'header'}")

    # Load content
    if args.file:
        print(f"  Input:      {args.file}")
        content = truncate_content(extract_content(args.file))
    else:
        print("  Input:      [built-in RAG sample]")
        content = SAMPLE_CONTENT

    print("=" * 60)

    # ── Phase 1: Transcript ──────────────────────────────────
    print("\n📝 PHASE 1: Generating Transcript...")
    start = time.time()

    try:
        dialogue = await generate_transcript(
            content,
            style=style,
            audience=audience,
            length=length,
            speaker_mode=speaker_mode,
            show_name=args.show,
            host_name=args.host,
            guest_name=args.guest,
            settings=settings,
        )
    except Exception as e:
        print(f"\n❌ Transcript generation failed: {e}")
        sys.exit(1)

    elapsed = time.time() - start
    word_count = sum(len(t["line"].split()) for t in dialogue)

    print(f"\n✅ Transcript: {len(dialogue)} turns, ~{word_count} words ({elapsed:.1f}s)\n")
    print(format_transcript_markdown(dialogue))

    # Save transcript
    transcript_file = args.output.replace(".wav", "_transcript.json")
    with open(transcript_file, "w") as f:
        json.dump(dialogue, f, indent=2, ensure_ascii=False)
    print(f"💾 Saved: {transcript_file}")

    if args.transcript_only:
        print("\n🏁 Done (--transcript-only mode, skipping audio)")
        return

    # ── Phase 2: Audio Synthesis ─────────────────────────────
    print("\n🔊 PHASE 2: Synthesizing Audio...")

    from podcast_mcp.audio import _chunk_dialogue
    chunks = _chunk_dialogue(dialogue)
    total_chars = sum(len(f"{t['speaker']}: {t['line']}") for t in dialogue)
    print(f"   {len(dialogue)} turns, ~{total_chars} chars → {len(chunks)} chunk(s)")
    print()

    start = time.time()

    try:
        audio_path = await synthesize_audio(
            dialogue,
            speaker_mode=speaker_mode,
            host_name=args.host,
            guest_name=args.guest,
            host_voice=host_voice,
            guest_voice=guest_voice,
            output_path=args.output,
            settings=settings,
        )
    except Exception as e:
        print(f"\n❌ Audio synthesis failed: {e}")
        print("   Transcript was saved — see", transcript_file)
        sys.exit(1)

    elapsed = time.time() - start
    file_size = os.path.getsize(audio_path)
    duration_est = file_size / (48_000 * 60)

    print(f"\n✅ Audio: {audio_path}")
    print(f"   Size: {file_size / 1_048_576:.2f} MB | Est. duration: {duration_est:.1f} min | Generated in {elapsed:.1f}s")

    # ── Done ─────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("🎉 Done!")
    print(f"   📝 Transcript: {transcript_file}")
    print(f"   🔊 Audio:      {audio_path}")
    print("=" * 60)


if __name__ == "__main__":
    args = parse_args()
    asyncio.run(run(args))
