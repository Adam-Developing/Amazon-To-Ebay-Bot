# ui_bridge.py
from __future__ import annotations
from typing import List, Optional
import os
import sys
import webbrowser

class IOBridge:
    """UI bridge for logging and prompting.
    Default implementation is non-interactive and silent.
    GUI should subclass and implement methods.
    """
    def log(self, msg: str) -> None:
        pass

    def prompt_text(self, prompt: str, default: str = "", options: List[str] | None = None) -> str:
        # Base bridge ignores options and returns default; UI implementations can use options for suggestions
        return default

    def prompt_choice(self, prompt: str, options: List[str]) -> Optional[str]:
        return options[0] if options else None

    def open_url(self, url: str) -> None:
        try:
            # Use a single call with autoraise=False to avoid stealing focus when supported.
            webbrowser.open(url, new=2, autoraise=False)
        except Exception:
            # Windows-specific fallback using os.startfile
            try:
                if sys.platform.startswith('win'):
                    os.startfile(url)
            except Exception:
                # Last-resort: print to console (silent logger otherwise)
                print(f"Failed to open URL: {url}")
