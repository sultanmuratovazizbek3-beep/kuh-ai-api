"""Pack widget/ into public/kuh-assistant-widget.zip for upload to amoCRM."""

from __future__ import annotations

import struct
import zipfile
import zlib
from pathlib import Path

BASE = Path(__file__).resolve().parent
WIDGET = BASE / "widget"
OUT = BASE / "public" / "kuh-assistant-widget.zip"


def write_minimal_png(path: Path, r: int = 37, g: int = 99, b: int = 235) -> None:
    """Solid-color 64x64 PNG without external deps."""
    width = height = 64

    def chunk(tag: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + tag
            + data
            + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
        )

    raw = b""
    for _y in range(height):
        raw += b"\x00"  # filter None
        raw += bytes([r, g, b]) * width

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    png = b"\x89PNG\r\n\x1a\n"
    png += chunk(b"IHDR", ihdr)
    png += chunk(b"IDAT", zlib.compress(raw, 9))
    png += chunk(b"IEND", b"")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(png)


def build() -> Path:
    logo = WIDGET / "images" / "logo.png"
    logo_min = WIDGET / "images" / "logo_min.png"
    write_minimal_png(logo, 37, 99, 235)
    write_minimal_png(logo_min, 37, 99, 235)

    required = [
        "manifest.json",
        "script.js",
        "style.css",
        "i18n/ru.json",
        "images/logo.png",
        "images/logo_min.png",
    ]
    for rel in required:
        p = WIDGET / rel
        if not p.exists():
            raise FileNotFoundError(p)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(OUT, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path in WIDGET.rglob("*"):
            if path.is_file():
                # zip must have files at root of archive for amoCRM
                arc = path.relative_to(WIDGET).as_posix()
                zf.write(path, arcname=arc)
    print(f"Built: {OUT} ({OUT.stat().st_size} bytes)")
    return OUT


if __name__ == "__main__":
    build()
