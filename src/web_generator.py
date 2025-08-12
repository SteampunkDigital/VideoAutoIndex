# web_generator.py
import os
import json
from pathlib import Path
from flask import Flask, render_template_string
from typing import Dict, List

class WebGenerator:
    def __init__(self, analysis_path: str, video_path: str, transcript_path: str = None):
        """
        Initialize the web generator.
        
        Args:
            analysis_path: Path to the JSON file containing meeting analysis
            video_path: Path to the video file
            transcript_path: Path to the JSON transcript file (optional)
        """
        self.analysis_path = Path(analysis_path)
        self.video_path = Path(video_path)
        self.transcript_path = Path(transcript_path) if transcript_path else None
        
        if not self.analysis_path.exists():
            raise FileNotFoundError(f"Analysis file not found: {analysis_path}")
        if not self.video_path.exists():
            raise FileNotFoundError(f"Video file not found: {video_path}")
        if self.transcript_path and not self.transcript_path.exists():
            raise FileNotFoundError(f"Transcript file not found: {transcript_path}")

    def generate(self, output_dir: str, output_filename: str = "meeting_summary.html") -> str:
        """
        Generate a webpage with meeting analysis and video links.
        
        Args:
            output_dir: Directory to save the webpage
            output_filename: Name of the output HTML file
            
        Returns:
            Path to the generated HTML file
        """
        os.makedirs(output_dir, exist_ok=True)
        
        # Read the analysis
        with open(self.analysis_path) as f:
            analysis = json.load(f)
            
        # Get relative paths for assets
        output_path = os.path.join(output_dir, output_filename)
        # Calculate relative path from the final webpage location (which will be in video directory)
        video_dir = os.path.dirname(self.video_path)
        video_rel_path = os.path.basename(self.video_path)  # Just use the video filename since it will be in same directory
            
        # Load transcript if provided
        transcript = self._load_transcript() if self.transcript_path else None
        
        # Generate HTML
        html = self._generate_html(analysis, video_rel_path, transcript)
        
        # Write HTML file
        with open(output_path, "w") as f:
            f.write(html)
            
        return output_path

    def _load_transcript(self) -> List[Dict]:
        """
        Load and format the JSON transcript file.
        
        Returns:
            List of transcript chunks with timing and text
        """
        with open(self.transcript_path, 'r', encoding='utf-8') as f:
            transcript_data = json.load(f)
        
        # Extract chunks and format for web display
        chunks = []
        for chunk in transcript_data.get('chunks', []):
            if 'timestamp' in chunk and 'text' in chunk and chunk['timestamp']:
                timestamp = chunk['timestamp']
                if len(timestamp) >= 2 and timestamp[0] is not None and timestamp[1] is not None:
                    start_time, end_time = timestamp[0], timestamp[1]
                    chunks.append({
                        'start_seconds': start_time,
                        'end_seconds': end_time,
                        'text': chunk['text'].strip(),
                        'start_time_formatted': self._seconds_to_timestamp(start_time),
                        'end_time_formatted': self._seconds_to_timestamp(end_time)
                    })
        
        return chunks
    
    def _seconds_to_timestamp(self, seconds: float) -> str:
        """
        Convert seconds to HH:MM:SS,mmm format.
        """
        if seconds is None:
            return "00:00:00,000"
        
        seconds = float(seconds)  # Ensure it's a float
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        ms = int((seconds % 1) * 1000)
        return f"{hours:02d}:{minutes:02d}:{secs:02d},{ms:03d}"
    
    def _generate_html(self, analysis: List[Dict], video_rel_path: str, transcript: List[Dict] = None) -> str:
        """
        Generate HTML content from the analysis.
        
        Args:
            analysis: List of topic dictionaries with moments and takeaways
            video_rel_path: Relative path to the video file
            
        Returns:
            Generated HTML content
        """
        template = '''
        <!DOCTYPE html>
        <html lang="en">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Meeting Summary</title>
            <style>
                body {
                    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
                    line-height: 1.6;
                    max-width: 1200px;
                    margin: 0 auto;
                    padding: 20px;
                    color: #333;
                }
                .video-container {
                    margin: 20px 0;
                }
                video {
                    max-width: 100%;
                }
                .topic {
                    margin: 40px 0;
                    padding: 20px;
                    background: #f8f9fa;
                    border-radius: 8px;
                }
                .topic h2 {
                    margin-top: 0;
                    color: #2c3e50;
                }
                .timestamp {
                    color: #666;
                    font-family: monospace;
                    background: #eee;
                    padding: 2px 6px;
                    border-radius: 4px;
                    cursor: pointer;
                }
                .timestamp:hover {
                    background: #ddd;
                }
                .key-moments {
                    margin: 20px 0;
                }
                .key-moment {
                    margin: 10px 0;
                    padding: 10px;
                    background: white;
                    border-left: 4px solid #3498db;
                }
                .takeaways {
                    margin: 20px 0;
                }
                .takeaway {
                    margin: 10px 0;
                    padding: 10px;
                    background: white;
                    border-left: 4px solid #2ecc71;
                }
                h3 {
                    color: #34495e;
                    margin: 20px 0 10px;
                }
                .transcript-section {
                    margin: 40px 0;
                    padding: 20px;
                    background: #f8f9fa;
                    border-radius: 8px;
                }
                .transcript-chunk {
                    margin: 5px 0;
                    padding: 8px 12px;
                    background: white;
                    border-radius: 4px;
                    cursor: pointer;
                    transition: background-color 0.2s;
                }
                .transcript-chunk:hover {
                    background: #e3f2fd;
                }
                .transcript-chunk.active {
                    background: #2196f3;
                    color: white;
                }
                .transcript-timestamp {
                    font-family: monospace;
                    color: #666;
                    font-size: 0.9em;
                    margin-right: 10px;
                }
                .transcript-chunk.active .transcript-timestamp {
                    color: #bbdefb;
                }
            </style>
        </head>
        <body>
            <h1>Meeting Summary</h1>
            
            <div class="video-container">
                <video id="meeting-video" controls>
                    <source src="{{ video_rel_path }}" type="video/mp4">
                    Your browser does not support the video tag.
                </video>
            </div>

            <div class="topics">
                {% for topic in analysis %}
                <div class="topic">
                    <h2>
                        {{ topic.topic }}
                        <span class="timestamp" onclick="seekVideo('{{ topic.timestamp }}')">
                            {{ topic.timestamp }}
                        </span>
                    </h2>

                    <div class="key-moments">
                        <h3>Key Moments</h3>
                        {% for moment in topic.key_moments %}
                        <div class="key-moment">
                            {{ moment.description }}
                            <span class="timestamp" onclick="seekVideo('{{ moment.timestamp }}')">
                                {{ moment.timestamp }}
                            </span>
                        </div>
                        {% endfor %}
                    </div>

                    <div class="takeaways">
                        <h3>Key Takeaways</h3>
                        {% for takeaway in topic.takeaways %}
                        <div class="takeaway">
                            {{ takeaway }}
                        </div>
                        {% endfor %}
                    </div>
                </div>
                {% endfor %}
            </div>

            {% if transcript %}
            <div class="transcript-section">
                <h2>Full Transcript</h2>
                <div class="transcript">
                    {% for chunk in transcript %}
                    <div class="transcript-chunk" 
                         data-start="{{ chunk.start_seconds }}" 
                         data-end="{{ chunk.end_seconds }}"
                         onclick="seekToTime({{ chunk.start_seconds }})">
                        <span class="transcript-timestamp">{{ chunk.start_time_formatted }}</span>
                        {{ chunk.text }}
                    </div>
                    {% endfor %}
                </div>
            </div>
            {% endif %}

            <script>
                function seekVideo(timestamp) {
                    const video = document.getElementById('meeting-video');
                    const seconds = parseTimestamp(timestamp);
                    video.currentTime = seconds;
                    video.play();
                }

                function seekToTime(seconds) {
                    const video = document.getElementById('meeting-video');
                    video.currentTime = seconds;
                    video.play();
                }

                function parseTimestamp(timestamp) {
                    // Convert HH:MM:SS,mmm to seconds
                    const [time, ms] = timestamp.split(',');
                    const [hours, minutes, seconds] = time.split(':').map(Number);
                    return hours * 3600 + minutes * 60 + seconds + Number(ms) / 1000;
                }

                // Highlight current transcript segment during playback
                function updateTranscriptHighlight() {
                    const video = document.getElementById('meeting-video');
                    const currentTime = video.currentTime;
                    const chunks = document.querySelectorAll('.transcript-chunk');
                    
                    chunks.forEach(chunk => {
                        const startTime = parseFloat(chunk.dataset.start);
                        const endTime = parseFloat(chunk.dataset.end);
                        
                        if (currentTime >= startTime && currentTime <= endTime) {
                            chunk.classList.add('active');
                        } else {
                            chunk.classList.remove('active');
                        }
                    });
                }


                // Set up video event listeners
                document.addEventListener('DOMContentLoaded', function() {
                    const video = document.getElementById('meeting-video');
                    if (video) {
                        // Update transcript highlight as video plays
                        video.addEventListener('timeupdate', updateTranscriptHighlight);
                        
                        // Also update on seeking
                        video.addEventListener('seeked', updateTranscriptHighlight);
                    }
                });
            </script>
        </body>
        </html>
        '''
        
        # Create a minimal Flask app for template rendering
        app = Flask(__name__)
        with app.app_context():
            return render_template_string(
                template,
                analysis=analysis,
                video_rel_path=video_rel_path,
                transcript=transcript
            )
