# web_generator.py
import os
import json
import mimetypes
from pathlib import Path
from flask import Flask, render_template_string
from typing import Dict, List
from .transcript import format_timestamp, normalize_chunk

SPEAKER_COLORS = ("#1d4ed8", "#9d174d", "#047857", "#6d28d9", "#92400e", "#0e7490")

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
        with open(output_path, "w", encoding="utf-8") as f:
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
        colors = {speaker: SPEAKER_COLORS[i % len(SPEAKER_COLORS)]
                  for i, speaker in enumerate(transcript_data.get('speakers', []))
                  if isinstance(speaker, str)}
        for index, raw_chunk in enumerate(transcript_data.get('chunks', [])):
            try:
                chunk = normalize_chunk(raw_chunk, index)
            except (ValueError, AttributeError):
                continue
            start_time, end_time = chunk['timestamp']
            speaker = chunk.get('speaker')
            if speaker and speaker not in colors:
                colors[speaker] = SPEAKER_COLORS[len(colors) % len(SPEAKER_COLORS)]
            chunks.append({
                'id': chunk['id'], 'speaker': speaker,
                'speaker_label': (speaker or 'Unknown speaker') if 'speaker' in chunk else None,
                'speaker_color': colors.get(speaker, '#64748b'),
                'start_seconds': start_time, 'end_seconds': end_time, 'text': chunk['text'],
                'start_time_formatted': self._seconds_to_timestamp(start_time),
                'end_time_formatted': self._seconds_to_timestamp(end_time)
            })
        
        return sorted(chunks, key=lambda chunk: chunk['start_seconds'])
    
    def _seconds_to_timestamp(self, seconds: float) -> str:
        """
        Convert seconds to HH:MM:SS,mmm format.
        """
        if seconds is None:
            return "00:00:00,000"
        
        return format_timestamp(float(seconds))
    
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
                    max-width: 1280px;
                    margin: 0 auto;
                    padding: 20px;
                    color: #333;
                }
                .page-layout {
                    display: grid;
                    grid-template-columns: minmax(0, 1fr) minmax(260px, 380px);
                    grid-template-areas: "content video";
                    gap: 28px;
                    align-items: start;
                }
                .content-column {
                    grid-area: content;
                    min-width: 0;
                }
                .video-container {
                    grid-area: video;
                    position: sticky;
                    top: 20px;
                    margin: 0;
                    padding: 14px;
                    background: #f8f9fa;
                    border-radius: 8px;
                    border: 1px solid #e5e7eb;
                }
                video, audio {
                    display: block;
                    width: 100%;
                    max-height: calc(100vh - 68px);
                    background: #111;
                    border-radius: 6px;
                }
                .topic {
                    margin: 0 0 28px;
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
                    margin: 0;
                    padding: 20px;
                    background: #f8f9fa;
                    border-radius: 8px;
                }
                .transcript-chunk {
                    display: block;
                    width: 100%;
                    text-align: left;
                    font: inherit;
                    color: inherit;
                    border: 1px solid #e5e7eb;
                    border-left: 4px solid var(--speaker-color, #64748b);
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
                    background: #dbeafe;
                    outline: 2px solid var(--speaker-color, #64748b);
                    outline-offset: -2px;
                }
                .transcript-chunk.overlapping {
                    background: #fef3c7;
                }
                .speaker-label {
                    color: var(--speaker-color, #64748b);
                    font-weight: 700;
                    margin-right: 8px;
                }
                .overlap-status {
                    color: #713f12;
                    font-weight: 600;
                }
                .transcript-timestamp {
                    font-family: monospace;
                    color: #666;
                    font-size: 0.9em;
                    margin-right: 10px;
                }
                .transcript-chunk.active .transcript-timestamp {
                    color: #374151;
                }
                @media (max-width: 860px) {
                    body {
                        padding: 14px;
                    }
                    .page-layout {
                        grid-template-columns: 1fr;
                        grid-template-areas:
                            "video"
                            "content";
                        gap: 24px;
                    }
                    .video-container {
                        position: static;
                    }
                    video {
                        width: auto;
                        max-width: 100%;
                        height: min(50vh, 520px);
                        max-height: 520px;
                        margin: 0 auto;
                    }
                }
            </style>
        </head>
        <body>
            <h1>Meeting Summary</h1>

            <div class="page-layout">
                <main class="content-column">
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
                <p id="overlap-status" class="overlap-status" role="status" hidden>Simultaneous speech</p>
                <div class="transcript">
                    {% for chunk in transcript %}
                    <button type="button" class="transcript-chunk"
                         data-segment-id="{{ chunk.id }}"
                         data-speaker="{{ chunk.speaker or '' }}"
                         style="--speaker-color: {{ chunk.speaker_color }}"
                         data-start="{{ chunk.start_seconds }}" 
                         data-end="{{ chunk.end_seconds }}"
                         onclick="seekToTime({{ chunk.start_seconds }})">
                        <span class="transcript-timestamp">{{ chunk.start_time_formatted }} – {{ chunk.end_time_formatted }}</span>
                        {% if chunk.speaker_label %}<span class="speaker-label">{{ chunk.speaker_label }}</span>{% endif %}
                        {{ chunk.text }}
                    </button>
                    {% endfor %}
                </div>
            </div>
            {% endif %}

                </main>

                <aside class="video-container">
                    {% if audio_only %}
                    <audio id="meeting-video" controls>
                        <source src="{{ video_rel_path }}" type="{{ media_type }}">
                        Your browser does not support audio playback.
                    </audio>
                    {% else %}
                    <video id="meeting-video" controls>
                        <source src="{{ video_rel_path }}" type="{{ media_type }}">
                        Your browser does not support video playback.
                    </video>
                    {% endif %}
                </aside>
            </div>

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
                let transcriptChunks = [];
                let previousActiveChunks = new Set();
                function updateTranscriptHighlight() {
                    const video = document.getElementById('meeting-video');
                    const currentTime = video.currentTime;
                    const activeSpeakers = new Set();
                    const activeChunks = new Set();
                    transcriptChunks.forEach(({element, start, end, speaker}) => {
                        if (currentTime >= start && currentTime < end) {
                            activeChunks.add(element);
                            if (speaker) activeSpeakers.add(speaker);
                        }
                    });
                    // Only touch active or previously active DOM nodes, even on long recordings.
                    previousActiveChunks.forEach(chunk => {
                        if (!activeChunks.has(chunk)) {
                            chunk.classList.remove('active');
                            chunk.classList.remove('overlapping');
                            chunk.removeAttribute('aria-current');
                        }
                    });
                    const overlapping = activeSpeakers.size > 1;
                    activeChunks.forEach(chunk => {
                        if (!previousActiveChunks.has(chunk)) {
                            chunk.classList.toggle('active', true);
                            chunk.setAttribute('aria-current', 'true');
                        }
                        chunk.classList.toggle('overlapping', overlapping);
                    });
                    previousActiveChunks = activeChunks;
                    const status = document.getElementById('overlap-status');
                    if (status) status.hidden = !overlapping;
                }


                // Set up video event listeners
                document.addEventListener('DOMContentLoaded', function() {
                    const video = document.getElementById('meeting-video');
                    if (video) {
                        transcriptChunks = Array.from(document.querySelectorAll('.transcript-chunk')).map(element => ({
                            element, start: parseFloat(element.dataset.start),
                            end: parseFloat(element.dataset.end), speaker: element.dataset.speaker
                        }));
                        // Update transcript highlight as video plays
                        video.addEventListener('timeupdate', updateTranscriptHighlight);
                        
                        // Also update on seeking
                        video.addEventListener('seeked', updateTranscriptHighlight);
                        video.addEventListener('seeking', updateTranscriptHighlight);
                        video.addEventListener('loadedmetadata', updateTranscriptHighlight);
                        // Short interjections can fall between timeupdate events.
                        let frame = null;
                        function tick() {
                            updateTranscriptHighlight();
                            frame = video.paused || video.ended ? null : requestAnimationFrame(tick);
                        }
                        video.addEventListener('play', function() {
                            if (frame === null) tick();
                        });
                        function stopHighlightLoop() {
                            if (frame !== null) cancelAnimationFrame(frame);
                            frame = null;
                            updateTranscriptHighlight();
                        }
                        video.addEventListener('pause', stopHighlightLoop);
                        video.addEventListener('ended', stopHighlightLoop);
                        updateTranscriptHighlight();
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
                transcript=transcript,
                media_type=mimetypes.guess_type(str(self.video_path))[0] or 'video/mp4',
                audio_only=(mimetypes.guess_type(str(self.video_path))[0] or '').startswith('audio/')
            )
