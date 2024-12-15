# Video Auto Index

Automatically process meeting videos to extract key moments, topics, and takeaways. The tool generates a navigable summary webpage with video chapters.

## Features

- Extracts audio from video files
- Transcribes speech to text using faster-whisper
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

- Python 3.8+
- ffmpeg
- Anthropic API key

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

2. Install Python dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Set up your Anthropic API key:
   ```bash
   export ANTHROPIC_API_KEY='your-api-key'
   ```

## Usage

Process a video file:
```bash
python src/main.py path/to/video.mp4 [--output-dir output]
```

This will:
1. Extract audio from the video
2. Transcribe the audio
3. Analyze the content for topics and key moments
4. Add chapters to the video
5. Generate an HTML summary page

The output directory will contain:
- `meeting_analysis.json`: Extracted topics, moments, and takeaways
- `*_audio.wav`: Extracted audio file
- `*.srt`: Generated subtitles
- `*_chaptered.mp4`: Video file with chapter markers
- `meeting_summary.html`: Interactive summary webpage

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
- `transcriber.py`: Speech-to-text conversion
- `key_moments.py`: Content analysis
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
