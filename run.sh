#!/bin/bash

# Script to run video auto-indexing
# Usage: ./run.sh [video_file_path]

# Set the conda environment and project directory
CONDA_ENV="video-auto-index"
VIDEO_FILE="${1}"

if [ -z "$VIDEO_FILE" ]; then
    echo "Usage: ./run.sh [video_file_path]"
    exit 1
fi

if [ ! -f ".env" ]; then
    echo "Error: .env file not found. Copy .env.example to .env and fill in your keys."
    exit 1
fi

# Export keys from .env for the Python CLI and downstream tools.
set -a
source ".env"
set +a

missing_vars=()
for var_name in OPENAI_API_KEY HF_TOKEN; do
    if [ -z "${!var_name}" ]; then
        missing_vars+=("$var_name")
    fi
done

if [ "${#missing_vars[@]}" -gt 0 ]; then
    echo "Error: Missing required value(s) in .env: ${missing_vars[*]}"
    exit 1
fi

# Activate conda environment and run the script
eval "$(conda shell.bash hook)"
conda activate "$CONDA_ENV"

# Run the Python script with the video file
python -m src.main "$VIDEO_FILE" --openai
