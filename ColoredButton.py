# python
"""
`ColoredButton` widget for Tkinter.

This module provides a lightweight, label-based clickable button with configurable
colors for normal/active/disabled states, keyboard activation, and safe command
execution (exceptions from command callbacks are logged, not raised).

Public:
- class ColoredButton(tk.Label)
"""
from typing import Callable, Optional, Any, Dict
import logging
import tkinter as tk

logger = logging.getLogger(__name__)


class ColoredButton(tk.Label):
    """
    A clickable label styled as a button.

    The widget acts like a button but is implemented as a `tk.Label` to allow
    fine-grained styling. It exposes `.enable()`, `.disable()`, `.set_command()`,
    and `.is_enabled` for programmatic control.

    Parameters
    - master: parent widget
    - text: displayed text
    - command: optional callable invoked on activation
    - bg, fg: normal background/foreground colors
    - active_bg, active_fg: colors shown on hover/press
    - disabled_bg, disabled_fg: colors when disabled
    - padx, pady: internal padding
    - \*\*kw: forwarded to `tk.Label`
    """

    def __init__(
        self,
        master: Any,
        text: str,
        command: Optional[Callable[[], Any]] = None,
        bg: str = "#23262a",
        fg: str = "#e6eef8",
        active_bg: str = "#3A90FF",
        active_fg: str = "#ffffff",
        disabled_bg: str = "#2a2c30",
        disabled_fg: str = "#7f8a97",
        padx: int = 12,
        pady: int = 8,
        **kw: Any,
    ) -> None:
        self._cmd = command
        self._enabled = True
        self._styles: Dict[str, str] = {
            "bg": bg,
            "fg": fg,
            "active_bg": active_bg,
            "active_fg": active_fg,
            "disabled_bg": disabled_bg,
            "disabled_fg": disabled_fg,
        }

        super().__init__(
            master,
            text=text,
            bg=bg,
            fg=fg,
            padx=padx,
            pady=pady,
            cursor="hand2",
            takefocus=1,
            **kw,
        )

        # Mouse interactions
        self.bind("<Enter>", self._on_enter, add=True)
        self.bind("<Leave>", self._on_leave, add=True)
        self.bind("<ButtonPress-1>", self._on_press, add=True)
        self.bind("<ButtonRelease-1>", self._on_release, add=True)

        # Keyboard activation when focused
        self.bind("<Return>", lambda e: self._activate(), add=True)
        self.bind("<space>", lambda e: self._activate(), add=True)

    # --- Internal event handlers ---

    def _on_enter(self, _event: tk.Event) -> None:
        if not self._enabled:
            return
        try:
            self.config(bg=self._styles["active_bg"], fg=self._styles["active_fg"])
        except Exception:
            logger.exception("Error in _on_enter")

    def _on_leave(self, _event: tk.Event) -> None:
        if not self._enabled:
            return
        try:
            self.config(bg=self._styles["bg"], fg=self._styles["fg"])
        except Exception:
            logger.exception("Error in _on_leave")

    def _on_press(self, _event: tk.Event) -> None:
        if not self._enabled:
            return
        try:
            # Keep active appearance during press
            self.config(bg=self._styles["active_bg"], fg=self._styles["active_fg"])
        except Exception:
            logger.exception("Error in _on_press")

    def _on_release(self, event: tk.Event) -> None:
        """
        Activate only when release occurs within widget bounds. Restore proper
        hover/normal appearance otherwise.
        """
        if not self._enabled:
            return
        try:
            x, y = event.x, event.y
            w, h = self.winfo_width(), self.winfo_height()
            if 0 <= x < w and 0 <= y < h:
                self._activate()
            else:
                # restore according to pointer presence
                self._on_leave(event)
        except Exception:
            logger.exception("Error in _on_release")

    # --- Activation and public API ---

    def _activate(self) -> None:
        """Invoke the configured command safely (exceptions are logged)."""
        if not self._enabled or self._cmd is None:
            return
        try:
            self._cmd()
        except Exception:
            logger.exception("Exception raised by ColoredButton command")

    def enable(self) -> None:
        """Enable the widget and restore normal appearance and pointer."""
        self._enabled = True
        try:
            self.config(bg=self._styles["bg"], fg=self._styles["fg"], cursor="hand2")
            # Keep widget state attribute consistent for external inspection
            try:
                self.configure(state="normal")
            except Exception:
                # some environments may not support state on Label; ignore
                pass
        except Exception:
            logger.exception("Error enabling ColoredButton")

    def disable(self) -> None:
        """Disable the widget and apply disabled appearance."""
        self._enabled = False
        try:
            self.config(bg=self._styles["disabled_bg"], fg=self._styles["disabled_fg"], cursor="arrow")
            try:
                self.configure(state="disabled")
            except Exception:
                pass
        except Exception:
            logger.exception("Error disabling ColoredButton")

    def set_command(self, command: Optional[Callable[[], Any]]) -> None:
        """Replace the command called on activation."""
        self._cmd = command

    @property
    def is_enabled(self) -> bool:
        """Return current enabled state."""
        return bool(self._enabled)

    def __repr__(self) -> str:  # pragma: no cover - convenience only
        return f"<ColoredButton text={self.cget('text')!r} enabled={self._enabled}>"