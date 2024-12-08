import pytest
import os
from src.video_processor import VideoProcessor

def test_video_processor_init(sample_video):
    """Test VideoProcessor initialization with valid video."""
    processor = VideoProcessor(sample_video)
    assert processor.video_path.exists()
    assert str(processor.video_path) == sample_video

def test_video_processor_init_invalid_path():
    """Test VideoProcessor initialization with non-existent video."""
    with pytest.raises(FileNotFoundError):
        VideoProcessor("nonexistent_video.mp4")

def test_extract_audio(sample_video, temp_dir):
    """Test audio extraction from video."""
    processor = VideoProcessor(sample_video)
    audio_path = processor.extract_audio(temp_dir)
    
    # Check that audio file was created
    assert os.path.exists(audio_path)
    assert audio_path.endswith("_audio.wav")
    
    # Check audio file is not empty
    assert os.path.getsize(audio_path) > 0

def test_extract_audio_invalid_output_dir(sample_video):
    """Test audio extraction with invalid output directory."""
    processor = VideoProcessor(sample_video)
    # Create a file where the output directory should be
    with open("invalid_dir", "w") as f:
        f.write("test")
    
    with pytest.raises(Exception):
        processor.extract_audio("invalid_dir")
    
    # Cleanup
    os.remove("invalid_dir")
