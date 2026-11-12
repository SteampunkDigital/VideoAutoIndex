"""Run the local transcription backend on a short clip without summary API calls.

Usage: python -m tools.evaluate_speechcpp [test_data/audio.wav]
"""

import argparse
import hashlib
import json
import shutil
import subprocess
import time
import wave
from pathlib import Path

from src.transcriber_speechcpp import SpeechCppTranscriber, speech_executable
from src.web_generator import WebGenerator


def overlap_intervals(timeline):
    """Return exact concurrent-voice ranges, using half-open intervals."""
    boundaries = sorted({t for span in timeline for t in span['timestamp']})
    overlaps = []
    for start, end in zip(boundaries, boundaries[1:]):
        speakers = sorted({span['speaker'] for span in timeline
                           if span['timestamp'][0] < end and span['timestamp'][1] > start})
        if len(speakers) < 2:
            continue
        if overlaps and overlaps[-1]['end'] == start and overlaps[-1]['speakers'] == speakers:
            overlaps[-1]['end'] = end
        else:
            overlaps.append({'start': start, 'end': end, 'speakers': speakers})
    return overlaps


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('audio_path', nargs='?', default='test_data/audio.wav')
    parser.add_argument('--output-dir', default='output/speechcpp-eval')
    parser.add_argument('--transcribe-model', help='speech.cpp recognition model (default: Parakeet v3)')
    args = parser.parse_args(argv)
    source, output = Path(args.audio_path).resolve(), Path(args.output_dir).resolve()
    output.mkdir(parents=True, exist_ok=True)
    with wave.open(str(source), 'rb') as audio:
        duration = audio.getnframes() / audio.getframerate()
    started = time.monotonic()
    transcript, subtitles = output / 'audio_transcript.json', output / 'audio_subtitles.srt'
    SpeechCppTranscriber(source, model_name=args.transcribe_model).transcribe(transcript, subtitles)
    elapsed = time.monotonic() - started
    data = json.loads(transcript.read_text(encoding='utf-8'))
    media = output / 'evaluation_audio.wav'
    if source != media:
        shutil.copyfile(source, media)
    # An empty analysis creates a transcript-only page, without inventing a summary.
    analysis = output / 'meeting_analysis.json'
    analysis.write_text('[]\n', encoding='utf-8')
    page = Path(WebGenerator(analysis, media, transcript).generate(output, 'transcript.html'))
    html = page.read_text(encoding='utf-8').replace('Meeting Summary', 'Speech.cpp Transcript Evaluation')
    page.write_text(html, encoding='utf-8')
    report = {
        'audio': str(source), 'audio_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
        'duration_seconds': duration, 'elapsed_seconds': round(elapsed, 3),
        'runtime': subprocess.run([speech_executable(), '--version'], check=True,
                                  capture_output=True, text=True).stdout.strip(),
        'metadata': data['metadata'], 'speakers': data['speakers'],
        'phrase_count': len(data['chunks']),
        'unknown_phrase_count': sum(c['speaker'] is None for c in data['chunks']),
        'detected_overlaps': overlap_intervals(data['speaker_segments']),
        'manual_speaker_accuracy': 'not_evaluated',
        'overlapping_phrase_recovery': 'not_verified',
    }
    (output / 'evaluation.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(f"Evaluation page: {page}")
    print(f"{len(data['speakers'])} detected speakers; {len(data['chunks'])} phrases; "
          f"{len(report['detected_overlaps'])} detected overlapping ranges")


if __name__ == '__main__':
    main()
