# key_moments.py
import json
import os
from typing import List, Dict, Optional, Literal
from anthropic import Anthropic
from openai import OpenAI
import openai
import anthropic

class KeyMomentsExtractor:
    def __init__(self, subtitle_path: str, api_provider: Literal["anthropic", "openai"], api_key: str):
        """
        Initialize the key moments extractor.
        
        Args:
            subtitle_path: Path to the input subtitle file
            api_provider: Which API to use ("anthropic" or "openai")
            api_key: API key for the specified provider
        """
        if not os.path.exists(subtitle_path):
            raise FileNotFoundError(f"Subtitle file not found: {subtitle_path}")
            
        self.subtitle_path = subtitle_path
        self.api_provider = api_provider
        
        if api_provider == "anthropic":
            self.anthropic = Anthropic(api_key=api_key)
            self.openai = None
        elif api_provider == "openai":
            self.openai = OpenAI(api_key=api_key)
            self.anthropic = None
            self.openai_model = self._get_best_openai_model()
        else:
            raise ValueError("api_provider must be 'anthropic' or 'openai'")

    def _get_best_openai_model(self) -> str:
        """
        Get the best available OpenAI model from the API.
        Prioritizes: gpt-5, o3, gpt-4o
        
        Returns:
            Model name string
        """
        try:
            models_response = self.openai.models.list()
            available_models = [model.id for model in models_response.data]
            
            # Preferred model order - top 3 models only
            preferred_models = ["gpt-5", "o3", "gpt-4o"]
            
            for model in preferred_models:
                if model in available_models:
                    print(f"Using OpenAI model: {model}")
                    return model
            
            # Fallback - should not happen given the models list
            raise ValueError("None of the preferred OpenAI models (gpt-5, o3, gpt-4o) are available")
            
        except openai.AuthenticationError as e:
            raise Exception(f"Cannot access OpenAI models - authentication failed. Please check your API key: {str(e)}")
        except openai.RateLimitError as e:
            raise Exception(f"Cannot access OpenAI models - rate limit exceeded. Please check your usage: {str(e)}")
        except Exception as e:
            print(f"Warning: Error fetching OpenAI models, using fallback: {e}")
            return "gpt-4o"  # Safe fallback
    
    def extract_key_moments(self) -> List[Dict]:
        """
        Extract topics, key moments, and takeaways from the subtitle file using AI.
        
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

        # Call AI API based on provider
        try:
            if self.api_provider == "anthropic":
                try:
                    # Use streaming for long operations (required for >10 min operations)
                    response_text = ""
                    with self.anthropic.messages.stream(
                        model="claude-opus-4-1-20250805",  # Latest and most capable Claude model
                        max_tokens=16384,
                        system="You are a meeting analyzer that breaks down discussions into topics, key moments, and takeaways. You only respond with properly formatted JSON.",
                        messages=[{
                            "role": "user",
                            "content": prompt
                        }]
                    ) as stream:
                        for text in stream.text_stream:
                            response_text += text
                            print(".", end="", flush=True)  # Show progress
                    print()  # New line after streaming
                except anthropic.RateLimitError as e:
                    raise Exception(f"Anthropic API rate limit exceeded. Please check your usage and billing: {str(e)}")
                except anthropic.AuthenticationError as e:
                    raise Exception(f"Anthropic API authentication failed. Please check your API key: {str(e)}")
                except anthropic.APIConnectionError as e:
                    raise Exception(f"Failed to connect to Anthropic API. Please check your internet connection: {str(e)}")
                except anthropic.InternalServerError as e:
                    raise Exception(f"Anthropic API internal server error. Please try again later: {str(e)}")
                except anthropic.BadRequestError as e:
                    raise Exception(f"Invalid request to Anthropic API: {str(e)}")
                except Exception as e:
                    raise Exception(f"Unexpected Anthropic API error: {str(e)}")
            else:  # OpenAI
                try:
                    # Use max_completion_tokens for newer models, max_tokens for older ones
                    api_params = {
                        "model": self.openai_model,
                        "messages": [
                            {"role": "system", "content": "You are a meeting analyzer that breaks down discussions into topics, key moments, and takeaways. You only respond with properly formatted JSON."},
                            {"role": "user", "content": prompt}
                        ],
                        "max_completion_tokens": 16384
                    }
                    
                    response = self.openai.chat.completions.create(**api_params)
                    response_text = response.choices[0].message.content
                except openai.RateLimitError as e:
                    raise Exception(f"OpenAI API rate limit exceeded or quota reached. Please check your usage and billing: {str(e)}")
                except openai.AuthenticationError as e:
                    raise Exception(f"OpenAI API authentication failed. Please check your API key: {str(e)}")
                except openai.APIConnectionError as e:
                    raise Exception(f"Failed to connect to OpenAI API. Please check your internet connection: {str(e)}")
                except openai.InternalServerError as e:
                    raise Exception(f"OpenAI API internal server error. Please try again later: {str(e)}")
                except openai.BadRequestError as e:
                    raise Exception(f"Invalid request to OpenAI API: {str(e)}")
                except Exception as e:
                    raise Exception(f"Unexpected OpenAI API error: {str(e)}")

            try:
                # Parse the response content as JSON
                topics = json.loads(response_text)
            except (json.JSONDecodeError, IndexError, AttributeError) as e:
                print(f"Raw response content: {response_text}")
                raise Exception(f"Failed to parse API response as JSON: {str(e)}")

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
            # Re-raise with context if it's already a handled API error
            if "API" in str(e) or "rate limit" in str(e).lower() or "quota" in str(e).lower():
                raise
            # Otherwise, wrap as general processing error
            raise Exception(f"Failed to process meeting content: {str(e)}")

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
