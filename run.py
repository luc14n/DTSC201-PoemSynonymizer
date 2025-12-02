# python
"""
Entry point for the Poem Synonymizer application.

Provides a small orchestration layer that wires together the GUI and a background
worker running the `processor`. Ensures graceful shutdown, signal handling, and
clear logging for troubleshooting.

Usage:
- Run this module as `python run.py`.
"""
from __future__ import annotations
import logging
import platform
import queue
import signal
import threading
import time
from typing import Optional

from gui import create_gui
from processer import processor  # keep original module name used in project

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


def run_gui(in_q: "queue.Queue", out_q: "queue.Queue", stop_event: threading.Event) -> None:
    """
    Create and run the GUI. If `stop_event` is set, the GUI will be asked to
    quit via the Tk event loop.

    This function blocks until the GUI is closed.
    """
    root = create_gui(in_queue=in_q, out_queue=out_q)

    def _poll_stop() -> None:
        if stop_event.is_set():
            try:
                root.quit()
            except Exception:
                logger.exception("Failed to quit GUI cleanly")
            return
        root.after(100, _poll_stop)

    root.after(100, _poll_stop)
    try:
        root.mainloop()
    except Exception:
        logger.exception("GUI mainloop exited with exception")
    finally:
        try:
            root.destroy()
        except Exception:
            pass
        logger.info("GUI has exited")


def worker(in_q: "queue.Queue", out_q: "queue.Queue", stop_event: threading.Event) -> None:
    """
    Background worker that consumes text payloads from `in_q`, processes them
    with `processor`, and pushes results to `out_q`.

    Protocol:
    - Receiving `None` on `in_q` is a sentinel to stop immediately.
    - The `stop_event` may be set externally to indicate shutdown; worker will
      prefer the sentinel but will also exit when the event is set and queue is empty.
    """
    poem_processor = processor()
    logger.info("Worker started")
    while True:
        if stop_event.is_set():
            # Attempt a non-blocking check to finish promptly
            try:
                item = in_q.get_nowait()
            except queue.Empty:
                break
        try:
            item = in_q.get(timeout=0.5)
        except queue.Empty:
            continue

        if item is None:
            logger.info("Worker received sentinel; exiting")
            break

        try:
            logger.debug("Worker received payload for processing")
            processed = poem_processor.process(item)
            out_q.put(processed)
            logger.debug("Worker processed payload and posted result")
        except Exception:
            logger.exception("Unexpected error while processing payload")
    logger.info("Worker stopped")


def _setup_signal_handlers(stop_event: threading.Event, in_q: "queue.Queue") -> None:
    """
    Arrange for SIGINT and SIGTERM to request shutdown. Handler sets the stop
    event and enqueues the sentinel to unblock the worker.
    """

    def _handle(signum, _frame):
        logger.info("Received signal %s; initiating shutdown", signum)
        stop_event.set()
        try:
            in_q.put_nowait(None)
        except Exception:
            # If queue is full or closed, ignore; worker will still exit on stop_event
            pass

    signal.signal(signal.SIGINT, _handle)
    try:
        signal.signal(signal.SIGTERM, _handle)
    except AttributeError:
        # Windows may not have SIGTERM
        pass


def main() -> int:
    """
    Set up queues, threads, and run the application. Returns exit code.
    """
    in_q: "queue.Queue" = queue.Queue()   # GUI -> worker
    out_q: "queue.Queue" = queue.Queue()  # worker -> GUI
    stop_event = threading.Event()

    _setup_signal_handlers(stop_event, in_q)

    system = platform.system()
    logger.info("Platform detected: %s", system)

    # Start worker thread (non-daemon to enable orderly shutdown and join)
    worker_thread = threading.Thread(target=worker, name="PoemWorker", args=(in_q, out_q, stop_event), daemon=False)
    worker_thread.start()

    try:
        if system == "Darwin":
            # macOS: GUI must run on main thread
            run_gui(in_q, out_q, stop_event)
        else:
            # Other platforms: run GUI in a dedicated thread and keep main thread for signal handling
            gui_thread = threading.Thread(target=run_gui, name="GUIThread", args=(in_q, out_q, stop_event), daemon=False)
            gui_thread.start()
            # Wait until either the GUI thread ends or a stop is requested
            while gui_thread.is_alive() and not stop_event.is_set():
                time.sleep(0.2)
            # If a stop was requested, ensure GUI is asked to quit
            stop_event.set()
            try:
                in_q.put_nowait(None)
            except Exception:
                pass
            gui_thread.join(timeout=5)
    except Exception:
        logger.exception("Unhandled exception in main runtime")
    finally:
        # Ensure worker will terminate
        stop_event.set()
        try:
            in_q.put_nowait(None)
        except Exception:
            pass
        worker_thread.join(timeout=5)
        logger.info("Application shutdown complete")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())