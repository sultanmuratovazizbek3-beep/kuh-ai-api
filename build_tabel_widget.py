"""Pack widget-tabel/ into public/tabel-widget.zip for upload to amoCRM."""

from __future__ import annotations

import json
import shutil
import struct
import zipfile
import zlib
from pathlib import Path

BASE = Path(__file__).resolve().parent
WIDGET = BASE / "widget-tabel"
OUT = BASE / "public" / "tabel-widget.zip"
OUT_WIDGET = BASE / "public" / "widget.zip"
DESKTOP = Path.home() / "Desktop" / "tabel-widget.zip"
DESKTOP_WIDGET = Path.home() / "Desktop" / "widget.zip"

LOGOS = {
    "images/logo_main.png": (400, 272),
    "images/logo.png": (130, 100),
    "images/logo_medium.png": (240, 84),
    "images/logo_small.png": (108, 108),
    "images/logo_min.png": (84, 84),
}

REQUIRED = [
    "manifest.json",
    "script.js",
    "style.css",
    "i18n/ru.json",
    *LOGOS.keys(),
]


def write_minimal_png(
    path: Path,
    width: int,
    height: int,
    r: int = 34,
    g: int = 197,
    b: int = 94,
) -> None:

    def chunk(tag: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + tag
            + data
            + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
        )

    raw = b""
    for _y in range(height):
        raw += b"\x00"
        raw += bytes([r, g, b]) * width

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    png = b"\x89PNG\r\n\x1a\n"
    png += chunk(b"IHDR", ihdr)
    png += chunk(b"IDAT", zlib.compress(raw, 9))
    png += chunk(b"IEND", b"")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(png)


def png_size(path: Path) -> tuple[int, int]:
    data = path.read_bytes()
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError(f"{path} is not a PNG")
    w, h = struct.unpack(">II", data[16:24])
    return w, h


def load_json_utf8(path: Path) -> dict:
    raw = path.read_bytes()
    if raw.startswith(b"\xef\xbb\xbf"):
        raise ValueError(f"{path} has UTF-8 BOM; amoCRM expects UTF-8 without BOM")
    return json.loads(raw.decode("utf-8"))


def validate_i18n(manifest: dict, i18n: dict) -> None:
    widget = manifest.get("widget") or {}
    for key in ("name", "description", "short_description"):
        ref = widget.get(key)
        if ref != f"widget.{key}":
            raise ValueError(f"manifest widget.{key} must be 'widget.{key}', got {ref!r}")
        if key not in (i18n.get("widget") or {}):
            raise ValueError(f"i18n/ru.json missing widget.{key}")
    settings = manifest.get("settings") or {}
    i18n_settings = i18n.get("settings") or {}
    for code, field in settings.items():
        name = (field or {}).get("name")
        if name != f"settings.{code}":
            raise ValueError(f"manifest settings.{code}.name must be 'settings.{code}', got {name!r}")
        if code not in i18n_settings:
            raise ValueError(f"i18n/ru.json missing settings.{code}")


def build() -> Path:
    for rel, (w, h) in LOGOS.items():
        write_minimal_png(WIDGET / rel, w, h, 34, 197, 94)

    for rel in REQUIRED:
        p = WIDGET / rel
        if not p.exists():
            raise FileNotFoundError(p)

    manifest = load_json_utf8(WIDGET / "manifest.json")
    i18n = load_json_utf8(WIDGET / "i18n" / "ru.json")
    validate_i18n(manifest, i18n)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(OUT, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for rel in REQUIRED:
            zf.write(WIDGET / rel, arcname=rel)

    DESKTOP.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(OUT, OUT_WIDGET)
    shutil.copy2(OUT, DESKTOP)
    shutil.copy2(OUT, DESKTOP_WIDGET)

    with zipfile.ZipFile(OUT, "r") as zf:
        names = zf.namelist()
    print(f"Built: {OUT} ({OUT.stat().st_size} bytes)")
    print(f"Desktop: {DESKTOP_WIDGET} ({DESKTOP_WIDGET.stat().st_size} bytes)")
    for rel, expected in LOGOS.items():
        got = png_size(WIDGET / rel)
        print(f"PNG {rel}: {got[0]}x{got[1]} (need {expected[0]}x{expected[1]})")
        if got != expected:
            raise ValueError(f"{rel} size {got} != {expected}")
    print("Zip namelist:")
    for name in names:
        print(f"  {name}")
    return OUT


if __name__ == "__main__":
    build()
