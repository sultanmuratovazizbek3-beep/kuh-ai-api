from __future__ import annotations

import time
from pathlib import Path

import pyautogui
import pyperclip
import win32con
import win32gui
import win32process
import ctypes

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
LOG = DATA / "fill_tabel_form.log"
pyautogui.FAILSAFE = False


def log(m):
    print(m, flush=True)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(m + "\n")


def windows():
    out = []

    def cb(hwnd, _):
        if win32gui.IsWindowVisible(hwnd):
            t = win32gui.GetWindowText(hwnd) or ""
            if t.strip():
                out.append((hwnd, t))

    win32gui.EnumWindows(cb, None)
    return out


def focus():
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
    hwnd = None
    for h, t in windows():
        if "яндекс" in t.lower() and "браузер" in t.lower():
            hwnd = h
            break
    if not hwnd:
        raise RuntimeError("no yandex")
    fg = win32gui.GetForegroundWindow()
    cur = win32process.GetWindowThreadProcessId(fg)[0]
    tgt = win32process.GetWindowThreadProcessId(hwnd)[0]
    ctypes.windll.user32.AttachThreadInput(cur, tgt, True)
    win32gui.ShowWindow(hwnd, win32con.SW_MAXIMIZE)
    try:
        win32gui.SetForegroundWindow(hwnd)
    except Exception:
        pass
    ctypes.windll.user32.AttachThreadInput(cur, tgt, False)
    time.sleep(0.3)


def shot(name):
    p = DATA / name
    pyautogui.screenshot(str(p))
    log("shot " + str(p))


def paste(text):
    pyperclip.copy(text)
    time.sleep(0.05)
    pyautogui.hotkey("ctrl", "v")
    time.sleep(0.12)


def open_url(url):
    focus()
    pyautogui.click(400, 50)
    time.sleep(0.2)
    pyautogui.hotkey("ctrl", "a")
    time.sleep(0.08)
    paste(url)
    pyautogui.press("enter")
    time.sleep(6)
    focus()


if __name__ == "__main__":
    open_url("https://kuhhospital.amocrm.ru/settings/widgets/")
    shot("fill_widgets.png")
    log("opened settings/widgets")
