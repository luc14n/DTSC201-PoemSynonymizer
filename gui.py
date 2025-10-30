import tkinter as tk
from tkinter import font
from ColoredButton import ColoredButton
import queue as _queue

def create_gui(in_queue=None, out_queue=None):
    root = tk.Tk()
    root.title("Poem Synonymizer")
    root.geometry("900x500")
    root.minsize(600, 300)

    # Colors (dark mode, renamed for clarity)
    bg_color = "#0f1115"         # main window background
    panel_color = "#15161a"      # panel / frame background
    input_color = "#1b1d22"      # input Text background
    output_color = "#111214"     # output Text background
    text_color = "#e6eef8"       # primary text / foreground color
    button_color = "#23262a"     # button background
    accent_color = "#3A90FF"     # accent color (blue) for active/hover
    accent_color_press = "#226fbd"  # accent color (blue) for active/hover

    root.configure(bg=bg_color)

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

    # Generate button below input
    def on_generate():
        text = input_box.get("1.0", "end-1c")
        if not text.strip():
            output_box.config(state="normal")
            output_box.delete("1.0", "end")
            output_box.config(state="disabled")
            return

        def _send_with_retry(payload, attempt=0):
            try:
                in_queue.put_nowait(payload)
                # optionally provide quick feedback (flash or disable briefly)
                generate_btn.disable()
                root.after(150, generate_btn.enable)
            except _queue.Full:
                # don't block main thread; retry with small backoff
                if attempt < 6:
                    generate_btn.disable()
                    delay_ms = 50 * (2 ** attempt)  # exponential backoff
                    root.after(delay_ms, lambda: _send_with_retry(payload, attempt + 1))
                else:
                    # final fallback: re-enable button so user can try again
                    generate_btn.enable()

        if in_queue is not None:
            _send_with_retry(text)

    btn_frame = tk.Frame(left_frame, bg=panel_color)
    btn_frame.pack(fill="x", pady=(8, 0))

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
                    output_box.config(state="normal")
                    output_box.delete("1.0", "end")
                    output_box.insert("1.0", processed)
                    output_box.config(state="disabled")
            except Exception:
                # queue empty
                pass
        root.after(100, poll_output)

    root.after(100, poll_output)

    def bind_generate(event=None):
        on_generate()
        return "break"

    root.bind_all("<Control-Return>", bind_generate)
    root.bind_all("<Command-Return>", bind_generate)

    return root