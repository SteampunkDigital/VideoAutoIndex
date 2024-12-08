# Video Auto Index

Automatically process meeting videos to extract key moments, generate takeaways, and create an indexed webpage.

## Setup

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Install ffmpeg:
- macOS: `brew install ffmpeg`
- Ubuntu/Debian: `sudo apt-get install ffmpeg`
- Windows: Download from [ffmpeg.org](https://ffmpeg.org/download.html)

## Testing

The project uses pytest for unit testing. To run the tests:

```bash
# Run all tests
pytest

# Run tests with verbose output
pytest -v

# Run tests for a specific module
pytest tests/test_video_processor.py

# Run tests and show coverage report
pytest --cov=src
```

### Writing Tests

Tests are located in the `tests` directory. Each module in `src` has a corresponding test file in `tests`. For example:
- `src/video_processor.py` → `tests/test_video_processor.py`
- `src/transcriber.py` → `tests/test_transcriber.py`

When adding new functionality, please ensure to add corresponding tests.
