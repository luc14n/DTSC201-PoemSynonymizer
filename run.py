import threading
import platform
import time
import queue
from codecs import BOM_UTF16_BE

from gui import create_gui
from processer import processor

def run_gui(in_queue, out_queue):
    root = create_gui(in_queue=in_queue, out_queue=out_queue)
    root.mainloop()

def worker(in_queue, out_queue):
    poem_processor = processor()

    while True:
        try:
            text = in_queue.get()  # block until available
            if text is None:
                break  # sentinel to stop worker
            print(f"Worker received {text} for processing.")

            processed = poem_processor.process(text)
            out_queue.put(processed)
            print(f"Worker output {processed} for reading.")
        except Exception:
            continue

if __name__ == "__main__":
    in_queue = queue.Queue()  # GUI -> worker
    out_queue = queue.Queue()  # worker -> GUI

    system = platform.system()

    if system == "Darwin":
        # macOS: run GUI on main thread; worker in background
        t = threading.Thread(target=worker, args=(in_queue, out_queue), daemon=True)
        t.start()
        run_gui(in_queue, out_queue)
    else:
        # Other platforms: GUI may run in a separate thread
        worker_thread = threading.Thread(target=worker, args=(in_queue, out_queue), daemon=True)
        worker_thread.start()
        gui_thread = threading.Thread(target=run_gui, args=(in_queue, out_queue), daemon=True)
        gui_thread.start()
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            pass