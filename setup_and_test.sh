#!/bin/bash
# AIXplore Podcast Generator — Setup & Test
# Run this from the podcast-mcp directory:
#   chmod +x setup_and_test.sh
#   ./setup_and_test.sh

set -e

echo "🎙️  AIXplore Podcast Generator — Setup"
echo "========================================"

# Create virtual environment if it doesn't exist
if [ ! -d ".venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv .venv
fi

# Activate it
source .venv/bin/activate

# Install the package
echo "Installing dependencies..."
pip install -e . --quiet

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
