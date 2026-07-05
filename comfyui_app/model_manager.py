from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable

from comfyui_app.config import COMFYUI_DIR, MODELS_DIR
from comfyui_app.model_resolver import MODEL_REGISTRY, ModelResolverError, _write_manifest, load_resolved_manifest

MODEL_FILE_EXTENSIONS = {".safetensors", ".gguf", ".pth", ".pt", ".ckpt", ".bin"}


@dataclass(frozen=True)
class InstalledModelEntry:
    category: str
    filename: str
    path: str
    size_bytes: int

    @property
    def label(self) -> str:
        return f"{self.category}/{self.filename} ({format_size(self.size_bytes)})"


def format_size(size_bytes: int) -> str:
    size = float(size_bytes)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024.0 or unit == "TB":
            if unit == "B":
                return f"{int(size)} B"
            return f"{size:.1f} {unit}"
        size /= 1024.0
    return f"{size_bytes} B"


def _safe_roots() -> list[Path]:
    roots = [MODELS_DIR.resolve()]
    aux_root = (COMFYUI_DIR / "custom_nodes" / "comfyui_controlnet_aux").resolve()
    if aux_root.exists():
        roots.append(aux_root)
    return roots


def _is_within_allowed_roots(path: Path) -> bool:
    real_path = path.resolve()
    for root in _safe_roots():
        try:
            real_path.relative_to(root)
            return True
        except ValueError:
            continue
    return False


def _category_for(path: Path, root: Path) -> str:
    parent = path.parent.resolve()
    try:
        relative = parent.relative_to(root.resolve())
    except ValueError:
        return root.name
    if not relative.parts:
        return root.name
    if root.name == "comfyui_controlnet_aux":
        return f"{root.name}/{relative.as_posix()}"
    return relative.as_posix()


def _scan_root(root: Path) -> list[InstalledModelEntry]:
    if not root.exists():
        return []
    entries: list[InstalledModelEntry] = []
    for file_path in root.rglob("*"):
        if not file_path.is_file():
            continue
        if file_path.suffix.lower() not in MODEL_FILE_EXTENSIONS:
            continue
        try:
            real_path = file_path.resolve()
        except FileNotFoundError:
            continue
        if not _is_within_allowed_roots(real_path):
            continue
        entries.append(
            InstalledModelEntry(
                category=_category_for(real_path, root),
                filename=real_path.name,
                path=str(real_path),
                size_bytes=real_path.stat().st_size,
            )
        )
    return entries


def _registry_kind_index() -> tuple[set[str], dict[str, str]]:
    kinds: set[str] = set()
    dest_subdirs: dict[str, str] = {}
    for component_groups in MODEL_REGISTRY.values():
        for candidates in component_groups.values():
            for candidate in candidates:
                kinds.add(candidate.kind.lower())
                dest_subdirs.setdefault(candidate.kind.lower(), candidate.dest_subdir)
    return kinds, dest_subdirs


def _entry_payload(entry: InstalledModelEntry, *, reason: str | None = None) -> dict[str, object]:
    payload = {
        "category": entry.category,
        "filename": entry.filename,
        "path": entry.path,
        "size_bytes": entry.size_bytes,
        "size": format_size(entry.size_bytes),
        "label": entry.label,
    }
    if reason is not None:
        payload["reason"] = reason
    return payload


def list_installed_models() -> dict[str, object]:
    entries: list[InstalledModelEntry] = []
    entries.extend(_scan_root(MODELS_DIR))
    aux_root = COMFYUI_DIR / "custom_nodes" / "comfyui_controlnet_aux"
    if aux_root.exists():
        entries.extend(_scan_root(aux_root))
    entries.sort(key=lambda item: (item.category.lower(), item.filename.lower(), item.path.lower()))
    total_bytes = sum(entry.size_bytes for entry in entries)
    return {
        "entries": [
            _entry_payload(entry)
            for entry in entries
        ],
        "total_bytes": total_bytes,
        "total": format_size(total_bytes),
        "count": len(entries),
    }


def find_removable_models() -> dict[str, object]:
    entries = _scan_root(MODELS_DIR)
    if not entries:
        return {"entries": [], "total_bytes": 0, "total": format_size(0), "count": 0}

    known_kinds, dest_subdirs = _registry_kind_index()
    grouped: dict[str, list[InstalledModelEntry]] = {}
    for entry in entries:
        grouped.setdefault(entry.filename.lower(), []).append(entry)

    removable: list[dict[str, object]] = []
    for filename, group in grouped.items():
        group_sorted = sorted(group, key=lambda item: (item.path.lower(), item.category.lower()))
        keeper = group_sorted[0]
        if len(group_sorted) > 1:
            preferred_subdir = dest_subdirs.get(filename)
            if preferred_subdir is not None:
                preferred = next(
                    (entry for entry in group_sorted if entry.category == preferred_subdir),
                    None,
                )
                if preferred is not None:
                    keeper = preferred
            for entry in group_sorted:
                if entry.path == keeper.path:
                    continue
                removable.append(_entry_payload(entry, reason="duplicate"))
        if filename not in known_kinds and len(group_sorted) == 1:
            removable.append(_entry_payload(keeper, reason="unused"))

    removable.sort(key=lambda item: (str(item["reason"]), str(item["category"]).lower(), str(item["filename"]).lower(), str(item["path"]).lower()))
    total_bytes = sum(int(entry["size_bytes"]) for entry in removable)
    return {
        "entries": removable,
        "total_bytes": total_bytes,
        "total": format_size(total_bytes),
        "count": len(removable),
    }


def _deleted_matches_entry(deleted_path: Path, entry: dict[str, object]) -> bool:
    candidates: list[Path] = []
    dest_dir = entry.get("dest_dir")
    local_filename = entry.get("local_filename")
    local_path = entry.get("local_path")
    if isinstance(dest_dir, str) and isinstance(local_filename, str) and dest_dir and local_filename:
        candidates.append(Path(dest_dir) / local_filename)
    if isinstance(local_path, str) and local_path:
        candidates.append(Path(local_path))
    for candidate in candidates:
        try:
            candidate_real = candidate.resolve(strict=False)
        except Exception:
            continue
        if candidate_real == deleted_path:
            return True
    return False


def _prune_manifest(deleted_paths: Iterable[Path]) -> None:
    manifest = load_resolved_manifest()
    if not isinstance(manifest, dict):
        return
    models = manifest.get("models")
    if not isinstance(models, dict):
        return
    deleted = [path.resolve() for path in deleted_paths]
    kept_models: dict[str, dict[str, object]] = {}
    for name, entry in models.items():
        if not isinstance(entry, dict):
            continue
        if any(_deleted_matches_entry(deleted_path, entry) for deleted_path in deleted):
            continue
        kept_models[name] = dict(entry)
    if kept_models == models:
        return
    manifest["models"] = kept_models
    manifest["timestamp"] = datetime.now().isoformat(timespec="seconds")
    _write_manifest(manifest)


def delete_models(paths: Iterable[str | Path]) -> dict[str, object]:
    path_list = [Path(path) for path in paths]
    if not path_list:
        return list_installed_models() | {"freed_bytes": 0, "freed": format_size(0)}

    original_paths: list[Path] = []
    resolved_paths: list[Path] = []
    for path in path_list:
        if not path.exists():
            raise ModelResolverError(f"Model file not found: {path}")
        real_path = path.resolve()
        if not _is_within_allowed_roots(real_path):
            raise ModelResolverError(f"Refusing to delete a file outside the ComfyUI model tree: {path}")
        if not path.is_file():
            raise ModelResolverError(f"Refusing to delete a non-file path: {path}")
        original_paths.append(path)
        if real_path not in resolved_paths:
            resolved_paths.append(real_path)

    freed_bytes = sum(real_path.stat().st_size for real_path in resolved_paths)
    for path in original_paths:
        path.unlink()

    _prune_manifest(resolved_paths)
    refreshed = list_installed_models()
    refreshed["freed_bytes"] = freed_bytes
    refreshed["freed"] = format_size(freed_bytes)
    return refreshed


def remove_unused_models(paths: Iterable[str | Path] | None = None) -> dict[str, object]:
    if paths is None:
        removable = find_removable_models()
        paths = [entry["path"] for entry in removable["entries"] if isinstance(entry.get("path"), str)]
    return delete_models(paths)
