import json
import os
import subprocess
from pathlib import Path
from unittest.mock import Mock

import pytest

from src.main import create_transcriber, main, process_video


@pytest.fixture
def cli(monkeypatch):
    monkeypatch.setattr("src.main.load_env_file", lambda: None)
    monkeypatch.setattr("src.main.check_python_dependencies", lambda: True)
    monkeypatch.setattr("src.main.check_ffmpeg", lambda: True)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    pipeline = Mock()
    monkeypatch.setattr("src.main.process_video", pipeline)
    return pipeline


def test_independent_stage_keys_and_models(cli, monkeypatch, capsys):
    monkeypatch.setenv("OPENAI_API_KEY", "transcription-key")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "summary-key")
    main(["video.mp4", "--transcribe", "openai", "--summarize", "anthropic",
          "--summarize-model", "custom-claude"])
    kwargs = cli.call_args.kwargs
    assert kwargs["transcriber_name"] == "openai"
    assert kwargs["api_provider"] == "anthropic"
    assert kwargs["transcribe_api_key"] == "transcription-key"
    assert kwargs["api_key"] == "summary-key"
    assert kwargs["summarize_model"] == "custom-claude"
    output = capsys.readouterr().out
    assert "Transcription: openai / gpt-4o-transcribe-diarize" in output
    assert "Summarization: anthropic / custom-claude" in output
    assert "transcription-key" not in output and "summary-key" not in output


def test_whisper_is_default_and_can_override_model(cli, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "summary-key")
    main(["video.mp4", "--summarize", "openai", "--transcribe-model", "openai/whisper-base"])
    assert cli.call_args.kwargs["transcriber_name"] == "whisper"
    assert cli.call_args.kwargs["transcribe_model"] == "openai/whisper-base"
    assert cli.call_args.kwargs["transcribe_api_key"] is None


def test_local_stages_need_no_keys(cli):
    main(["video.mp4", "--transcribe", "apple", "--summarize", "apple"])
    assert cli.call_args.kwargs["api_key"] is None
    assert cli.call_args.kwargs["transcribe_api_key"] is None


def test_speechcpp_is_a_complete_local_transcription_backend(cli, capsys):
    main(["video.mp4", "--transcribe", "speechcpp", "--summarize", "apple"])
    assert cli.call_args.kwargs['transcriber_name'] == 'speechcpp'
    assert cli.call_args.kwargs['transcribe_api_key'] is None
    assert 'speechcpp / parakeet-tdt-0.6b-v3' in capsys.readouterr().out


def test_speechcpp_stronger_model_override(cli, capsys):
    main(['video.mp4', '--transcribe', 'speechcpp', '--transcribe-model',
          'nemotron-3.5-transcribe', '--summarize', 'apple'])
    assert cli.call_args.kwargs['transcribe_model'] == 'nemotron-3.5-transcribe'
    assert 'speechcpp / nemotron-3.5-transcribe' in capsys.readouterr().out


def test_generate_requires_no_provider_keys_or_ffmpeg(cli, monkeypatch):
    monkeypatch.setattr("src.main.check_ffmpeg", lambda: pytest.fail("ffmpeg is unused"))
    main(["video.mp4", "--skipto", "generate"])
    assert cli.called
    assert cli.call_args.kwargs["api_key"] is None


def test_analyze_does_not_validate_skipped_transcription(cli, monkeypatch):
    monkeypatch.setattr("src.main.check_ffmpeg", lambda: pytest.fail("ffmpeg is unused"))
    main(["video.mp4", "--skipto", "analyze", "--transcribe", "openai", "--summarize", "apple"])
    assert cli.call_args.kwargs["transcribe_api_key"] is None


def test_feedback_cli_uses_existing_transcript(cli, monkeypatch):
    monkeypatch.setattr('src.main.check_ffmpeg', lambda: pytest.fail('ffmpeg is unused'))
    main(['meeting.mp4', '--skipto', 'analyze', '--feedback', 'feedback.json', '--summarize', 'apple'])
    assert cli.call_args.kwargs['feedback_path'] == 'feedback.json'
    assert cli.call_args.kwargs['transcribe_api_key'] is None


def test_feedback_cannot_silently_start_new_transcription(cli, capsys):
    with pytest.raises(SystemExit):
        main(['meeting.mp4', '--feedback', 'feedback.json', '--summarize', 'apple'])
    assert '--feedback requires --skipto analyze' in capsys.readouterr().err
    cli.assert_not_called()


@pytest.mark.parametrize("arguments,error", [
    ([], "--summarize is required"),
    (["--transcribe", "openai", "--summarize", "apple"], "OPENAI_API_KEY"),
    (["--summarize", "openai"], "OPENAI_API_KEY"),
    (["--summarize", "anthropic"], "ANTHROPIC_API_KEY"),
    (["--transcribe", "apple", "--transcribe-model", "x", "--summarize", "apple"], "--transcribe-model"),
    (["--summarize", "apple", "--summarize-model", "x"], "--summarize-model"),
    (["--transcribe", "openai", "--transcribe-model", "gpt-transcribe", "--summarize", "apple"],
     "speaker labels and timestamps"),
    (["--openai"], "unrecognized arguments"),
])
def test_cli_fails_before_running_stages(cli, arguments, error, capsys):
    with pytest.raises(SystemExit) as failure:
        main(["video.mp4", *arguments])
    assert failure.value.code == 2
    assert error in capsys.readouterr().err
    cli.assert_not_called()


def test_openai_transcriber_factory(tmp_path, monkeypatch):
    source = tmp_path / "audio.wav"
    source.touch()
    factory = Mock()
    monkeypatch.setattr("src.transcriber_openai.OpenAITranscriber", factory)
    create_transcriber(str(source), "openai", api_key="transcription-key", transcription_language="ja")
    factory.assert_called_once_with(str(source), api_key="transcription-key",
                                    model_name="gpt-4o-transcribe-diarize", language="ja")


def test_pipeline_transcribes_and_summarizes_with_different_providers(tmp_path, monkeypatch):
    video = tmp_path / "video.mp4"
    video.touch()
    output = tmp_path / "output"
    output.mkdir()
    (output / "video_audio.wav").touch()
    def transcribe(json_path, subtitle_path):
        from src.transcript import write_transcript
        write_transcript({"speakers": ["A", "B"], "chunks": [
            {"timestamp": [0, 4], "text": "Hello", "speaker": "A"},
            {"timestamp": [2, 5], "text": "Yes", "speaker": "B"},
        ]}, json_path, subtitle_path)
    backend = Mock()
    backend.transcribe.side_effect = transcribe
    factory = Mock(return_value=backend)
    monkeypatch.setattr("src.main.create_transcriber", factory)
    extractor = Mock()
    extractor.extract_key_moments.return_value = []
    summary_factory = Mock(return_value=extractor)
    monkeypatch.setattr("src.main.KeyMomentsExtractor", summary_factory)
    process_video(str(video), str(output), skip_to="transcribe", api_provider="anthropic",
                  api_key="summary-key", transcriber_name="openai", transcribe_api_key="speech-key",
                  summarize_model="custom-claude")
    assert factory.call_args.args[1] == "openai"
    assert factory.call_args.kwargs["api_key"] == "speech-key"
    assert summary_factory.call_args.kwargs == {
        "api_provider": "anthropic", "api_key": "summary-key", "model_name": "custom-claude"}
    html = (tmp_path / "video_summary.html").read_text()
    assert 'data-speaker="A"' in html and 'data-speaker="B"' in html
    assert json.loads((output / "audio_transcript.json").read_text())["chunks"][1]["timestamp"] == [2, 5]


def test_generation_pipeline_does_not_construct_models(tmp_path, monkeypatch):
    video = tmp_path / "video.mp4"
    video.touch()
    (tmp_path / "meeting_analysis.json").write_text("[]")
    (tmp_path / "audio_transcript.json").write_text('{"chunks": []}')
    monkeypatch.setattr("src.main.create_transcriber", lambda *a, **k: pytest.fail("Unused transcriber"))
    monkeypatch.setattr("src.main.KeyMomentsExtractor", lambda *a, **k: pytest.fail("Unused summary model"))
    process_video(str(video), str(tmp_path), skip_to="generate")
    assert "Meeting Summary" in (tmp_path / "video_summary.html").read_text()


def test_shell_wrapper_forwards_stage_options_and_quoted_paths(tmp_path):
    executables = tmp_path / "bin"
    executables.mkdir()
    for name, content in {
        "conda": "#!/bin/bash\nexit 0\n",
        "python": '#!/bin/bash\nprintf "%s\\n" "$@"\n',
    }.items():
        executable = executables / name
        executable.write_text(content)
        executable.chmod(0o755)
    arguments = ["meeting with spaces.mp4", "--transcribe", "openai", "--summarize", "anthropic"]
    wrapper = Path(__file__).resolve().parents[1] / "run.sh"
    result = subprocess.run(["bash", str(wrapper), *arguments], text=True, capture_output=True,
                            env={**os.environ, "PATH": f"{executables}:{os.environ['PATH']}"}, check=True)
    assert result.stdout.splitlines() == ["-m", "src.main", *arguments]
