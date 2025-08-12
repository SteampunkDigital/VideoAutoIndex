#!/bin/bash

# Script to run video auto-indexing
# Usage: ./run.sh [video_file_path]

# Set the conda environment and project directory
CONDA_ENV="video-auto-index"
VIDEO_FILE="${1}"
OPENAI_API_KEY=""

# Activate conda environment and run the script
eval "$(conda shell.bash hook)"
conda activate "$CONDA_ENV"

# Run the Python script with the video file
python -m src.main --openai "$OPENAI_API_KEY" "$VIDEO_FILE"
