#!/bin/bash

# Script to run video auto-indexing
# Usage: ./run.sh [video_file_path] [whisper|qwen|dictation] [apple|openai|anthropic]
# Default transcriber: dictation (Apple Speech)
# Default analyzer: apple (Apple Foundation Models)

# Set the conda environment and project directory
CONDA_ENV="video-auto-index"
VIDEO_FILE="${1}"
TRANSCRIBER="${2:-dictation}"
ANALYZER="${3:-apple}"

if [ -z "$VIDEO_FILE" ]; then
    echo "Usage: ./run.sh [video_file_path] [whisper|qwen|dictation] [apple|openai|anthropic]"
    exit 1
fi

if [ "$TRANSCRIBER" != "whisper" ] && [ "$TRANSCRIBER" != "qwen" ] && [ "$TRANSCRIBER" != "dictation" ]; then
    echo "Error: transcriber must be 'whisper', 'qwen', or 'dictation'"
    exit 1
fi

if [ "$ANALYZER" != "apple" ] && [ "$ANALYZER" != "openai" ] && [ "$ANALYZER" != "anthropic" ]; then
    echo "Error: analyzer must be 'apple', 'openai', or 'anthropic'"
    exit 1
fi

if [ -f ".env" ]; then
    # Export keys from .env for the Python CLI and downstream tools.
    set -a
    source ".env"
    set +a
fi

missing_vars=()
if [ "$ANALYZER" = "openai" ] && [ -z "$OPENAI_API_KEY" ]; then
    missing_vars+=("OPENAI_API_KEY")
fi
if [ "$ANALYZER" = "anthropic" ] && [ -z "$ANTHROPIC_API_KEY" ]; then
    missing_vars+=("ANTHROPIC_API_KEY")
fi
if [ "$TRANSCRIBER" = "qwen" ] && [ -z "$HF_TOKEN" ]; then
    missing_vars+=("HF_TOKEN")
fi

if [ "${#missing_vars[@]}" -gt 0 ]; then
    echo "Error: Missing required environment value(s): ${missing_vars[*]}"
    echo "Set them in your shell or in .env."
    exit 1
fi

# Activate conda environment and run the script
eval "$(conda shell.bash hook)"
conda activate "$CONDA_ENV"

# Run the Python script with the video file
echo "Running VideoAutoIndex with transcriber=$TRANSCRIBER analyzer=$ANALYZER"
python -m src.main "$VIDEO_FILE" "--$ANALYZER" --transcriber "$TRANSCRIBER"
