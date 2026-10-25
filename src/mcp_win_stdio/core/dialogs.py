"""
Windows native GUI dialog helpers (folder browser and file picker) with CLI fallbacks.
Uses Python's standard library tkinter on Windows, with fallback to console prompt.
"""

import os
import sys
from pathlib import Path
from typing import List, Optional, Tuple


def is_gui_available() -> bool:
    """Check if GUI dialogs can be displayed in current environment."""
    if sys.platform != "win32":
        return bool(os.environ.get("DISPLAY"))
    try:
        import tkinter  # noqa: F401
        return True
    except Exception:
        return False


def pick_directory(title: str = "Select Folder", initialdir: Optional[str] = None) -> Optional[str]:
    """
    Open native Windows folder browser dialog.
    Returns selected directory path as a string, or None if cancelled.
    """
    try:
        import tkinter as tk
        from tkinter import filedialog

        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        folder = filedialog.askdirectory(
            title=title,
            initialdir=str(initialdir) if initialdir else os.getcwd(),
        )
        root.destroy()
        if folder:
            return str(Path(folder).resolve())
        return None
    except Exception:
        return None


def pick_file(
    title: str = "Select File",
    filetypes: Optional[List[Tuple[str, str]]] = None,
    initialdir: Optional[str] = None,
) -> Optional[str]:
    """
    Open native Windows file picker dialog.
    Returns selected file path as a string, or None if cancelled.
    """
    try:
        import tkinter as tk
        from tkinter import filedialog

        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        if filetypes is None:
            filetypes = [("All Files", "*.*")]
        file_path = filedialog.askopenfilename(
            title=title,
            filetypes=filetypes,
            initialdir=str(initialdir) if initialdir else os.getcwd(),
        )
        root.destroy()
        if file_path:
            return str(Path(file_path).resolve())
        return None
    except Exception:
        return None


def prompt_path_or_dialog(
    prompt_label: str,
    is_directory: bool = True,
    title: str = "Select Path",
    filetypes: Optional[List[Tuple[str, str]]] = None,
    default_path: Optional[str] = None,
) -> Optional[str]:
    """
    Interactively prompt user to either pick via native Windows dialog or enter manually.
    """
    if not sys.stdin.isatty():
        return default_path

    if is_gui_available():
        print(f"\n📂 {prompt_label}:")
        print("   [1] Open Windows picker dialog (Recommended)")
        print("   [2] Enter or paste path manually")
        def_hint = f" [default: {default_path}]" if default_path else ""
        choice = input("   Choose (1/2) [default: 1]: ").strip() or "1"

        if choice == "1":
            print("   Opening Windows dialog... (Check taskbar if window does not appear in front)")
            if is_directory:
                picked = pick_directory(title=title, initialdir=default_path)
            else:
                picked = pick_file(title=title, filetypes=filetypes, initialdir=default_path)
            if picked:
                print(f"   ✅ Selected: {picked}")
                return picked
            print("   ⚠️  No path selected from dialog. Falling back to manual entry.")

    manual = input(f"   Enter path{def_hint}: ").strip().strip("\"'")
    if not manual and default_path:
        return default_path
    return manual if manual else None
