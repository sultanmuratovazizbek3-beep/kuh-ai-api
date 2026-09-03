"""Fill amoCRM private widget form in the already-open Yandex window."""

from __future__ import annotations

import time
import ctypes
from pathlib import Path

import pyautogui
import pyperclip
import win32con
import win32gui
import win32process

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
ZIP_PATH = str(ROOT / "public" / "tabel-widget.zip")
LOG = DATA / "fill_tabel_form.log"
URL = "https://kuhhospital.amocrm.ru/amo-market/application/"

pyautogui.FAILSAFE = False
pyautogui.PAUSE = 0.05


def log(msg: str) -> None:
    line = msg
    print(line, flush=True)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def windows():
    out = []

    def cb(hwnd, _):
        if win32gui.IsWindowVisible(hwnd):
            t = win32gui.GetWindowText(hwnd) or ""
            if t.strip():
                out.append((hwnd, t))

    win32gui.EnumWindows(cb, None)
    return out


def minimize_others() -> None:
    for hwnd, t in windows():
        tl = t.lower()
        if "яндекс" in tl and "браузер" in tl:
            continue
        if "program manager" in tl:
            continue
        try:
            win32gui.ShowWindow(hwnd, win32con.SW_MINIMIZE)
        except Exception:
            pass


def yandex_hwnd():
    for hwnd, t in windows():
        if "яндекс" in t.lower() and "браузер" in t.lower():
            return hwnd
    return None


def force_fg(hwnd) -> None:
    fg = win32gui.GetForegroundWindow()
    cur = win32process.GetWindowThreadProcessId(fg)[0]
    tgt = win32process.GetWindowThreadProcessId(hwnd)[0]
    ctypes.windll.user32.AttachThreadInput(cur, tgt, True)
    win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
    win32gui.ShowWindow(hwnd, win32con.SW_MAXIMIZE)
    try:
        win32gui.SetForegroundWindow(hwnd)
    except Exception:
        pass
    ctypes.windll.user32.AttachThreadInput(cur, tgt, False)


def focus() -> None:
    minimize_others()
    hwnd = yandex_hwnd()
    if not hwnd:
        raise RuntimeError("Yandex window not found")
    force_fg(hwnd)
    time.sleep(0.35)


def shot(name: str) -> None:
    p = DATA / name
    pyautogui.screenshot(str(p))
    log(f"shot {p}")


def paste(text: str) -> None:
    pyperclip.copy(text)
    time.sleep(0.08)
    pyautogui.hotkey("ctrl", "v")
    time.sleep(0.15)


def open_url(url: str) -> None:
    focus()
    pyautogui.click(380, 50)
    time.sleep(0.2)
    pyautogui.hotkey("ctrl", "a")
    time.sleep(0.1)
    paste(url)
    pyautogui.press("enter")
    time.sleep(6)
    focus()


def main() -> None:
    LOG.write_text("", encoding="utf-8")
    log("start")
    focus()
    shot("fill_0.png")

    open_url(URL)
    shot("fill_1.png")
    log("page opened, waiting for next step")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        log(f"ERROR {e}")
        raise
