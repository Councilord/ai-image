from __future__ import annotations

from pathlib import Path


def pick_directory(current: str) -> str:
    try:
        import tkinter as tk
        from tkinter import filedialog

        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        chosen = filedialog.askdirectory(initialdir=current or str(Path.cwd()))
        root.destroy()
        return chosen or current
    except Exception:
        return current
