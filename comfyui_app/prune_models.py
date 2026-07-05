from __future__ import annotations

import argparse
from typing import Sequence

from comfyui_app.model_manager import find_removable_models, format_size, remove_unused_models


def _render_entries(data: dict[str, object]) -> None:
    entries = data.get("entries")
    if not isinstance(entries, list) or not entries:
        print("No unused or duplicate models found.")
        return
    print("Removable models:")
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        reason = entry.get("reason", "unused")
        category = entry.get("category", "?")
        filename = entry.get("filename", "?")
        size = entry.get("size", format_size(int(entry.get("size_bytes", 0) or 0)))
        path = entry.get("path", "")
        print(f"- {reason}: {category}/{filename} ({size})")
        print(f"  {path}")
    print(f"Reclaimable space: {data.get('total', '0 B')} across {data.get('count', 0)} files")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Remove unused or duplicate model files from the ComfyUI models folder.")
    parser.add_argument("--yes", action="store_true", help="Delete the removable files without prompting.")
    args = parser.parse_args(list(argv) if argv is not None else None)

    data = find_removable_models()
    _render_entries(data)

    entries = data.get("entries")
    if not isinstance(entries, list) or not entries:
        return 0

    if not args.yes:
        response = input("Remove these files? [y/N] ").strip().lower()
        if response not in {"y", "yes"}:
            print("Cancelled.")
            return 0

    paths = [entry["path"] for entry in entries if isinstance(entry, dict) and isinstance(entry.get("path"), str)]
    removed = remove_unused_models(paths)
    print(f"Removed {removed.get('freed', '0 B')} and refreshed the installed models list.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
