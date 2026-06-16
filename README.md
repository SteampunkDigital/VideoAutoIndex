# Video Auto Index

Automatically process meeting videos to extract key moments, topics, and takeaways. The tool generates a navigable summary webpage with video chapters.

## Demo

View the GitHub Pages demo: https://steampunkdigital.github.io/VideoAutoIndex/demo/

## Features

- Extracts audio from video files
- Transcribes speech to text using insanely-fast-whisper
  - Uses Whisper large-v3 model by default for best accuracy
  - Optimized for both NVIDIA GPUs and Apple Silicon
  - Flash Attention 2 support for NVIDIA GPUs
  - Word-level timestamp support
- Analyzes content to identify:
  - Major topics with timestamps
  - Key moments within each topic
  - Actionable takeaways
- Adds chapter markers to the video
- Generates an interactive HTML summary
  - Clickable timestamps for video navigation
  - Organized by topics
  - Highlights key moments and takeaways

## Requirements

- Python 3.11+
- ffmpeg
- NVIDIA GPU or Apple Silicon Mac
- Conda (for environment management)

## Installation

1. Install ffmpeg:
   ```bash
   # macOS
   brew install ffmpeg

   # Ubuntu/Debian
   sudo apt-get install ffmpeg

   # Windows
   # Download from https://ffmpeg.org/download.html
   ```

2. Set up the conda environment:
   ```bash
   # Create and activate the conda environment
   conda env create -f environment.yml
   conda activate video-auto-index
   ```

   This will automatically install all dependencies, including insanely-fast-whisper.

3. Create a `.env` file for API-backed modes:
   ```bash
   cp .env.example .env
   ```

   Add the keys for the hosted model providers you plan to use:
   ```bash
   ANTHROPIC_API_KEY=your-anthropic-api-key
   OPENAI_API_KEY=your-openai-api-key
   ```

   You only need the key for the mode you run:
   - `--anthropic` requires `ANTHROPIC_API_KEY`
   - `--openai` requires `OPENAI_API_KEY`
   - `--apple` does not require any API keys

   Shell environment variables take precedence over values in `.env`.

## Usage

Process a video file:
```bash
python -m src.main [video path] (--apple | --openai | --anthropic) [--output-dir output]
```

Running modes:
- `--apple`: Uses Apple `DictationTranscriber` for transcription and `tools/apple_foundation_key_moments.swift` for key moments. No API keys are needed.
- `--openai`: Uses Whisper for transcription and OpenAI for key moments analysis. Requires `OPENAI_API_KEY`.
- `--anthropic`: Uses Whisper for transcription and Claude for key moments analysis. Requires `ANTHROPIC_API_KEY`.

Whisper device defaults:
- Darwin/macOS: `mps`
- Windows/Linux: `0` for CPU/CUDA
- Use `--device-id DEVICE` to override the Whisper device for `--openai` or `--anthropic`.

For example:
```bash
# Local Apple models; no API keys required
python -m src.main /path/to/video.mp4 --apple --output-dir output

# Whisper transcription plus OpenAI analysis
python -m src.main /path/to/video.mp4 --openai --output-dir output

# Whisper transcription plus Claude analysis
python -m src.main /path/to/video.mp4 --anthropic --output-dir output
```

This will:
1. Extract audio from the video
2. Transcribe the audio using the selected mode
3. Analyze the meeting content for topics and key moments using the selected mode
4. Generate an HTML summary page

The output directory will contain:
- `audio.wav`: Extracted audio file
- `audio_transcript.json`: Transcribed speech with timestamps
- `audio_subtitles.srt`: Generated subtitles
- `meeting_analysis.json`: Extracted topics, moments, and takeaways

Final web output is stored in:
- `<video_base_path>/<video_filename>_summary.html`

## Output Format

The analysis JSON follows this structure:
```json
[
  {
    "topic": "Topic description",
    "timestamp": "HH:MM:SS,mmm",
    "key_moments": [
      {
        "description": "Key moment description",
        "timestamp": "HH:MM:SS,mmm"
      }
    ],
    "takeaways": [
      "Actionable takeaway 1",
      "Actionable takeaway 2"
    ]
  }
]
```

## Development

The project is organized into modular components:
- `video_processor.py`: Handles video/audio operations
- `transcriber.py`: Speech-to-text conversion using insanely-fast-whisper for hosted model modes
- `transcriber_apple_dictation.py`: Apple DictationTranscriber wrapper for `--apple`
- `key_moments.py`: AI content analysis using Anthropic, OpenAI, or Apple Foundation Models
- `web_generator.py`: HTML summary generation
- `main.py`: Pipeline orchestration

Each component can be run independently, allowing for flexible processing pipelines.

## Testing

The project includes a comprehensive test suite covering all components:

### Running Tests

Run all tests:
```bash
pytest
```

Run with coverage report:
```bash
pytest --cov=src tests/
```

Run specific test categories:
```bash
# Unit tests only
pytest -v -m "not integration"

# Integration tests only
pytest -v -m "integration"
```

### Test Structure

- `test_video_processor.py`: Tests for video and audio processing
- `test_transcriber.py`: Tests for speech-to-text conversion
- `test_key_moments.py`: Tests for content analysis with API mocking
- `test_web_generator.py`: Tests for HTML generation
- `test_main.py`: Integration tests for the full pipeline

### Test Coverage

The test suite includes:
- Unit tests for each component
- Integration tests for the full pipeline
- API mocking for external services
- Fixture-based test data
- Error handling verification
- Edge case validation

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests for new functionality
5. Ensure all tests pass
6. Submit a pull request
