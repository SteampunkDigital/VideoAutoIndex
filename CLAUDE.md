# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

VideoAutoIndex is a Python application that processes meeting videos to extract key moments, topics, and takeaways. It generates navigable HTML summaries with clickable timestamps for video navigation.

## Core Architecture

The application follows a modular pipeline architecture with 4 main processing stages:

1. **Video Processing** (`video_processor.py`) - Extracts audio from video files using ffmpeg
2. **Transcription** (`transcriber.py`) - Converts audio to text using insanely-fast-whisper with word-level timestamps
3. **Content Analysis** (`key_moments.py`) - Uses AI APIs (Anthropic Claude or OpenAI GPT) to analyze transcripts and extract topics, key moments, and takeaways
4. **Web Generation** (`web_generator.py`) - Creates interactive HTML summaries with embedded video navigation

The main orchestration happens in `main.py` which coordinates the entire pipeline and supports stage skipping for development.

## Environment Setup

```bash
# Set up conda environment
conda env create -f environment.yml
conda activate video-auto-index

# Set API key (choose one)
export ANTHROPIC_API_KEY='your-anthropic-key'
# OR
export OPENAI_API_KEY='your-openai-key'
```

## Development Commands

### Running the Application
```bash
# REQUIRED: Choose AI provider (Anthropic or OpenAI)

# Using Anthropic Claude (with explicit key)
python -m src.main /path/to/video.mp4 --anthropic sk-ant-key...

# Using Anthropic Claude (with environment variable)
python -m src.main /path/to/video.mp4 --anthropic

# Using OpenAI GPT (with explicit key) 
python -m src.main /path/to/video.mp4 --openai sk-proj-key...

# Using OpenAI GPT (with environment variable)
python -m src.main /path/to/video.mp4 --openai

# Additional options
python -m src.main /path/to/video.mp4 --anthropic --output-dir output
python -m src.main /path/to/video.mp4 --openai --device-id mps --skip transcribe
```

### Testing
```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=src tests/

# Run only unit tests (exclude integration tests)
pytest -v -m "not integration"

# Run only integration tests
pytest -v -m "integration"
```

## Key Dependencies

- **insanely-fast-whisper**: Optimized Whisper implementation for transcription
- **anthropic**: Claude API client for content analysis
- **openai**: OpenAI API client for content analysis
- **ffmpeg-python**: Video/audio processing
- **flask**: Used only for HTML template rendering in web generator

## AI Provider Options

### Anthropic Claude
- **Model**: Claude Opus 4.1 (latest and most capable)
- **Usage**: `--anthropic [key]`
- **Strengths**: Excellent reasoning, structured output, long context

### OpenAI GPT
- **Models**: Automatically selects best available (GPT-5, O3, or GPT-4o)
- **Usage**: `--openai [key]`
- **Strengths**: Fast processing, competitive reasoning

## Data Flow

1. Input: Video file (.mp4, .mov, etc.)
2. Output: `{video_name}_audio.wav` (extracted audio)
3. Output: `audio_transcript.json` (raw transcription with timestamps)
4. Output: `audio_subtitles.srt` (formatted subtitles)
5. Output: `meeting_analysis.json` (structured topics and key moments)
6. Final: `{video_name}_summary.html` (interactive web summary)

## Testing Strategy

- Unit tests for each component with mocked external dependencies
- Integration tests for full pipeline using sample data
- API mocking for AI provider calls to avoid API costs during testing
- Fixture-based test data in `test_data/` directory

## Error Handling

The application includes comprehensive error handling for API issues:

### Common API Errors
- **Quota/Rate Limits**: Clear messages about usage limits and billing
- **Authentication**: Helpful guidance on API key validation
- **Network Issues**: Connection troubleshooting tips
- **Model Access**: Automatic fallback for OpenAI model selection

### Error Recovery
When API errors occur, the application provides specific troubleshooting steps and exits gracefully, preserving any completed work (audio extraction, transcription) for retry with `--skip`.

## Stage Skipping for Development

Use the `--skip` argument to jump to specific stages during development:
- `--skip transcribe`: Skip audio extraction, start from existing audio file
- `--skip analyze`: Skip to content analysis with existing transcript
- `--skip generate`: Skip to web generation with existing analysis

This is useful for iterating on specific components without re-running expensive operations like transcription, and essential for recovery after API errors.