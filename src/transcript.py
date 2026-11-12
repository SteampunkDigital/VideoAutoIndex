"""Shared transcript validation and SRT output; overlapping cues are intentional."""

import json
import math
import os
import shutil
import tempfile
from pathlib import Path


def normalize_chunk(chunk, index=0):
    """Validate a chunk without imposing a non-overlapping timeline."""
    times = chunk.get("timestamp")
    if not isinstance(times, (list, tuple)) or len(times) != 2:
        raise ValueError("Transcript chunk requires a [start, end] timestamp")
    if any(isinstance(t, bool) or not isinstance(t, (int, float)) or not math.isfinite(t) for t in times):
        raise ValueError("Transcript timestamps must be finite numbers")
    start, end = times
    if start < 0 or end <= start:
        raise ValueError("Transcript timestamps require 0 <= start < end")
    if not isinstance(chunk.get("text"), str):
        raise ValueError("Transcript text must be a string")
    speaker = chunk.get("speaker")
    if speaker is not None and (not isinstance(speaker, str) or not speaker.strip()):
        raise ValueError("Transcript speaker must be a nonempty string or null")
    return {**chunk, "id": str(chunk.get("id", f"segment-{index}")),
            "timestamp": [float(start), float(end)], "text": chunk["text"].strip()}


def format_timestamp(seconds):
    """Round once to milliseconds, including carry into minutes and hours."""
    milliseconds = round(seconds * 1000)
    seconds, milliseconds = divmod(milliseconds, 1000)
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{milliseconds:03d}"


def transcript_to_srt(chunks):
    cues = []
    for index, chunk in enumerate(chunks, 1):
        start, end = chunk["timestamp"]
        text = " ".join(chunk["text"].split())
        if "speaker" in chunk:
            text = f"[{chunk['speaker'] or 'Unknown speaker'}] {text}"
        cues.append(f"{index}\n{format_timestamp(start)} --> {format_timestamp(end)}\n{text}\n")
    return "\n".join(cues)


def write_transcript(data, transcript_path, subtitle_path):
    """Stage both outputs before publishing; restore old files on rename failure."""
    chunks = [normalize_chunk(chunk, i) for i, chunk in enumerate(data["chunks"])]
    chunks.sort(key=lambda chunk: chunk["timestamp"][0])
    data = {**data, "chunks": chunks}
    outputs = [(Path(subtitle_path), transcript_to_srt(chunks)),
               (Path(transcript_path), json.dumps(data, ensure_ascii=False, indent=2))]
    if outputs[0][0].resolve() == outputs[1][0].resolve():
        raise ValueError("Transcript and subtitle paths must be different")
    staged, backups, published = {}, {}, []
    try:
        for path, content in outputs:
            path.parent.mkdir(parents=True, exist_ok=True)
            fd, temporary = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
            staged[path] = Path(temporary)
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                stream.write(content)
            if path.exists():
                fd, backup = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.backup.")
                os.close(fd)
                backups[path] = Path(backup)
                shutil.copyfile(path, backup)
        for path, _ in outputs:
            os.replace(staged[path], path)
            published.append(path)
    except OSError:
        for path in reversed(published):
            if path in backups:
                os.replace(backups[path], path)
            else:
                path.unlink(missing_ok=True)
        raise
    finally:
        for path in (*staged.values(), *backups.values()):
            path.unlink(missing_ok=True)
