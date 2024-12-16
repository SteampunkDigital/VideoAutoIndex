# web_generator.py
import os
import json
from pathlib import Path
from flask import Flask, render_template_string
from typing import Dict, List

class WebGenerator:
    def __init__(self, analysis_path: str, video_path: str):
        """
        Initialize the web generator.
        
        Args:
            analysis_path: Path to the JSON file containing meeting analysis
            video_path: Path to the video file
        """
        self.analysis_path = Path(analysis_path)
        self.video_path = Path(video_path)
        
        if not self.analysis_path.exists():
            raise FileNotFoundError(f"Analysis file not found: {analysis_path}")
        if not self.video_path.exists():
            raise FileNotFoundError(f"Video file not found: {video_path}")

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
        video_rel_path = os.path.relpath(self.video_path, output_dir)
            
        # Generate HTML
        html = self._generate_html(analysis, video_rel_path)
        
        # Write HTML file
        with open(output_path, "w") as f:
            f.write(html)
            
        return output_path

    def _generate_html(self, analysis: List[Dict], video_rel_path: str) -> str:
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

            <script>
                function seekVideo(timestamp) {
                    const video = document.getElementById('meeting-video');
                    const seconds = parseTimestamp(timestamp);
                    video.currentTime = seconds;
                    video.play();
                }

                function parseTimestamp(timestamp) {
                    // Convert HH:MM:SS,mmm to seconds
                    const [time, ms] = timestamp.split(',');
                    const [hours, minutes, seconds] = time.split(':').map(Number);
                    return hours * 3600 + minutes * 60 + seconds + Number(ms) / 1000;
                }
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
                video_rel_path=video_rel_path
            )
