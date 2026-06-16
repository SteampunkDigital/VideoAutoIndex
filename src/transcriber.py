"""Backward-compatible default transcriber import.

The default pipeline still uses the Whisper implementation. Import the Canary
Qwen CoreML transcriber explicitly from src.transcriber_canary_qwen_coreml.
"""

from .transcriber_whisper import Transcriber

__all__ = ["Transcriber"]
