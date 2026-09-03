from pathlib import Path
import time, ctypes, pyautogui, pyperclip, win32con, win32gui, win32process

DATA = Path(__file__).resolve().parent / "data"
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
    time.sleep(0.35)


def shot(n):
    pyautogui.screenshot(str(DATA / n))
    log("shot " + n)


def paste(t):
    pyperclip.copy(t)
    time.sleep(0.05)
    pyautogui.hotkey("ctrl", "v")


if __name__ == "__main__":
    focus()
    pyautogui.click(400, 50)
    time.sleep(0.15)
    pyautogui.hotkey("ctrl", "a")
    paste("https://kuhhospital.amocrm.ru/settings/")
    pyautogui.press("enter")
    time.sleep(5)
    focus()
    shot("fill_settings.png")
    log("opened settings")
