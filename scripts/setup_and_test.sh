#!/bin/bash
# AIXplore Podcast Generator — Setup & Test
# Run this from the podcast-mcp directory:
#   chmod +x setup_and_test.sh
#   ./setup_and_test.sh

set -e

echo "🎙️  AIXplore Podcast Generator — Setup"
echo "========================================"

# Prefer uv for faster installs
if command -v uv &>/dev/null; then
    echo "Using uv (fast mode)..."
    uv pip install -e . --quiet
else
    echo "uv not found, falling back to pip..."
    # Create virtual environment if it doesn't exist
    if [ ! -d ".venv" ]; then
        echo "Creating virtual environment..."
        python3 -m venv .venv
    fi
    source .venv/bin/activate
    pip install -e . --quiet
fi

# Check for API key
if [ -z "$GEMINI_API_KEY" ]; then
    echo ""
    echo "❌ GEMINI_API_KEY not set."
    echo "   Run: export GEMINI_API_KEY=\"your-key-here\""
    echo "   Then re-run this script."
    exit 1
fi

echo ""
echo "Running end-to-end test..."
echo ""
python test_e2e.py
