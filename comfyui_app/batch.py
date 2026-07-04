from __future__ import annotations

from datetime import datetime
import logging
import threading
from pathlib import Path
from typing import Callable, Protocol, Iterator

from comfyui_app.generation import GenerationResult
from comfyui_app.model_resolver import ModelResolverError

logger = logging.getLogger(__name__)
CANCEL_EVENT = threading.Event()


class SingleImageEditFn(Protocol):
    def __call__(
        self,
        input_image_path: Path,
        prompt: str,
        negative: str,
        output_dir: Path,
    ) -> GenerationResult | Path:
        ...


def request_cancel() -> None:
    CANCEL_EVENT.set()


def clear_cancel() -> None:
    CANCEL_EVENT.clear()


def _timestamped_run_dir(output_dir: Path) -> Path:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return output_dir / f"batch_{stamp}"


def _iter_image_files(source_dir: Path, exts: tuple[str, ...]) -> list[Path]:
    return [file_path for file_path in sorted(source_dir.iterdir()) if file_path.is_file() and file_path.suffix.lower() in exts]


def _folder_summary(
    run_dir: Path,
    processed: list[str],
    failures: list[str],
) -> dict[str, object]:
    message = "No images found in that folder." if not processed and not failures else f"Processed {len(processed)} files."
    if CANCEL_EVENT.is_set():
        message = f"Cancelled after {len(processed)} files."
    if processed or failures:
        message = f"{message} Output folder: {run_dir}"
    return {
        "count": len(processed),
        "failures": failures,
        "results": processed,
        "message": message,
        "output_dir": str(run_dir),
    }


def _run_folder(
    source_dir: Path,
    target_dir: Path,
    prompt: str,
    negative: str,
    gen_fn: SingleImageEditFn,
    exts: tuple[str, ...],
    on_result: Callable[[Path], None] | None = None,
) -> dict[str, object]:
    if not source_dir.exists() or not source_dir.is_dir():
        raise ModelResolverError(f"The input folder does not exist: {source_dir}")
    run_dir = _timestamped_run_dir(target_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    processed: list[str] = []
    failures: list[str] = []
    for file_path in _iter_image_files(source_dir, exts):
        if CANCEL_EVENT.is_set():
            break
        try:
            result = gen_fn(file_path, prompt, negative, run_dir)
            output_path = result.image_path if isinstance(result, GenerationResult) else Path(result)
            processed.append(str(output_path))
            if on_result is not None:
                on_result(output_path)
        except Exception as exc:
            failures.append(f"{file_path.name}: {exc}")
            logger.exception("Failed to process %s", file_path)
    return _folder_summary(run_dir, processed, failures)


def iter_process_folder(
    input_dir: str | Path,
    output_dir: str | Path,
    prompt: str,
    negative: str,
    gen_fn: SingleImageEditFn,
    exts: tuple[str, ...] = (".png", ".jpg", ".jpeg", ".webp", ".bmp"),
) -> Iterator[dict[str, object]]:
    source_dir = Path(input_dir)
    target_dir = Path(output_dir)
    clear_cancel()
    if not source_dir.exists() or not source_dir.is_dir():
        raise ModelResolverError(f"The input folder does not exist: {source_dir}")
    run_dir = _timestamped_run_dir(target_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    processed: list[str] = []
    failures: list[str] = []
    for file_path in _iter_image_files(source_dir, exts):
        if CANCEL_EVENT.is_set():
            break
        try:
            result = gen_fn(file_path, prompt, negative, run_dir)
            output_path = result.image_path if isinstance(result, GenerationResult) else Path(result)
            processed.append(str(output_path))
        except Exception as exc:
            failures.append(f"{file_path.name}: {exc}")
            logger.exception("Failed to process %s", file_path)
        yield _folder_summary(run_dir, processed, failures)
    yield _folder_summary(run_dir, processed, failures)


def process_folder(
    input_dir: str | Path,
    output_dir: str | Path,
    prompt: str,
    negative: str,
    gen_fn: SingleImageEditFn,
    exts: tuple[str, ...] = (".png", ".jpg", ".jpeg", ".webp", ".bmp"),
    on_result: Callable[[Path], None] | None = None,
) -> dict[str, object]:
    clear_cancel()
    source_dir = Path(input_dir)
    target_dir = Path(output_dir)
    return _run_folder(source_dir, target_dir, prompt, negative, gen_fn, exts, on_result=on_result)
