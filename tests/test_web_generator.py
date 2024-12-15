import pytest
import os
import json
from src.web_generator import WebGenerator
from bs4 import BeautifulSoup

@pytest.fixture
def sample_analysis(temp_dir):
    """Create a sample analysis JSON file for testing."""
    analysis = [
        {
            "topic": "Project Overview",
            "timestamp": "00:00:00,000",
            "key_moments": [
                {
                    "description": "Introduction of team members",
                    "timestamp": "00:00:05,000"
                },
                {
                    "description": "Project goals outlined",
                    "timestamp": "00:00:10,000"
                }
            ],
            "takeaways": [
                "Team roles established",
                "Q4 objectives defined"
            ]
        }
    ]
    
    analysis_path = os.path.join(temp_dir, "analysis.json")
    with open(analysis_path, "w") as f:
        json.dump(analysis, f)
    return analysis_path

@pytest.fixture
def sample_video(temp_dir):
    """Create a dummy video file for testing."""
    video_path = os.path.join(temp_dir, "video.mp4")
    with open(video_path, "wb") as f:
        f.write(b"dummy video data")
    return video_path

def test_web_generator_init(sample_analysis, sample_video):
    """Test WebGenerator initialization with valid files."""
    generator = WebGenerator(sample_analysis, sample_video)
    assert generator.analysis_path.exists()
    assert generator.video_path.exists()

def test_web_generator_init_invalid_analysis():
    """Test WebGenerator initialization with non-existent analysis file."""
    with pytest.raises(FileNotFoundError):
        WebGenerator("nonexistent.json", "dummy.mp4")

def test_web_generator_init_invalid_video(sample_analysis):
    """Test WebGenerator initialization with non-existent video file."""
    with pytest.raises(FileNotFoundError):
        WebGenerator(sample_analysis, "nonexistent.mp4")

def test_generate_html(sample_analysis, sample_video, temp_dir):
    """Test HTML generation with valid inputs."""
    generator = WebGenerator(sample_analysis, sample_video)
    output_path = generator.generate(temp_dir)
    
    # Check that HTML file was created
    assert os.path.exists(output_path)
    assert output_path.endswith(".html")
    
    # Parse and validate HTML content
    with open(output_path, "r") as f:
        content = f.read()
    
    soup = BeautifulSoup(content, "html.parser")
    
    # Check basic structure
    assert soup.title.string == "Meeting Summary"
    assert soup.find("video") is not None
    
    # Check topics section
    topics = soup.find_all(class_="topic")
    assert len(topics) > 0
    
    # Check first topic
    topic = topics[0]
    assert "Project Overview" in topic.h2.text
    assert "00:00:00,000" in topic.h2.text
    
    # Check key moments
    moments = topic.find_all(class_="key-moment")
    assert len(moments) == 2
    assert "Introduction of team members" in moments[0].text
    assert "00:00:05,000" in moments[0].text
    
    # Check takeaways
    takeaways = topic.find_all(class_="takeaway")
    assert len(takeaways) == 2
    assert "Team roles established" in takeaways[0].text

def test_generate_creates_output_dir(sample_analysis, sample_video, temp_dir):
    """Test HTML generation creates output directory if it doesn't exist."""
    output_dir = os.path.join(temp_dir, "nested", "output")
    
    generator = WebGenerator(sample_analysis, sample_video)
    output_path = generator.generate(output_dir)
    
    assert os.path.exists(output_dir)
    assert os.path.exists(output_path)

def test_generate_relative_video_path(sample_analysis, sample_video, temp_dir):
    """Test HTML generation uses relative video path."""
    generator = WebGenerator(sample_analysis, sample_video)
    output_path = generator.generate(temp_dir)
    
    with open(output_path, "r") as f:
        content = f.read()
    
    soup = BeautifulSoup(content, "html.parser")
    video_source = soup.find("source")
    
    # Video source should be a relative path
    assert not os.path.isabs(video_source["src"])
    assert "../" not in video_source["src"]

def test_generate_invalid_analysis_json(temp_dir, sample_video):
    """Test HTML generation with invalid JSON file."""
    # Create invalid JSON file
    invalid_json = os.path.join(temp_dir, "invalid.json")
    with open(invalid_json, "w") as f:
        f.write("invalid json content")
    
    generator = WebGenerator(invalid_json, sample_video)
    with pytest.raises(json.JSONDecodeError):
        generator.generate(temp_dir)

def test_javascript_functionality(sample_analysis, sample_video, temp_dir):
    """Test that required JavaScript functions are present."""
    generator = WebGenerator(sample_analysis, sample_video)
    output_path = generator.generate(temp_dir)
    
    with open(output_path, "r") as f:
        content = f.read()
    
    # Check for required JavaScript functions
    assert "function seekVideo" in content
    assert "function parseTimestamp" in content
    
    # Check timestamp click handlers
    soup = BeautifulSoup(content, "html.parser")
    timestamps = soup.find_all(class_="timestamp")
    assert len(timestamps) > 0
    for timestamp in timestamps:
        assert "onclick" in timestamp.attrs
        assert "seekVideo" in timestamp["onclick"]
