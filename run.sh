#!/bin/bash

# Script to run video auto-indexing
# Usage: ./run.sh [video_file_path] [apple|openai|anthropic] [en|ja] [en|ja] [dictation|speech-progressive]
# Default mode: apple
# Default transcription language: en
# Optional fourth argument compares a second Apple transcription language.

# Set the conda environment and project directory
CONDA_ENV="video-auto-index"
VIDEO_FILE="${1}"
MODE="${2:-apple}"
TRANSCRIPTION_LANGUAGE="${3:-en}"
COMPARE_TRANSCRIPTION_LANGUAGE="${4:-}"
APPLE_TRANSCRIPTION_ENGINE="${5:-speech-progressive}"

if [ -z "$VIDEO_FILE" ]; then
    echo "Usage: ./run.sh [video_file_path] [apple|openai|anthropic] [en|ja] [optional compare en|ja] [dictation|speech-progressive]"
    exit 1
fi

if [ "$MODE" != "apple" ] && [ "$MODE" != "openai" ] && [ "$MODE" != "anthropic" ]; then
    echo "Error: mode must be 'apple', 'openai', or 'anthropic'"
    exit 1
fi

if [ "$TRANSCRIPTION_LANGUAGE" != "en" ] && [ "$TRANSCRIPTION_LANGUAGE" != "ja" ]; then
    echo "Error: transcription language must be 'en' or 'ja'"
    exit 1
fi

if [ -n "$COMPARE_TRANSCRIPTION_LANGUAGE" ] && [ "$COMPARE_TRANSCRIPTION_LANGUAGE" != "en" ] && [ "$COMPARE_TRANSCRIPTION_LANGUAGE" != "ja" ]; then
    echo "Error: compare transcription language must be 'en' or 'ja'"
    exit 1
fi

if [ "$APPLE_TRANSCRIPTION_ENGINE" != "dictation" ] && [ "$APPLE_TRANSCRIPTION_ENGINE" != "speech-progressive" ]; then
    echo "Error: Apple transcription engine must be 'dictation' or 'speech-progressive'"
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
echo "Running VideoAutoIndex in $MODE mode with $TRANSCRIPTION_LANGUAGE transcription"
args=("$VIDEO_FILE" "--$MODE" --transcription-language "$TRANSCRIPTION_LANGUAGE")
if [ -n "$COMPARE_TRANSCRIPTION_LANGUAGE" ]; then
    args+=(--compare-transcription-language "$COMPARE_TRANSCRIPTION_LANGUAGE")
fi
if [ "$MODE" = "apple" ]; then
    args+=(--apple-transcription-engine "$APPLE_TRANSCRIPTION_ENGINE")
fi
python -m src.main "${args[@]}"
