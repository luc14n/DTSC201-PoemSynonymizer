# python
"""
Refactored GUI module for Poem Synonymizer.

Public API:
- create_gui(in_queue: Optional[queue.Queue], out_queue: Optional[queue.Queue]) -> tk.Tk

This module intentionally keeps side-effects minimal and returns a `tk.Tk` root
that the caller can `mainloop()` on.  It is safe if `in_queue`/`out_queue` are
`None` (useful for testing the UI without background workers).
"""

from typing import Optional, Any, Callable
import tkinter as tk
from tkinter import font
import queue as _queue
import re
import os
import json
import traceback

# Local import for a custom button widget used in the original project.
# It's expected to implement `.disable()` and `.enable()` methods.
from ColoredButton import ColoredButton  # keep as-is; tests should provide a stub if necessary

# Constants / appearance
_BG_COLOR = "#0f1115"
_PANEL_COLOR = "#15161a"
_INPUT_COLOR = "#1b1d22"
_OUTPUT_COLOR = "#111214"
_TEXT_COLOR = "#e6eef8"
_BUTTON_COLOR = "#23262a"
_ACCENT_COLOR = "#3A90FF"
_ACCENT_COLOR_PRESS = "#226fbd"

_PROFANITY_FALLBACK = {"damn", "hell", "shit", "fuck", "bitch", "asshole"}
_PROFANITY_FILE = "profanity_list.txt"
_PROFANITY_META_MAX_WORD_LEN = 200  # unused but kept for clarity


def _safe_load_profanity_list(path: str = _PROFANITY_FILE) -> set:
    """
    Load a profanity list from `path`. Lines starting with '#' or after '#' are ignored.
    Returns a non-empty set; falls back to a default set on error.
    """
    try:
        full = os.path.abspath(path)
        if os.path.exists(full):
            words = set()
            with open(full, "r", encoding="utf-8") as f:
                for line in f:
                    # strip comments and whitespace, keep lowercase
                    token = line.split("#", 1)[0].strip().lower()
                    if token:
                        words.add(token)
            return words if words else _PROFANITY_FALLBACK
    except Exception:
        pass
    return _PROFANITY_FALLBACK


# Attempt to use better_profanity if available (optional enhancement)
try:
    from better_profanity import profanity as _bp_profanity  # type: ignore

    _ADVANCED_PROFANITY_AVAILABLE = True
except Exception:
    _bp_profanity = None  # type: ignore
    _ADVANCED_PROFANITY_AVAILABLE = False


def create_gui(in_queue: Optional[_queue.Queue] = None, out_queue: Optional[_queue.Queue] = None) -> tk.Tk:
    """
    Build and return the main Tk root for the Poem Synonymizer.

    Parameters:
    - in_queue: queue used to send requests to the processor (put_nowait payloads)
    - out_queue: queue used by a processor to push back processed text

    The UI will poll `out_queue` periodically. If `in_queue` is None, generate actions
    are no-ops (useful for UI-only testing).
    """
    root = tk.Tk()
    root.title("Poem Synonymizer")
    root.geometry("900x500")
    root.minsize(600, 300)
    root.configure(bg=_BG_COLOR)

    # State captured in closure
    last_sent_text: Optional[str] = None
    profanity_set = _safe_load_profanity_list()
    profanity_pattern = re.compile(
        r"\b(" + "|".join(re.escape(w) for w in sorted(profanity_set, key=len, reverse=True)) + r")\b",
        flags=re.IGNORECASE,
    ) if profanity_set else None

    # If available, preload custom censor words for better_profanity
    if _ADVANCED_PROFANITY_AVAILABLE and _bp_profanity is not None:
        try:
            _bp_profanity.load_censor_words(list(profanity_set))
        except Exception:
            # Non-fatal: fallback to regex below
            pass

    def _mask_profane(match: re.Match) -> str:
        s = match.group(0)
        return "".join("*" if c.isalpha() else c for c in s)

    def profanity_filter(text: str) -> str:
        """Apply configured profanity filtering to `text` and return the censored string."""
        if not text:
            return text
        if _ADVANCED_PROFANITY_AVAILABLE and _bp_profanity is not None:
            try:
                return _bp_profanity.censor(text)
            except Exception:
                # fallback to regex-based censoring
                pass
        if profanity_pattern is None:
            return text
        try:
            return profanity_pattern.sub(_mask_profane, text)
        except Exception:
            return text

    # Layout: two panels (left input, right output)
    left_frame = tk.Frame(root, bg=_PANEL_COLOR, padx=10, pady=10)
    right_frame = tk.Frame(root, bg=_PANEL_COLOR, padx=10, pady=10)
    left_frame.grid(row=0, column=0, sticky="nsew")
    right_frame.grid(row=0, column=1, sticky="nsew")
    root.grid_columnconfigure(0, weight=1, uniform="cols")
    root.grid_columnconfigure(1, weight=1, uniform="cols")
    root.grid_rowconfigure(0, weight=1)

    # Shared font for readability
    text_font = font.Font(family="Helvetica", size=12)

    # Input widgets
    tk.Label(left_frame, text="Input", bg=_PANEL_COLOR, fg=_TEXT_COLOR, anchor="w").pack(fill="x", padx=(2, 0), pady=(0, 6))
    input_container = tk.Frame(left_frame, bg=_PANEL_COLOR)
    input_container.pack(fill="both", expand=True)
    input_scroll = tk.Scrollbar(input_container)
    input_scroll.pack(side="right", fill="y")
    input_box = tk.Text(
        input_container,
        wrap="word",
        bg=_INPUT_COLOR,
        fg=_TEXT_COLOR,
        insertbackground=_TEXT_COLOR,
        relief="flat",
        font=text_font,
        yscrollcommand=input_scroll.set,
        padx=8,
        pady=8,
        borderwidth=0,
    )
    input_box.pack(fill="both", expand=True)
    input_scroll.config(command=input_box.yview)

    # Output widgets
    tk.Label(right_frame, text="Output", bg=_PANEL_COLOR, fg=_TEXT_COLOR, anchor="w").pack(fill="x", padx=(2, 0), pady=(0, 6))
    output_container = tk.Frame(right_frame, bg=_PANEL_COLOR)
    output_container.pack(fill="both", expand=True)
    output_scroll = tk.Scrollbar(output_container)
    output_scroll.pack(side="right", fill="y")
    output_box = tk.Text(
        output_container,
        wrap="word",
        bg=_OUTPUT_COLOR,
        fg=_TEXT_COLOR,
        relief="flat",
        font=text_font,
        yscrollcommand=output_scroll.set,
        padx=8,
        pady=8,
        borderwidth=0,
        state="disabled",
    )
    output_box.pack(fill="both", expand=True)
    output_scroll.config(command=output_box.yview)

    # Helper: robust send-with-retry that won't crash the UI
    def _send_with_retry(payload: Any, attempt: int = 0) -> None:
        """
        Put `payload` into `in_queue` using an exponential backoff on Full.
        Disables the generate button briefly to prevent rapid repeats.
        """
        nonlocal in_queue
        try:
            if in_queue is not None:
                in_queue.put_nowait(payload)
            # Attempt to provide UI feedback if the widget exposes disable/enable
            try:
                generate_btn.disable()
                root.after(150, generate_btn.enable)
            except Exception:
                # If the custom button doesn't support these methods, ignore
                pass
        except _queue.Full:
            if attempt < 6:
                try:
                    generate_btn.disable()
                except Exception:
                    pass
                delay_ms = 50 * (2 ** attempt)
                root.after(delay_ms, lambda: _send_with_retry(payload, attempt + 1))
            else:
                try:
                    generate_btn.enable()
                except Exception:
                    pass
        except Exception:
            # Log stack to console for debugging but continue running UI
            traceback.print_exc()

    # Generate button behavior
    def on_generate(force: bool = False) -> None:
        """
        Handler for generation actions.

        Behavior:
        - If trimmed input is empty: clears output and resets last cache.
        - If input hasn't changed and not `force`, sends a rebuild command `{"_rebuild": True}`.
        - Otherwise sends the full text payload for processing.
        """
        nonlocal last_sent_text
        try:
            text = input_box.get("1.0", "end-1c")
            normalized = text.strip()

            # Clear output when input is empty
            if not normalized:
                output_box.config(state="normal")
                output_box.delete("1.0", "end")
                output_box.config(state="disabled")
                last_sent_text = None
                return

            # If unchanged, request a rebuild (processor will call build_synonym_string)
            if not force and normalized == last_sent_text:
                if in_queue is not None:
                    _send_with_retry({"_rebuild": True})
                return

            # Send fresh text payload
            if in_queue is not None:
                last_sent_text = normalized
                _send_with_retry(text)
        except Exception:
            traceback.print_exc()

    # Bottom controls row
    btn_frame = tk.Frame(left_frame, bg=_PANEL_COLOR)
    btn_frame.pack(fill="x", pady=(8, 0))

    prof_var = tk.BooleanVar(value=False)
    tk.Checkbutton(
        btn_frame,
        text="Profanity filter",
        variable=prof_var,
        bg=_PANEL_COLOR,
        fg=_TEXT_COLOR,
        selectcolor=_PANEL_COLOR,
        activebackground=_PANEL_COLOR,
        activeforeground=_TEXT_COLOR,
        highlightthickness=0,
        bd=0,
    ).pack(side="left", padx=(0, 8))

    if _ADVANCED_PROFANITY_AVAILABLE:
        tk.Label(btn_frame, text="(advanced filter available)", bg=_PANEL_COLOR, fg="#9fb6ff").pack(side="left", padx=(0, 8))

    generate_btn = ColoredButton(
        btn_frame,
        text="Generate",
        bg=_BUTTON_COLOR,
        fg=_TEXT_COLOR,
        active_bg=_ACCENT_COLOR,
        active_fg="#ffffff",
        disabled_bg="#2a2c30",
        disabled_fg="#7f8a97",
        command=on_generate,
        relief="flat",
        borderwidth=0,
    )
    generate_btn.pack(anchor="e", padx=4)

    # Poll `out_queue` and write to the output box when available
    def _poll_output() -> None:
        if out_queue is not None:
            try:
                while True:
                    processed = out_queue.get_nowait()
                    # Apply optional profanity filtering
                    if prof_var.get():
                        try:
                            processed = profanity_filter(processed)
                        except Exception:
                            pass
                    output_box.config(state="normal")
                    output_box.delete("1.0", "end")
                    output_box.insert("1.0", processed)
                    output_box.config(state="disabled")
            except _queue.Empty:
                # No more items right now
                pass
            except Exception:
                # Guard against unexpected errors in background data
                traceback.print_exc()
        root.after(100, _poll_output)

    root.after(100, _poll_output)

    # Keyboard bindings: Command/Ctrl+Return triggers generate
    def _bind_generate(event: Optional[tk.Event] = None) -> str:
        on_generate()
        return "break"

    root.bind_all("<Control-Return>", _bind_generate)
    root.bind_all("<Command-Return>", _bind_generate)

    return root