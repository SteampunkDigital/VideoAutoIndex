"""Backward-compatible default transcriber import.

The default pipeline uses the Whisper implementation.
"""

from .transcriber_whisper import Transcriber

__all__ = ["Transcriber"]
