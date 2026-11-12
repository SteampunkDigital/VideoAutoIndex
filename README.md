# Video Auto Index

Automatically process meeting videos to extract key moments, topics, and takeaways. The tool generates a navigable summary webpage with video chapters.

## Demo

View the GitHub Pages demo: https://steampunkdigital.github.io/VideoAutoIndex/

The demo uses `videos/sample.mp4`, a conversation about a 3D sushi scan, with
Nemotron transcription and diarization. Its reviewed speaker names are Narrator
and Aaron; you can try renaming speakers, editing phrases, and copying feedback JSON.

The demo is published from `docs/`, so GitHub Pages should be configured to deploy
from the `main` branch with `/docs` as the Pages folder.

## Features

- Extracts audio from video files
- Transcribes speech to text using insanely-fast-whisper
  - Uses Whisper large-v3 model by default for best accuracy
  - Optimized for both NVIDIA GPUs and Apple Silicon
  - Flash Attention 2 support for NVIDIA GPUs
  - Word-level timestamp support
- Supports Apple Speech and OpenAI speaker-diarized transcription
- Offers an experimental local speech.cpp transcription and speaker-attribution backend
- Selects transcription and summarization providers independently
- Preserves overlapping utterances and highlights all active speakers in HTML
- Analyzes content to identify:
  - Major topics with timestamps
  - Key moments within each topic
  - Actionable takeaways
- Adds chapter markers to the video
- Generates an interactive HTML summary
  - Clickable timestamps for video navigation
  - Organized by topics
  - Highlights key moments and takeaways

## Requirements

- Python 3.11+
- ffmpeg
- NVIDIA GPU or Apple Silicon Mac
- Conda (for environment management)

## Installation

1. Set up the conda environment:
   ```bash
   # Create and activate the conda environment
   conda env create -f environment.yml
   conda activate video-auto-index
   ```

   This installs all dependencies, including insanely-fast-whisper and a
   TorchCodec-compatible FFmpeg release. The pinned environment FFmpeg avoids
   incompatibilities with newer system or Homebrew FFmpeg releases.

2. Create a `.env` file for API-backed modes:
   ```bash
   cp .env.example .env
   ```

   Add the keys for the hosted model providers you plan to use:
   ```bash
   ANTHROPIC_API_KEY=your-anthropic-api-key
   OPENAI_API_KEY=your-openai-api-key
   ```

   Keys are resolved independently for the stages you run:
   - `--transcribe openai` or `--summarize openai` requires `OPENAI_API_KEY`.
   - `--summarize anthropic` requires `ANTHROPIC_API_KEY`.
   - Apple stages and Whisper do not require API keys.
   - `--skipto generate` requires no API keys or provider selection.

   Shell environment variables take precedence over values in `.env`.

## Usage

Process a video file:
```bash
python -m src.main meeting.mp4 --transcribe openai --summarize openai
```

Stage selection:
- `--transcribe whisper|apple|openai|speechcpp` selects speech recognition; defaults to `whisper`. Apple uses `SpeechTranscriber`; OpenAI uses `gpt-4o-transcribe-diarize`.
- `--summarize` selects topics, key moments, and takeaways; required unless using `--skipto generate`.
- `--transcribe-model` selects a backend-specific model: a Whisper model, the supported OpenAI diarization model, or Parakeet/Nemotron for speech.cpp.
- `speechcpp` handles recognition, diarization, and phrase attribution internally; it requires no API key or separate diarization flag.
- `--summarize-model` overrides the OpenAI or Anthropic summary model. Apple chooses its models automatically and does not accept model overrides.
- Startup output identifies the provider and model for each active stage.
- The former top-level `--openai`, `--anthropic`, and `--apple` flags have been replaced by these stage selections.

Transcription language:
- `--transcription-language en`: English transcription. This is the default.
- `--transcription-language ja`: Japanese transcription.
- In Apple Japanese mode, the tool automatically runs a second English `SpeechTranscriber` pass and selects a non-overlapping transcript timeline using confidence and simple text-quality scoring.
- Transcripts and subtitles stay in the spoken language. Topic names, key moments, and takeaways in `meeting_analysis.json` are generated in English.
- Apple transcript JSON chunks include `confidence` and `locale` when the Speech framework returns confidence attributes.

Whisper device defaults:
- Darwin/macOS: `mps`
- Windows/Linux: `0` for CPU/CUDA
- Use `--device-id DEVICE` to override the device for `--transcribe whisper`.

For example:
```bash
# Local Apple models; no API keys required
python -m src.main /path/to/video.mp4 --transcribe apple --summarize apple --output-dir output

# Whisper transcription plus OpenAI analysis
python -m src.main /path/to/video.mp4 --transcribe whisper --summarize openai --output-dir output

# Whisper transcription plus Claude analysis
python -m src.main /path/to/video.mp4 --transcribe whisper --summarize anthropic --output-dir output

# Speaker-diarized OpenAI transcription plus Claude summaries
python -m src.main /path/to/video.mp4 --transcribe openai --summarize anthropic

# Experimental local recognition and phrase attribution, with OpenAI summaries
python -m src.main /path/to/video.mp4 --transcribe speechcpp --summarize openai

# OpenAI at both stages, with an explicit summary model
python -m src.main /path/to/video.mp4 --transcribe openai --summarize openai --summarize-model gpt-6.1-terra

# Japanese native transcription plus English analysis
python -m src.main /path/to/video.mp4 --transcribe apple --summarize apple --transcription-language ja --output-dir output

# Shell wrapper forwards the same stage arguments to Python
./run.sh /path/to/video.mp4 --transcribe openai --summarize openai

# Regenerate existing artifacts without invoking AI or ffmpeg
python -m src.main /path/to/video.mp4 --skipto generate --output-dir output
```

This will:
1. Extract audio from the video
2. Transcribe the audio using the selected transcription provider
3. Analyze the meeting content for topics and key moments using the selected summarization provider
4. Generate an HTML summary page

The output directory will contain:
- `<video_name>_audio.wav`: Extracted audio file
- `audio_transcript.json`: Transcribed speech with timestamps
- `audio_subtitles.srt`: Generated subtitles
- `meeting_analysis.json`: Extracted topics, moments, and takeaways

Final web output is stored in:
- `<video_base_path>/<video_filename>_summary.html`

## Speaker diarization and overlaps

The OpenAI backend requests `diarized_json` with automatic server-side chunking.
It writes the existing `chunks` JSON structure with additional `id` and `speaker`
fields, and metadata identifying the backend, model, language, and schema version.
SRT cues include bracketed speaker labels. Both outputs preserve overlapping time
ranges. Legacy Whisper and Apple transcripts remain readable.

The HTML displays separate clickable utterances, speaker labels, and consistent
speaker colors. Every segment in `start <= playback time < end` is highlighted.
When multiple identified speakers are active, the page indicates simultaneous
speech. Unknown voices remain labeled unknown; colors alone do not identify speakers.

Uploads larger than the API limit are compressed to mono 16 kHz MP3 at 32 kbps.
If still too large, the recording is divided into non-overlapping 20-minute upload
windows and timestamps are shifted back to the original recording timeline.
Speaker labels then include `Part N /` because identity across separate requests
is unknown. Fixed window boundaries may split an utterance. Transcription quality
during cross-talk should be evaluated with representative recordings; diarization
does not guarantee that both voices are recovered.

`gpt-4o-transcribe-diarize` is a temporary backend: OpenAI lists its shutdown as
February 26, 2027. The backend rejects `gpt-transcribe` overrides because that model
does not currently provide the speaker labels and timestamps this pipeline needs.
A replacement needs a separate diarization/alignment stage or an API with those
capabilities. See the [OpenAI transcription guide](https://developers.openai.com/api/docs/guides/speech-to-text)
and [deprecation notice](https://developers.openai.com/api/docs/deprecations).

## Local speech.cpp evaluation

The experimental `speechcpp` backend has been exercised with speech.cpp **0.10.1**
on `test_data/audio.wav`. Install the matching executable from the
[upstream releases](https://github.com/nyosegawa/speech.cpp/releases) on PATH,
set `SPEECHCPP_BIN` to its executable path, or place the macOS release's executable
and accompanying library in `.build/speechcpp/`. This workspace uses the latter.

The backend uses Parakeet v3 for English, Silero VAD to recognize short speech
regions, and Nemotron-3-Diarization over the complete recording to maintain speaker
labels. Models are fetched and verified by speech.cpp on first use. The English
models require about 1.4 GB of downloads. The existing `--transcription-language ja`
selects Parakeet Japanese; that route has not yet been evaluated on a Japanese clip.

For a larger recognition model with native timestamp support, select Nemotron 3.5
Transcribe. This keeps the same VAD, recording-wide diarization, and HTML output.
Its default quantized weights download is approximately 19 GB; sufficient RAM and
disk space are required. Accent recognition improvements should be checked on the
actual recording before changing defaults.

```bash
python -m src.main meeting.mp4 --transcribe speechcpp --transcribe-model nemotron-3.5-transcribe --summarize openai
```

To repeat the short-clip evaluation without any summarization API calls:

```bash
python -m tools.evaluate_speechcpp test_data/audio.wav

# Evaluate the larger model separately
python -m tools.evaluate_speechcpp test_data/audio.wav --transcribe-model nemotron-3.5-transcribe --output-dir output/speechcpp-nemotron-eval
```

This writes JSON, SRT, a playable `transcript.html`, the copied evaluation audio,
and `evaluation.json` under `output/speechcpp-eval/`. The report records the runtime,
model names, input hash, and detected overlap ranges. The checked-in
`test_data/speechcpp_audio_result.json` is actual runtime output for regression
testing, not a manually labeled accuracy reference.

Phrase labels use temporal overlap with speaker intervals. A label needs coverage
of at least half the phrase and a lead of at least a quarter of its duration over
the next speaker; otherwise it is Unknown. This is a heuristic, not a calibrated
confidence score. Raw overlapping voice intervals are retained separately as
`speaker_segments` for attribution and diagnostics. The HTML shows all recognized
phrases, without a separate speaker-activity section. Every phrase whose time
range contains the playback time is highlighted, including overlapping phrases.
Transcript text is never duplicated to manufacture a second speaker's words.
Recognized phrase attribution and recovery of both voices during cross-talk still
need listening review before using this backend for full meetings.

## Transcript review and correction feedback

Generated pages support edits for the current page session:

- Click a speaker chip and type a name. Every phrase with that stable speaker ID
  updates together. Enter finishes; Escape cancels the current edit.
- Double-click phrase text to edit a word or range, or focus the phrase and press
  Enter to select the entire phrase. Enter finishes; Escape cancels.
- Click a timestamp to play that phrase. Selecting or editing text does not seek.
- Select text across phrases and use **Copy selected phrases** to copy complete
  selected phrases with their current speaker names and timestamps. **Copy
  transcript** copies the whole transcript; normal browser text selection and
  copying also remain available.

The **Transcript correction JSON** block at the bottom updates as edits are made.
It includes the media filename, source transcript SHA-256, model metadata, stable
speaker IDs with display names, and changed regions. Each changed region retains
its original segment ID, start/end seconds, original text, corrected text, and a
word-replacement hint scoped to that region. Restoring the original text removes
that region from the export. Unknown voices retain a null speaker ID.

Edits are kept in memory only; reload resets them. Use **Copy correction JSON**
before leaving the page to retain the feedback. The HTML embeds its editor script
and requires no server or browser storage.

Save the copied JSON to a file, then import it against the output directory that
contains the transcript used to generate that page:

```bash
./run.sh meeting.mp4 --skipto analyze --summarize openai --output-dir output --feedback feedback.json
```

`--feedback` requires `--skipto analyze`. It applies your **confirmed names and
exact text corrections**, then reruns summarization and HTML generation. It does
not run recognition again or send the word hints as a global ASR prompt. The
original `audio_transcript.json` and `audio_subtitles.srt` remain intact; reviewed
results are written as `audio_transcript.reviewed.json`,
`audio_subtitles.reviewed.srt`, `meeting_analysis.reviewed.json`, and
`<video_name>_reviewed_summary.html`. Speaker IDs stay stable; display names are
stored separately in `speaker_names`. Clearing a phrase explicitly removes it.

The importer validates the source transcript SHA-256, media filename, region IDs,
original text, timestamps, and speaker mappings before writing reviewed files.
A mismatch stops the import. Feedback exported from a reviewed page can be applied
again using the same command and output directory; its reviewed source fingerprint
is recognized too. Keep word hints scoped to their regions when experimenting with
future ASR retranscription.

## Output Format

The analysis JSON follows this structure:
```json
[
  {
    "topic": "Topic description",
    "timestamp": "HH:MM:SS,mmm",
    "key_moments": [
      {
        "description": "Key moment description",
        "timestamp": "HH:MM:SS,mmm"
      }
    ],
    "takeaways": [
      "Actionable takeaway 1",
      "Actionable takeaway 2"
    ]
  }
]
```

## Development

The project is organized into modular components:
- `video_processor.py`: Handles video/audio operations
- `transcriber.py`: Backward-compatible Whisper import
- `transcriber_openai.py`: OpenAI diarized transcription and upload preparation
- `transcriber_speechcpp.py`: Local recognition, diarization, and phrase attribution
- `transcript.py`: Transcript validation and JSON/SRT publication
- `transcriber_apple_speech.py`: Apple SpeechTranscriber wrapper for `--transcribe apple`
- `key_moments.py`: AI content analysis using Anthropic, OpenAI, or Apple Foundation Models
- `web_generator.py`: HTML summary generation
- `main.py`: Pipeline orchestration

Each component can be run independently, allowing for flexible processing pipelines.

## Testing

The project includes a comprehensive test suite covering all components:

### Running Tests

Run all tests:
```bash
pytest
```

Run with coverage report:
```bash
pytest --cov=src tests/
```

Run specific test categories:
```bash
# Unit tests only
pytest -v -m "not integration"

# Integration tests only
pytest -v -m "integration"
```

Playback behavior tests execute the generated JavaScript using Node.js when it is
available. OpenAI backend tests mock API responses and do not require a live key.
The optional `tests/transcript_editor_browser.cjs` check uses Playwright with an
installed Chrome to exercise actual editing, copy behavior, overlap highlighting,
and reload reset. It generates its own short fixture. For example, from the
activated Python environment:

```bash
npm install --prefix /tmp/videoautoindex-ui-tests playwright
NODE_PATH=/tmp/videoautoindex-ui-tests/node_modules PYTHON=python node tests/transcript_editor_browser.cjs
```

### Test Structure

- `test_video_processor.py`: Tests for video and audio processing
- `test_transcriber.py`: Tests for speech-to-text conversion
- `test_key_moments.py`: Tests for content analysis with API mocking
- `test_web_generator.py`: Tests for HTML generation
- `test_main.py`: Integration tests for the full pipeline

### Test Coverage

The test suite includes:
- Unit tests for each component
- Integration tests for the full pipeline
- API mocking for external services
- Fixture-based test data
- Error handling verification
- Edge case validation

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests for new functionality
5. Ensure all tests pass
6. Submit a pull request
