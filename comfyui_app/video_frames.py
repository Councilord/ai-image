from __future__ import annotations

import logging
import shutil
import subprocess
from pathlib import Path

from comfyui_app.model_resolver import ModelResolverError

logger = logging.getLogger(__name__)

try:
    import cv2
except Exception:  # pragma: no cover - optional dependency
    cv2 = None  # type: ignore[assignment]

try:
    import imageio_ffmpeg
except Exception:  # pragma: no cover - optional dependency
    imageio_ffmpeg = None  # type: ignore[assignment]


def _save_frame(image, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if cv2 is None:
        raise ModelResolverError("OpenCV is not available, so frames cannot be written.")
    cv2.imwrite(str(output_path), image)


def _require_ffmpeg_exe() -> str:
    if imageio_ffmpeg is None:
        raise ModelResolverError("imageio-ffmpeg is required for video reassembly.")
    return imageio_ffmpeg.get_ffmpeg_exe()


def _probe_audio_stream(source: Path) -> bool:
    ffmpeg = _require_ffmpeg_exe()
    result = subprocess.run([ffmpeg, "-hide_banner", "-i", str(source)], capture_output=True, text=True, check=False)
    return "Audio:" in (result.stderr or "")


def probe_video_metadata(video_path: str | Path) -> dict[str, object]:
    source = Path(video_path)
    metadata: dict[str, object] = {"fps": 0.0, "width": 0, "height": 0, "has_audio": False}
    if cv2 is not None:
        capture = cv2.VideoCapture(str(source))
        if not capture.isOpened():
            raise ModelResolverError(f"Could not open the video file: {source}")
        try:
            metadata["fps"] = float(capture.get(cv2.CAP_PROP_FPS) or 0.0)
            metadata["width"] = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
            metadata["height"] = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
        finally:
            capture.release()
    metadata["has_audio"] = _probe_audio_stream(source)
    return metadata


def extract_frames(
    video_path: str | Path,
    out_dir: str | Path,
    every_n: int = 1,
    max_frames: int | None = None,
) -> list[str]:
    source = Path(video_path)
    target_dir = Path(out_dir)
    target_dir.mkdir(parents=True, exist_ok=True)

    if cv2 is not None:
        capture = cv2.VideoCapture(str(source))
        if not capture.isOpened():
            raise ModelResolverError(f"Could not open the video file: {source}")
        saved: list[str] = []
        frame_index = 0
        output_index = 0
        try:
            while True:
                ok, frame = capture.read()
                if not ok:
                    break
                if frame_index % max(1, every_n) == 0:
                    output_path = target_dir / f"frame_{output_index:06d}.png"
                    _save_frame(frame, output_path)
                    saved.append(str(output_path))
                    output_index += 1
                    if max_frames is not None and len(saved) >= max_frames:
                        break
                frame_index += 1
        finally:
            capture.release()
        return saved

    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        raise ModelResolverError(
            "OpenCV is not installed and ffmpeg was not found on PATH, so video frames cannot be extracted."
        )

    pattern = target_dir / "frame_%06d.png"
    select_filter = f"select='not(mod(n\\,{max(1, every_n)}))'"
    command = [
        ffmpeg,
        "-i",
        str(source),
        "-vf",
        select_filter,
        "-vsync",
        "vfr",
    ]
    if max_frames is not None:
        command.extend(["-frames:v", str(max_frames)])
    command.append(str(pattern))
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise ModelResolverError("ffmpeg could not extract frames from the uploaded video.")
    saved = sorted(str(path) for path in target_dir.glob("frame_*.png"))
    if max_frames is not None:
        saved = saved[:max_frames]
    return saved


def build_frames_to_video_command(
    frame_pattern: str | Path,
    out_path: str | Path,
    fps: float,
    audio_source: str | Path | None = None,
    has_audio: bool | None = None,
) -> list[str]:
    ffmpeg = _require_ffmpeg_exe()
    command = [
        ffmpeg,
        "-y",
        "-framerate",
        f"{fps:.6f}".rstrip("0").rstrip("."),
        "-i",
        str(frame_pattern),
    ]
    if audio_source is not None and (has_audio is True or has_audio is None):
        command.extend([
            "-i",
            str(audio_source),
            "-map",
            "0:v",
            "-map",
            "1:a?",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-shortest",
        ])
    else:
        command.extend(["-c:v", "libx264", "-pix_fmt", "yuv420p"])
    command.append(str(out_path))
    return command


def frames_to_video(
    frames_dir_or_list: str | Path | list[str | Path],
    out_path: str | Path,
    fps: float,
    audio_source: str | Path | None = None,
) -> Path:
    output_path = Path(out_path)
    if output_path.suffix.lower() != ".mp4":
        output_path = output_path.with_suffix(".mp4")
    if isinstance(frames_dir_or_list, (str, Path)):
        frame_pattern = Path(frames_dir_or_list) / "frame_%06d.png"
    else:
        if not frames_dir_or_list:
            raise ModelResolverError("No frames were provided for video reassembly.")
        frame_pattern = Path(frames_dir_or_list[0]).with_name("frame_%06d.png")
    audio_ok = _probe_audio_stream(Path(audio_source)) if audio_source is not None else False
    command = build_frames_to_video_command(frame_pattern, output_path, fps, audio_source=audio_source, has_audio=audio_ok)
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        raise ModelResolverError(detail or "ffmpeg could not reassemble the video.")
    return output_path
