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
        self.subtitle_path = subtitle_path
        self.anthropic = Anthropic(api_key=os.environ.get('ANTHROPIC_API_KEY'))
        if not os.environ.get('ANTHROPIC_API_KEY'):
            raise ValueError("ANTHROPIC_API_KEY environment variable is required")

    def extract_key_moments(self) -> List[Dict]:
        """
        Extract key moments from the subtitle file using Claude.
        
        Returns:
            List of dictionaries containing key moments with their timestamps and descriptions
        """
        # Read the subtitle file
        with open(self.subtitle_path, 'r') as f:
            subtitle_content = f.read()

        # Prepare the prompt for Claude
        prompt = f"""Analyze this meeting transcript and identify the key moments. 
        For each key moment, extract the timestamp and provide a concise description.
        Format your response as a JSON array of objects with 'timestamp' and 'description' fields.
        Only include significant moments that represent important discussions, decisions, or transitions in the meeting.
        Ensure the timestamps match the exact SRT format from the transcript (HH:MM:SS,mmm).
        
        Example response format:
        [
            {{"timestamp": "00:01:15,000", "description": "Team agreed on new project timeline"}},
            {{"timestamp": "00:05:30,500", "description": "Budget constraints discussed and resolved"}}
        ]

        Transcript:
        {subtitle_content}

        Respond only with the JSON array, no other text.
        """

        # Call Claude API
        try:
            response = self.anthropic.messages.create(
                model="claude-3-opus-20240229",
                max_tokens=4096,
                temperature=0,
                system="You are a meeting analyzer that extracts key moments from transcripts. You only respond with properly formatted JSON.",
                messages=[{
                    "role": "user",
                    "content": prompt
                }]
            )
            
            # Parse the response
            key_moments = json.loads(response.content)
            
            # Validate the response format
            if not isinstance(key_moments, list):
                raise ValueError("Expected a list of key moments")
            
            for moment in key_moments:
                if not isinstance(moment, dict) or 'timestamp' not in moment or 'description' not in moment:
                    raise ValueError("Invalid key moment format")
                
                # Validate timestamp format
                self._validate_timestamp_format(moment['timestamp'])
            
            return key_moments
            
        except Exception as e:
            raise Exception(f"Failed to extract key moments: {str(e)}")

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
