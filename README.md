# Video Auto Index

Automatically process meeting videos to extract key moments, generate takeaways, and create an indexed webpage.

## Setup

### Using Conda (Recommended)

1. Install Miniconda if you haven't already:
   - Download from [Miniconda](https://docs.conda.io/en/latest/miniconda.html)
   - Or via command line:
     ```bash
     # macOS
     brew install --cask miniconda
     
     # Linux
     wget https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh
     bash Miniconda3-latest-Linux-x86_64.sh
     ```

2. Create and activate the conda environment:
   ```bash
   # Create environment from environment.yml
   conda env create -f environment.yml
   
   # Activate environment
   conda activate video-auto-index
   ```

3. Verify installation:
   ```bash
   # Check ffmpeg
   ffmpeg -version
   
   # Run tests
   pytest -v
   ```

### Manual Setup (Alternative)

If you prefer not to use conda, you can install dependencies manually:

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
