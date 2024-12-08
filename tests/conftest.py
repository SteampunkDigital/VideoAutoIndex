import pytest
import os
import tempfile
from pathlib import Path

@pytest.fixture
def temp_dir():
    """Provide a temporary directory for test files."""
    with tempfile.TemporaryDirectory() as tmpdirname:
        yield tmpdirname

@pytest.fixture
def sample_video(temp_dir):
    """Create a small test video file using ffmpeg."""
    video_path = os.path.join(temp_dir, "test_video.mp4")
    
    # Create a 1-second test video with a black screen and silence
    os.system(
        f'ffmpeg -f lavfi -i color=c=black:s=320x240:d=1 '
        f'-f lavfi -i anullsrc=r=44100:cl=mono:d=1 '
        f'-c:v libx264 -c:a aac -t 1 {video_path} '
        f'-y >/dev/null 2>&1'
    )
    
    if not os.path.exists(video_path):
        pytest.skip("Failed to create test video. Is ffmpeg installed?")
    
    yield video_path
    
    # Cleanup is handled by temp_dir fixture
