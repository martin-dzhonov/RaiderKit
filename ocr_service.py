"""Client for the EasyOCR subprocess; mimics Reader.readtext."""

import logging
import pickle
import struct
import subprocess
import sys
import threading
from pathlib import Path

logger = logging.getLogger(__name__)

WORKER_PATH = Path(__file__).with_name("ocr_worker.py")
WORKER_FLAG = "--ocr-worker"


def _worker_command():
    """Return the correct command for source and packaged builds."""
    if getattr(sys, "frozen", False) or "__compiled__" in globals():
        return [sys.executable, WORKER_FLAG]

    return [sys.executable, str(WORKER_PATH)]


class OcrService:
    def __init__(self):
        self._lock = threading.Lock()
        self._process = None

    def _read_exact(self, size):
        data = bytearray()

        while len(data) < size:
            chunk = self._process.stdout.read(size - len(data))

            if not chunk:
                raise RuntimeError(
                    f"OCR worker exited unexpectedly "
                    f"(exit code: {self._process.poll()})"
                )

            data.extend(chunk)

        return bytes(data)

    def _receive(self):
        size = struct.unpack("<I", self._read_exact(4))[0]
        return pickle.loads(self._read_exact(size))

    def _start(self):
        command = _worker_command()
        logger.info("Starting OCR worker: %s", command)
        print(f"OCR worker command: {command}", file=sys.stderr, flush=True)

        self._process = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=None,  # Temporary debugging: show worker errors.
            # Keep CREATE_NO_WINDOW disabled while debugging.
        )

        try:
            status, payload = self._receive()

            if status != "ready":
                raise RuntimeError(f"OCR worker failed to initialize: {payload}")

            logger.info("OCR worker is ready.")

        except Exception:
            self._stop()
            raise

    def _stop(self):
        process, self._process = self._process, None

        if process is not None:
            if process.poll() is None:
                process.kill()

            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                logger.warning("OCR worker did not exit promptly.")

    def start(self):
        with self._lock:
            if self._process is None or self._process.poll() is not None:
                self._stop()
                self._start()

    def readtext(self, image, **kwargs):
        with self._lock:
            for attempt in range(2):
                try:
                    if self._process is None or self._process.poll() is not None:
                        self._stop()
                        self._start()

                    data = pickle.dumps((image, kwargs))
                    self._process.stdin.write(struct.pack("<I", len(data)) + data)
                    self._process.stdin.flush()

                    status, payload = self._receive()

                    if status == "ok":
                        return payload

                    raise RuntimeError(f"OCR request failed: {payload}")

                except Exception:
                    logger.exception("OCR request failed (attempt %d)", attempt + 1)
                    self._stop()

        raise RuntimeError("OCR service unavailable")


_SERVICE = None
_SERVICE_LOCK = threading.Lock()


def get_service():
    global _SERVICE

    with _SERVICE_LOCK:
        if _SERVICE is None:
            _SERVICE = OcrService()

        return _SERVICE
