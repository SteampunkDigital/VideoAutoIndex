#!/bin/bash

# Script to run video auto-indexing
# Usage: ./run.sh [video_file_path] [apple|openai|anthropic]
# Default mode: apple

# Set the conda environment and project directory
CONDA_ENV="video-auto-index"
VIDEO_FILE="${1}"
MODE="${2:-apple}"

if [ -z "$VIDEO_FILE" ]; then
    echo "Usage: ./run.sh [video_file_path] [apple|openai|anthropic]"
    exit 1
fi

if [ "$MODE" != "apple" ] && [ "$MODE" != "openai" ] && [ "$MODE" != "anthropic" ]; then
    echo "Error: mode must be 'apple', 'openai', or 'anthropic'"
    exit 1
fi

if [ -f ".env" ]; then
    # Export keys from .env for the Python CLI and downstream tools.
    set -a
    source ".env"
    set +a
fi

missing_vars=()
if [ "$MODE" = "openai" ] && [ -z "$OPENAI_API_KEY" ]; then
    missing_vars+=("OPENAI_API_KEY")
fi
if [ "$MODE" = "anthropic" ] && [ -z "$ANTHROPIC_API_KEY" ]; then
    missing_vars+=("ANTHROPIC_API_KEY")
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
echo "Running VideoAutoIndex in $MODE mode"
python -m src.main "$VIDEO_FILE" "--$MODE"
