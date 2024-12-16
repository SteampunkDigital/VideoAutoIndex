# key_moments.py
import json
import os
from typing import List, Dict
from anthropic import Anthropic

class KeyMomentsExtractor:
    def __init__(self, subtitle_path: str):
        """
        Initialize the key moments extractor.
        
        Args:
            subtitle_path: Path to the input subtitle file
        """
        if not os.path.exists(subtitle_path):
            raise FileNotFoundError(f"Subtitle file not found: {subtitle_path}")
            
        self.subtitle_path = subtitle_path
        self.anthropic = Anthropic(api_key=os.environ.get('ANTHROPIC_API_KEY'))
        if not os.environ.get('ANTHROPIC_API_KEY'):
            raise ValueError("ANTHROPIC_API_KEY environment variable is required")

    def extract_key_moments(self) -> List[Dict]:
        """
        Extract topics, key moments, and takeaways from the subtitle file using Claude.
        
        Returns:
            List of topic dictionaries containing:
            - topic: Brief topic description
            - timestamp: Start time of the topic
            - key_moments: List of important moments within this topic
            - takeaways: List of actionable takeaways from this topic
        """
        # Read the subtitle file
        with open(self.subtitle_path, 'r') as f:
            subtitle_content = f.read()

        # Prepare the prompt for Claude
        prompt = f"""Analyze this meeting transcript and break it down into major topics.
        For each topic, identify its key moments and extract actionable takeaways.
        Format your response as a JSON array where each object represents a topic section with this structure:

        [
            {{
                "topic": "Brief topic description",
                "timestamp": "HH:MM:SS,mmm",
                "key_moments": [
                    {{
                        "description": "Description of an important moment",
                        "timestamp": "HH:MM:SS,mmm"
                    }}
                ],
                "takeaways": [
                    "Actionable takeaway or key decision 1",
                    "Actionable takeaway or key decision 2"
                ]
            }}
        ]

        Important:
        - Each topic should be a distinct discussion point or agenda item
        - Timestamps must match the exact SRT format from the transcript (HH:MM:SS,mmm)
        - Key moments should capture significant points, decisions, or transitions
        - Takeaways should be actionable items or important conclusions
        - Keep descriptions concise but informative

        Transcript:
        {subtitle_content}

        Respond only with the JSON array."""

        # Call Claude API
        try:
            response = self.anthropic.messages.create(
                model="claude-3-5-sonnet-20241022",
                max_tokens=4096,  # Maximum allowed for Claude-3-Sonnet
                temperature=0,
                system="You are a meeting analyzer that breaks down discussions into topics, key moments, and takeaways. You only respond with properly formatted JSON.",
                messages=[{
                    "role": "user",
                    "content": prompt
                }]
            )

            try:
                # Parse the response content as JSON
                topics = json.loads(response.content[0].text)
            except (json.JSONDecodeError, IndexError, AttributeError) as e:
                print(f"Raw response content: {response.content}")
                raise Exception(f"Failed to parse API response: {str(e)}")

            # Validate the response format
            if not isinstance(topics, list):
                raise ValueError("Expected a list of topics")
            
            for topic in topics:
                if not isinstance(topic, dict):
                    raise ValueError("Invalid topic format")
                    
                required_fields = ['topic', 'timestamp', 'key_moments', 'takeaways']
                if not all(field in topic for field in required_fields):
                    raise ValueError(f"Missing required fields in topic: {required_fields}")
                
                # Validate timestamp format
                self._validate_timestamp_format(topic['timestamp'])
                
                # Validate key_moments
                if not isinstance(topic['key_moments'], list):
                    raise ValueError("Expected list of key moments")
                for moment in topic['key_moments']:
                    if not isinstance(moment, dict):
                        raise ValueError("Invalid key moment format")
                    if 'description' not in moment or 'timestamp' not in moment:
                        raise ValueError("Missing required fields in key moment")
                    self._validate_timestamp_format(moment['timestamp'])
                
                # Validate takeaways
                if not isinstance(topic['takeaways'], list):
                    raise ValueError("Expected list of takeaways")
                for takeaway in topic['takeaways']:
                    if not isinstance(takeaway, str):
                        raise ValueError("Invalid takeaway format")
            
            return topics
            
        except Exception as e:
            raise Exception(f"Failed to parse API response: {str(e)}")

    def _validate_timestamp_format(self, timestamp: str) -> None:
        """
        Validate that a timestamp string matches the SRT format (HH:MM:SS,mmm).
        
        Args:
            timestamp: Timestamp string to validate
            
        Raises:
            ValueError: If timestamp format is invalid
        """
        try:
            # Split into time and milliseconds
            time_parts = timestamp.split(',')
            if len(time_parts) != 2:
                raise ValueError
                
            # Validate milliseconds
            if not time_parts[1].isdigit() or len(time_parts[1]) != 3:
                raise ValueError
                
            # Split time into hours, minutes, seconds
            hours, minutes, seconds = time_parts[0].split(':')
            
            # Validate each component
            if not (hours.isdigit() and minutes.isdigit() and seconds.isdigit()):
                raise ValueError
            if not (len(hours) == 2 and len(minutes) == 2 and len(seconds) == 2):
                raise ValueError
            if not (0 <= int(hours) <= 99 and 0 <= int(minutes) <= 59 and 0 <= int(seconds) <= 59):
                raise ValueError
                
        except (ValueError, IndexError):
            raise ValueError(
                f"Invalid timestamp format: {timestamp}. Expected format: HH:MM:SS,mmm"
            )

    def _parse_timestamp(self, timestamp: str) -> float:
        """
        Convert SRT timestamp format (HH:MM:SS,mmm) to seconds.
        
        Args:
            timestamp: Timestamp string in SRT format
        
        Returns:
            Time in seconds as a float
        """
        # Split into time and milliseconds
        time_str, milliseconds = timestamp.split(',')
        hours, minutes, seconds = time_str.split(':')
        
        total_seconds = (
            int(hours) * 3600 +
            int(minutes) * 60 +
            int(seconds) +
            int(milliseconds) / 1000
        )
        
        return total_seconds
