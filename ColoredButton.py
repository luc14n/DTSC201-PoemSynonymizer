import tkinter as tk
from typing import Callable, Optional

class ColoredButton(tk.Label):
    def __init__(
        self,
        master,
        text: str,
        command: Optional[Callable] = None,
        bg: str = "#23262a",
        fg: str = "#e6eef8",
        active_bg: str = "#3A90FF",
        active_fg: str = "#ffffff",
        disabled_bg: str = "#2a2c30",
        disabled_fg: str = "#7f8a97",
        padx: int = 12,
        pady: int = 8,
        **kw,
    ):
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
        self._cmd = command
        self._normal_bg = bg
        self._normal_fg = fg
        self._active_bg = active_bg
        self._active_fg = active_fg
        self._disabled_bg = disabled_bg
        self._disabled_fg = disabled_fg
        self._enabled = True

        # mouse
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        self.bind("<ButtonPress-1>", self._on_press)
        self.bind("<ButtonRelease-1>", self._on_release)

        # keyboard activation when focused
        self.bind("<Return>", lambda e: self._activate())
        self.bind("<space>", lambda e: self._activate())

    def _on_enter(self, _event):
        if not self._enabled:
            return
        self.config(bg=self._active_bg, fg=self._active_fg)

    def _on_leave(self, _event):
        if not self._enabled:
            return
        self.config(bg=self._normal_bg, fg=self._normal_fg)

    def _on_press(self, _event):
        if not self._enabled:
            return
        # pressed visual (keep active colors)
        self.config(bg=self._active_bg, fg=self._active_fg)

    def _on_release(self, _event):
        if not self._enabled:
            return
        # run command only if pointer is still over widget
        x, y = _event.x, _event.y
        w, h = self.winfo_width(), self.winfo_height()
        if 0 <= x < w and 0 <= y < h:
            self._activate()
        else:
            # restore hover/normal depending on pointer
            self._on_leave(_event)

    def _activate(self):
        if not self._enabled or self._cmd is None:
            return
        try:
            self._cmd()
        except Exception:
            # swallow exceptions from user command to avoid crashing the UI
            pass

    def enable(self):
        self._enabled = True
        self.config(bg=self._normal_bg, fg=self._normal_fg, cursor="hand2")
        self.configure(state="normal")

    def disable(self):
        self._enabled = False
        self.config(bg=self._disabled_bg, fg=self._disabled_fg, cursor="arrow")
        self.configure(state="disabled")