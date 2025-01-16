# Video Auto Index

Automatically process meeting videos to extract key moments, topics, and takeaways. The tool generates a navigable summary webpage with video chapters.

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

   # Install insanely-fast-whisper
   pip install insanely-fast-whisper --ignore-requires-python
   ```

3. Set up your Anthropic API key:
   ```bash
   export ANTHROPIC_API_KEY='your-api-key'
   ```

## Usage

Process a video file:
```bash
python -m src.main [video path] [--output-dir output] [--device-id DEVICE]
```

Device options:
- Default: Automatically uses MPS on Apple Silicon, CPU/CUDA on other systems
- `--device-id 0`: Force CPU/CUDA device
- `--device-id mps`: Force MPS device on Apple Silicon

For example:
```bash
# Use default device (auto-detected)
python -m src.main /path/to/video.mp4 --output-dir output

# Force CPU/CUDA device
python -m src.main /path/to/video.mp4 --output-dir output --device-id 0

# Force MPS device on Apple Silicon
python -m src.main /path/to/video.mp4 --output-dir output --device-id mps
```

This will:
1. Extract audio from the video
2. Transcribe the audio using insanely-fast-whisper
3. Analyze the meeting content for topics and key moments
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
- `transcriber.py`: Speech-to-text conversion using insanely-fast-whisper
- `key_moments.py`: AI content analysis
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
