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


class OcrService:
    def __init__(self):
        self._lock = threading.Lock()
        self._process = None

    def _read_exact(self, size):
        data = b""

        while len(data) < size:
            chunk = self._process.stdout.read(size - len(data))

            if not chunk:
                raise RuntimeError("OCR process exited")

            data += chunk

        return data

    def _receive(self):
        size = struct.unpack("<I", self._read_exact(4))[0]
        return pickle.loads(self._read_exact(size))

    def _start(self):
        self._process = subprocess.Popen(
            [sys.executable, str(WORKER_PATH)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
        )
        status, _ = self._receive()

        if status != "ready":
            raise RuntimeError("OCR process failed to start")

    def _stop(self):
        process, self._process = self._process, None

        if process is not None and process.poll() is None:
            process.kill()

    def start(self):
        with self._lock:
            if self._process is None:
                self._start()

    def readtext(self, image, **kwargs):
        with self._lock:
            for attempt in range(2):
                try:
                    if self._process is None or self._process.poll() is not None:
                        self._start()

                    data = pickle.dumps((image, kwargs))
                    self._process.stdin.write(struct.pack("<I", len(data)) + data)
                    self._process.stdin.flush()
                    status, payload = self._receive()

                    if status == "ok":
                        return payload

                    raise RuntimeError(payload)
                except Exception:
                    logger.exception("OCR request failed (attempt %d)", attempt + 1)
                    self._stop()

        raise RuntimeError("OCR service unavailable")


_SERVICE = None


def get_service():
    global _SERVICE

    if _SERVICE is None:
        _SERVICE = OcrService()

    return _SERVICE
