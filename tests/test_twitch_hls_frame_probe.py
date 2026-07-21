from datetime import datetime, timezone
import io
import json
from pathlib import Path
import subprocess
from unittest.mock import Mock

import pytest

from scripts.twitch_hls_frame_probe import (
    collect_frames,
    command_parts,
    file_observation,
    redact_ephemeral_stream_urls,
)


def test_command_parts_supports_python_module_command():
    assert command_parts("python3 -m streamlink") == ["python3", "-m", "streamlink"]


def test_command_parts_rejects_empty_command():
    with pytest.raises(ValueError, match="must not be empty"):
        command_parts("  ")


def test_file_observation_uses_utc_mtime(tmp_path: Path):
    path = tmp_path / "frame.jpg"
    path.write_bytes(b"frame")
    timestamp = datetime(2026, 7, 21, 7, 15, 45, tzinfo=timezone.utc).timestamp()
    path.touch()
    path.chmod(0o644)
    import os

    os.utime(path, (timestamp, timestamp))

    assert file_observation(path) == {
        "path": str(path),
        "bytes": 5,
        "observedAt": "2026-07-21T07:15:45Z",
    }


def test_redact_ephemeral_stream_urls_preserves_capabilities():
    metadata = {
        "plugin": "twitch",
        "streams": {
            "1080p60": {"type": "hls", "url": "https://signed", "master": "https://master"}
        },
    }

    assert redact_ephemeral_stream_urls(metadata) == {
        "plugin": "twitch",
        "streams": {
            "1080p60": {
                "type": "hls",
                "url": "[redacted_ephemeral_hls_url]",
                "master": "[redacted_ephemeral_hls_url]",
            }
        },
    }


def test_collect_frames_records_ffmpeg_timeout(monkeypatch, tmp_path: Path):
    metadata = {"plugin": "twitch", "streams": {"best": {"url": "signed"}}}
    calls = 0

    def fake_run(command, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            return subprocess.CompletedProcess(command, 0, json.dumps(metadata), "")
        frame_pattern = Path(command[-1])
        Path(str(frame_pattern).replace("%02d", "01")).write_bytes(b"frame")
        raise subprocess.TimeoutExpired(command, kwargs["timeout"], stderr=b"")

    stream_process = Mock()
    stream_process.stdout = io.BytesIO(b"stream")
    stream_process.wait.return_value = 0
    monkeypatch.setattr("scripts.twitch_hls_frame_probe.require_command", lambda _: None)
    monkeypatch.setattr("scripts.twitch_hls_frame_probe.subprocess.run", fake_run)
    monkeypatch.setattr("scripts.twitch_hls_frame_probe.subprocess.Popen", lambda *args, **kwargs: stream_process)

    result = collect_frames(
        channel_url="https://www.twitch.tv/example",
        output_dir=tmp_path,
        label="timeout",
        quality="best",
        sample_count=2,
        interval_sec=15,
        timeout_sec=20,
        streamlink_command=["streamlink"],
        ffmpeg_command=["ffmpeg"],
    )

    assert result["success"] is False
    assert result["ffmpegTimedOut"] is True
    assert result["ffmpegReturnCode"] == 124
    assert result["failureReason"] == "ffmpeg timed out after 20s; captured 1 of 2 frames"
    assert Path(result["reportPath"]).is_file()
