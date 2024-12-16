import pytest
import os
import json
from src.web_generator import WebGenerator
from bs4 import BeautifulSoup

@pytest.fixture
def test_data_dir():
    """Get the test_data directory path."""
    return os.path.join(os.path.dirname(os.path.dirname(__file__)), "test_data")

@pytest.fixture
def sample_analysis(test_data_dir):
    """Load the actual test data analysis."""
    analysis_path = os.path.join(test_data_dir, "meeting_analysis.json")
    with open(analysis_path, 'r') as f:
        return json.load(f)

@pytest.fixture
def sample_analysis_path(temp_dir, sample_analysis):
    """Create a temporary analysis file with actual test data."""
    analysis_path = os.path.join(temp_dir, "meeting_analysis.json")
    with open(analysis_path, "w") as f:
        json.dump(sample_analysis, f)
    return analysis_path

@pytest.fixture
def sample_video(temp_dir):
    """Create a dummy video file for testing."""
    video_path = os.path.join(temp_dir, "video.mp4")
    with open(video_path, "wb") as f:
        f.write(b"dummy video data")
    return video_path

def test_web_generator_init(sample_analysis_path, sample_video):
    """Test WebGenerator initialization with valid files."""
    generator = WebGenerator(sample_analysis_path, sample_video)
    assert generator.analysis_path.exists()
    assert generator.video_path.exists()

def test_web_generator_init_invalid_analysis():
    """Test WebGenerator initialization with non-existent analysis file."""
    with pytest.raises(FileNotFoundError):
        WebGenerator("nonexistent.json", "dummy.mp4")

def test_web_generator_init_invalid_video(sample_analysis_path):
    """Test WebGenerator initialization with non-existent video file."""
    with pytest.raises(FileNotFoundError):
        WebGenerator(sample_analysis_path, "nonexistent.mp4")

def test_generate_html(sample_analysis_path, sample_video, temp_dir, sample_analysis):
    """Test HTML generation with actual test data."""
    generator = WebGenerator(sample_analysis_path, sample_video)
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
    
    # Check topics section matches test data
    topics = soup.find_all(class_="topic")
    assert len(topics) == len(sample_analysis)
    
    # Check first topic matches test data
    topic = topics[0]
    test_topic = sample_analysis[0]
    assert test_topic["topic"] in topic.h2.text
    assert test_topic["timestamp"] in topic.h2.text
    
    # Check key moments match test data
    moments = topic.find_all(class_="key-moment")
    assert len(moments) == len(test_topic["key_moments"])
    for moment, test_moment in zip(moments, test_topic["key_moments"]):
        assert test_moment["description"] in moment.text
        assert test_moment["timestamp"] in moment.text
    
    # Check takeaways match test data
    takeaways = topic.find_all(class_="takeaway")
    assert len(takeaways) == len(test_topic["takeaways"])
    for takeaway, test_takeaway in zip(takeaways, test_topic["takeaways"]):
        assert test_takeaway in takeaway.text

def test_generate_creates_output_dir(sample_analysis_path, sample_video, temp_dir):
    """Test HTML generation creates output directory if it doesn't exist."""
    output_dir = os.path.join(temp_dir, "nested", "output")
    
    generator = WebGenerator(sample_analysis_path, sample_video)
    output_path = generator.generate(output_dir)
    
    assert os.path.exists(output_dir)
    assert os.path.exists(output_path)

def test_generate_relative_video_path(sample_analysis_path, sample_video, temp_dir):
    """Test HTML generation uses relative video path."""
    generator = WebGenerator(sample_analysis_path, sample_video)
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

def test_javascript_functionality(sample_analysis_path, sample_video, temp_dir):
    """Test that required JavaScript functions are present."""
    generator = WebGenerator(sample_analysis_path, sample_video)
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
