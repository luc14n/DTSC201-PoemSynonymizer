import tkinter as tk
from tkinter import font
from ColoredButton import ColoredButton
import queue as _queue
import re
import os
import traceback

# Try to import better_profanity; fall back silently if unavailable
try:
    from better_profanity import profanity as _bp_profanity
    _ADVANCED_PROFANITY_AVAILABLE = True
except Exception:
    _bp_profanity = None
    _ADVANCED_PROFANITY_AVAILABLE = False

def create_gui(in_queue=None, out_queue=None):
    root = tk.Tk()
    root.title("Poem Synonymizer")
    root.geometry("900x500")
    root.minsize(600, 300)

    last_sent_text = None

    # Colors (dark mode)
    bg_color = "#0f1115"
    panel_color = "#15161a"
    input_color = "#1b1d22"
    output_color = "#111214"
    text_color = "#e6eef8"
    button_color = "#23262a"
    accent_color = "#3A90FF"
    accent_color_press = "#226fbd"

    root.configure(bg=bg_color)

    # helper: load profanity list from file or fallback to defaults
    def _load_profanity_list():
        default = {"damn", "hell", "shit", "fuck", "bitch", "asshole"}
        try:
            path = os.path.abspath("profanity_list.txt")
            if os.path.exists(path):
                words = []
                with open(path, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.split("#", 1)[0].strip().lower()
                        if line:
                            words.append(line)
                return set(words) if words else default
        except Exception:
            pass
        return default

    PROFANITY_SET = _load_profanity_list()

    # Prepare regex-based pattern (fallback)
    PROFANITY_PATTERN = None
    if PROFANITY_SET:
        PROFANITY_PATTERN = re.compile(
            r"\b(" + "|".join(re.escape(w) for w in sorted(PROFANITY_SET, key=len, reverse=True)) + r")\b",
            flags=re.IGNORECASE,
        )

    def _mask_profane(match):
        s = match.group(0)
        return "".join("*" if c.isalpha() else c for c in s)

    # If advanced library is available, preload custom list into it
    if _ADVANCED_PROFANITY_AVAILABLE and _bp_profanity is not None:
        try:
            # better_profanity expects a list of words
            _bp_profanity.load_censor_words(list(PROFANITY_SET))
        except Exception:
            # ignore loading errors and fall back to regex below when censoring
            pass

    def profanity_filter(text: str) -> str:
        if not text:
            return text

        # Prefer advanced filter if available
        if _ADVANCED_PROFANITY_AVAILABLE and _bp_profanity is not None:
            try:
                # use better_profanity.censor which will replace letters with '*'
                return _bp_profanity.censor(text)
            except Exception:
                # fall through to regex fallback
                pass

        # Regex fallback: replace matched profane words with '*' for letters
        if PROFANITY_PATTERN is None:
            return text
        try:
            return PROFANITY_PATTERN.sub(_mask_profane, text)
        except Exception:
            return text

    # Layout frames
    left_frame = tk.Frame(root, bg=panel_color, padx=10, pady=10)
    right_frame = tk.Frame(root, bg=panel_color, padx=10, pady=10)
    left_frame.grid(row=0, column=0, sticky="nsew")
    right_frame.grid(row=0, column=1, sticky="nsew")

    root.grid_columnconfigure(0, weight=1, uniform="cols")
    root.grid_columnconfigure(1, weight=1, uniform="cols")
    root.grid_rowconfigure(0, weight=1)

    # Shared font
    text_font = font.Font(family="Helvetica", size=12)

    # Input Text (left)
    input_label = tk.Label(left_frame, text="Input", bg=panel_color, fg=text_color, anchor="w")
    input_label.pack(fill="x", padx=(2,0), pady=(0,6))

    input_container = tk.Frame(left_frame, bg=panel_color)
    input_container.pack(fill="both", expand=True)

    input_scroll = tk.Scrollbar(input_container)
    input_scroll.pack(side="right", fill="y")

    input_box = tk.Text(
        input_container,
        wrap="word",
        bg=input_color,
        fg=text_color,
        insertbackground=text_color,
        relief="flat",
        font=text_font,
        yscrollcommand=input_scroll.set,
        padx=8,
        pady=8,
        borderwidth=0,
    )
    input_box.pack(fill="both", expand=True)
    input_scroll.config(command=input_box.yview)

    # Output Text (right)
    output_label = tk.Label(right_frame, text="Output", bg=panel_color, fg=text_color, anchor="w")
    output_label.pack(fill="x", padx=(2, 0), pady=(0, 6))

    output_container = tk.Frame(right_frame, bg=panel_color)
    output_container.pack(fill="both", expand=True)

    output_scroll = tk.Scrollbar(output_container)
    output_scroll.pack(side="right", fill="y")

    output_box = tk.Text(
        output_container,
        wrap="word",
        bg=output_color,
        fg=text_color,
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

    # Define send-with-retry helper here so it's available whenever on_generate needs it
    def _send_with_retry(payload, attempt=0):
        try:
            if in_queue is not None:
                in_queue.put_nowait(payload)
            # disable/enable the button if it exists; resolve at call time
            try:
                generate_btn.disable()
                root.after(150, generate_btn.enable)
            except Exception:
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
            # unexpected errors shouldn't crash the UI
            traceback.print_exc()

    # Generate button below input
    def on_generate(force=False):
        nonlocal last_sent_text
        try:
            text = input_box.get("1.0", "end-1c")
            normalized = text.strip()

            # if empty, clear output and reset cache
            if not normalized:
                output_box.config(state="normal")
                output_box.delete("1.0", "end")
                output_box.config(state="disabled")
                last_sent_text = None
                return

            # skip sending full request if unchanged; instead request a rebuild using existing words_type
            if not force and normalized == last_sent_text:
                if in_queue is not None:
                    _send_with_retry({"_rebuild": True})
                return

            if in_queue is not None:
                last_sent_text = normalized
                _send_with_retry(text)
        except Exception:
            traceback.print_exc()

    btn_frame = tk.Frame(left_frame, bg=panel_color)
    btn_frame.pack(fill="x", pady=(8, 0))

    # Profanity filter checkbox
    prof_var = tk.BooleanVar(value=False)
    prof_cb = tk.Checkbutton(
        btn_frame,
        text="Profanity filter",
        variable=prof_var,
        bg=panel_color,
        fg=text_color,
        selectcolor=panel_color,
        activebackground=panel_color,
        activeforeground=text_color,
        highlightthickness=0,
        bd=0,
    )
    prof_cb.pack(side="left", padx=(0, 8))

    # Provide a small label if advanced filter is available
    if _ADVANCED_PROFANITY_AVAILABLE:
        adv_label = tk.Label(btn_frame, text="(advanced filter available)", bg=panel_color, fg="#9fb6ff")
        adv_label.pack(side="left", padx=(0, 8))

    generate_btn = ColoredButton(
        btn_frame,
        text="Generate",
        bg=button_color,
        fg=text_color,
        active_bg=accent_color,
        active_fg="#ffffff",
        disabled_bg="#2a2c30",
        disabled_fg="#7f8a97",
        command=on_generate,
        relief="flat",
        borderwidth=0,
    )
    generate_btn.pack(anchor="e", padx=4)

    # poll out_queue periodically and update output_box
    def poll_output():
        if out_queue is not None:
            try:
                while True:
                    processed = out_queue.get_nowait()
                    # Apply profanity filter if enabled
                    if prof_var.get():
                        try:
                            processed = profanity_filter(processed)
                        except Exception:
                            pass

                    output_box.config(state="normal")
                    output_box.delete("1.0", "end")
                    output_box.insert("1.0", processed)
                    output_box.config(state="disabled")
            except Exception:
                pass
        root.after(100, poll_output)

    root.after(100, poll_output)

    def bind_generate(event=None):
        on_generate()
        return "break"

    root.bind_all("<Control-Return>", bind_generate)
    root.bind_all("<Command-Return>", bind_generate)

    return root