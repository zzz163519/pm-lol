#!/usr/bin/env python3
"""Capture timestamped frames from a public Twitch live channel for Phase 0 evidence."""

from __future__ import annotations

import argparse
import json
import shlex
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def command_parts(value: str) -> list[str]:
    parts = shlex.split(value)
    if not parts:
        raise ValueError("command must not be empty")
    return parts


def require_command(parts: list[str]) -> None:
    executable = parts[0]
    if Path(executable).is_file() or shutil.which(executable):
        return
    raise FileNotFoundError(f"required executable not found: {executable}")


def file_observation(path: Path) -> dict[str, Any]:
    stat = path.stat()
    observed_at = datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat().replace("+00:00", "Z")
    return {"path": str(path), "bytes": stat.st_size, "observedAt": observed_at}


def redact_ephemeral_stream_urls(metadata: dict[str, Any]) -> dict[str, Any]:
    """Keep stream capabilities while excluding signed HLS URLs and embedded IP data."""
    streams = metadata.get("streams")
    if not isinstance(streams, dict):
        return metadata
    for stream in streams.values():
        if not isinstance(stream, dict):
            continue
        for key in ("url", "master"):
            if key in stream:
                stream[key] = "[redacted_ephemeral_hls_url]"
    return metadata


def collect_frames(
    *,
    channel_url: str,
    output_dir: Path,
    label: str,
    quality: str,
    sample_count: int,
    interval_sec: int,
    timeout_sec: int,
    streamlink_command: list[str],
    ffmpeg_command: list[str],
) -> dict[str, Any]:
    require_command(streamlink_command)
    require_command(ffmpeg_command)
    if sample_count < 1:
        raise ValueError("sample_count must be at least 1")
    if interval_sec < 1:
        raise ValueError("interval_sec must be at least 1")

    output_dir.mkdir(parents=True, exist_ok=True)
    tag = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    metadata_path = output_dir / f"twitch-{label}-{tag}-stream.json"
    report_path = output_dir / f"twitch-{label}-{tag}-probe.json"
    frame_pattern = output_dir / f"twitch-{label}-{tag}-%02d.jpg"
    started_at = utc_now()

    metadata_run = subprocess.run(
        [*streamlink_command, "--json", channel_url],
        check=False,
        capture_output=True,
        text=True,
        timeout=min(timeout_sec, 60),
    )
    if metadata_run.returncode != 0:
        raise RuntimeError(f"stream metadata failed: {metadata_run.stderr.strip()}")
    metadata = redact_ephemeral_stream_urls(json.loads(metadata_run.stdout))
    metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    stream_process = subprocess.Popen(
        [*streamlink_command, "--stdout", "--loglevel", "error", channel_url, quality],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    )
    assert stream_process.stdout is not None
    ffmpeg_timed_out = False
    ffmpeg_return_code = 0
    ffmpeg_stderr = ""
    try:
        try:
            ffmpeg_run = subprocess.run(
                [
                    *ffmpeg_command,
                    "-y",
                    "-loglevel",
                    "error",
                    "-i",
                    "pipe:0",
                    "-vf",
                    f"fps=1/{interval_sec}",
                    "-frames:v",
                    str(sample_count),
                    str(frame_pattern),
                ],
                stdin=stream_process.stdout,
                check=False,
                capture_output=True,
                timeout=timeout_sec,
            )
            ffmpeg_return_code = ffmpeg_run.returncode
            ffmpeg_stderr = ffmpeg_run.stderr.decode("utf-8", errors="replace").strip()
        except subprocess.TimeoutExpired as exc:
            ffmpeg_timed_out = True
            ffmpeg_return_code = 124
            stderr = exc.stderr or b""
            ffmpeg_stderr = stderr.decode("utf-8", errors="replace").strip()
    finally:
        stream_process.stdout.close()
        stream_process.terminate()
        try:
            stream_process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            stream_process.kill()
            stream_process.wait(timeout=5)

    frames = sorted(output_dir.glob(f"twitch-{label}-{tag}-*.jpg"))
    result = {
        "channelUrl": channel_url,
        "quality": quality,
        "startedAt": started_at,
        "endedAt": utc_now(),
        "requestedSampleCount": sample_count,
        "intervalSec": interval_sec,
        "ffmpegReturnCode": ffmpeg_return_code,
        "ffmpegTimedOut": ffmpeg_timed_out,
        "metadataPath": str(metadata_path),
        "frames": [file_observation(path) for path in frames],
        "success": ffmpeg_return_code == 0 and len(frames) == sample_count,
        "failureReason": None,
    }
    if not result["success"]:
        if ffmpeg_timed_out:
            result["failureReason"] = (
                f"ffmpeg timed out after {timeout_sec}s; captured {len(frames)} of {sample_count} frames"
            )
        else:
            result["failureReason"] = ffmpeg_stderr or f"captured {len(frames)} of {sample_count} frames"
    report_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    result["reportPath"] = str(report_path)
    return result


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--channel-url", required=True)
    parser.add_argument("--label", required=True, help="Filesystem-safe match label.")
    parser.add_argument("--output-dir", default="docs/source-spike")
    parser.add_argument("--quality", default="best")
    parser.add_argument("--sample-count", type=int, default=3)
    parser.add_argument("--interval-sec", type=int, default=12)
    parser.add_argument("--timeout-sec", type=int, default=75)
    parser.add_argument("--streamlink-command", default="streamlink")
    parser.add_argument("--ffmpeg-command", default="ffmpeg")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    result = collect_frames(
        channel_url=args.channel_url,
        output_dir=Path(args.output_dir),
        label=args.label,
        quality=args.quality,
        sample_count=args.sample_count,
        interval_sec=args.interval_sec,
        timeout_sec=args.timeout_sec,
        streamlink_command=command_parts(args.streamlink_command),
        ffmpeg_command=command_parts(args.ffmpeg_command),
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["success"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
