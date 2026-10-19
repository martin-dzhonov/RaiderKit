"""EasyOCR host process. Runs torch outside the Qt process to avoid native crashes."""

import os
import pickle
import struct
import sys

os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")


def _read_exact(stream, size):
    data = b""

    while len(data) < size:
        chunk = stream.read(size - len(data))

        if not chunk:
            return None

        data += chunk

    return data


def _std_stream(handle_id, mode):
    """Open a standard handle directly; GUI-subsystem builds can lack sys.stdin/stdout."""
    if os.name == "nt":
        import ctypes
        import msvcrt

        kernel32 = ctypes.windll.kernel32
        kernel32.GetStdHandle.restype = ctypes.c_void_p
        handle = kernel32.GetStdHandle(handle_id)
        fd = msvcrt.open_osfhandle(handle, os.O_RDONLY if mode == "rb" else 0)
        return os.fdopen(fd, mode)

    return os.fdopen(os.dup(0 if mode == "rb" else 1), mode)


def main():
    protocol_in = _std_stream(-10, "rb")
    protocol_out = _std_stream(-11, "wb")
    sys.stdout = sys.stderr = open(os.devnull, "w")

    import easyocr

    reader = easyocr.Reader(["en"], gpu=False, verbose=False)

    def send(payload):
        data = pickle.dumps(payload)
        protocol_out.write(struct.pack("<I", len(data)) + data)
        protocol_out.flush()

    send(("ready", None))

    while True:
        header = _read_exact(protocol_in, 4)

        if header is None:
            return

        body = _read_exact(protocol_in, struct.unpack("<I", header)[0])

        if body is None:
            return

        image, kwargs = pickle.loads(body)

        try:
            send(("ok", reader.readtext(image, **kwargs)))
        except Exception as error:
            send(("error", repr(error)))


if __name__ == "__main__":
    main()
