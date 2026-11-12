#!/bin/bash
# Usage: ./run.sh VIDEO --transcribe PROVIDER --summarize PROVIDER [other CLI options]
set -e

if [ "$#" -eq 0 ]; then
    echo "Usage: ./run.sh VIDEO [--transcribe whisper|apple|openai|speechcpp] --summarize anthropic|apple|openai"
    exit 1
fi

# Python loads .env without overriding the shell and validates only active stages.
eval "$(conda shell.bash hook)"
conda activate video-auto-index
python -m src.main "$@"
