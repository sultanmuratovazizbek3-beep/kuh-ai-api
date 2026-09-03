"""
CRM AI Desk — reliable desktop launcher.

Starts:
  1) API process (separate pythonw)  → stays alive
  2) UI process (pywebview window)   → can reopen without killing API

Double-click Launch_CRM_AI_Desk.vbs / desktop shortcut.
"""

from __future__ import annotations

import multiprocessing
import os
import socket
import subprocess
import sys
import time
import traceback
from pathlib import Path


def root_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


ROOT = root_dir()
os.chdir(str(ROOT))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DATA = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "CRMAIDesk"
LOG_DIR = DATA / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG = LOG_DIR / "app.log"
PORT = int(os.environ.get("API_PORT", "8090"))
PID_API = DATA / "api.pid"


def log(msg: str) -> None:
    line = f"{time.strftime('%Y-%m-%d %H:%M:%S')} {msg}\n"
    try:
        with LOG.open("a", encoding="utf-8") as f:
            f.write(line)
    except Exception:
        pass


def port_alive(port: int = PORT) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.4):
            return True
    except OSError:
        return False


def py_exe(prefer_console: bool = False) -> str:
    """API: prefer python.exe (more reliable). UI: pythonw (no console)."""
    venv_w = ROOT / ".venv" / "Scripts" / "pythonw.exe"
    venv_p = ROOT / ".venv" / "Scripts" / "python.exe"
    if prefer_console:
        if venv_p.exists():
            return str(venv_p)
        if venv_w.exists():
            return str(venv_w)
    else:
        if venv_w.exists():
            return str(venv_w)
        if venv_p.exists():
            return str(venv_p)
    return sys.executable


def spawn_detached(exe: str, script: Path) -> int | None:
    """Start a process that outlives this launcher (escapes shell Job Objects)."""
    # 1) WMI Win32_Process.Create — survives agent/shell job teardown on Windows
    try:
        import pythoncom  # type: ignore
        import win32com.client  # type: ignore

        pythoncom.CoInitialize()
        wmi = win32com.client.GetObject("winmgmts:")
        startup = wmi.Get("Win32_ProcessStartup").SpawnInstance_()
        startup.ShowWindow = 0
        cmd = f'"{exe}" "{script}"'
        ret = wmi.Get("Win32_Process").Create(cmd, str(ROOT), startup)
        # ret can be (rc, pid) or object with properties depending on bridge
        if isinstance(ret, tuple):
            rc, pid = ret[0], ret[1] if len(ret) > 1 else None
        else:
            rc = getattr(ret, "ReturnValue", 1)
            pid = getattr(ret, "ProcessId", None)
        if int(rc) == 0 and pid:
            log(f"WMI spawn ok pid={pid} {script.name}")
            return int(pid)
        log(f"WMI spawn rc={rc} for {script.name}")
    except Exception as e:
        log(f"WMI spawn skip: {e}")

    # 2) CIM via PowerShell one-liner (no pywin32 required)
    try:
        cmd_line = f'"{exe}" "{script}"'
        ps = (
            f"$r=Invoke-CimMethod -ClassName Win32_Process -MethodName Create "
            f"-Arguments @{{CommandLine='{cmd_line.replace(chr(39), chr(39)+chr(39))}';"
            f"CurrentDirectory='{str(ROOT)}'}}; "
            f"if($r.ReturnValue -eq 0){{$r.ProcessId}} else {{exit $r.ReturnValue}}"
        )
        out = subprocess.check_output(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps],
            cwd=str(ROOT),
            text=True,
            timeout=15,
        ).strip()
        if out.isdigit():
            log(f"CIM spawn ok pid={out} {script.name}")
            return int(out)
    except Exception as e:
        log(f"CIM spawn skip: {e}")

    # 3) DETACHED + breakaway Popen fallback
    creation = 0x00000008 | 0x00000200 | 0x01000000
    proc = subprocess.Popen(
        [exe, str(script)],
        cwd=str(ROOT),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=creation,
        close_fds=True,
    )
    log(f"Popen spawn pid={proc.pid} {script.name}")
    return proc.pid


def start_api_process() -> None:
    if port_alive():
        # verify health, not only TCP
        try:
            import urllib.request

            with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/health", timeout=1.5) as r:
                if r.status == 200:
                    log("API already listening (health ok)")
                    return
        except Exception:
            log("port open but health fail — will not start second API")
            return

    api_script = ROOT / "api_main.py"
    if not api_script.exists():
        log("FATAL: api_main.py missing")
        raise FileNotFoundError(str(api_script))

    exe = py_exe(prefer_console=True)
    log(f"starting API process: {exe} api_main.py")
    try:
        pid = spawn_detached(exe, api_script)
        if pid:
            try:
                PID_API.write_text(str(pid), encoding="utf-8")
            except Exception:
                pass
            log(f"API pid={pid}")
    except Exception as e:
        log(f"API spawn failed: {e}")
        raise

    for i in range(100):
        if port_alive():
            try:
                import urllib.request

                with urllib.request.urlopen(
                    f"http://127.0.0.1:{PORT}/health", timeout=0.8
                ) as r:
                    if r.status == 200:
                        log(f"API ready (health) in {i * 0.15:.1f}s")
                        return
            except Exception:
                pass
        time.sleep(0.15)
    log("API timeout after start")


def worker_alive() -> bool:
    """True if worker.pid process still exists."""
    pid_path = DATA / "worker.pid"
    try:
        if not pid_path.exists():
            return False
        pid = int(pid_path.read_text(encoding="utf-8").strip())
        import ctypes

        kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
        SYNCHRONIZE = 0x00100000
        handle = kernel32.OpenProcess(SYNCHRONIZE, False, pid)
        if handle:
            kernel32.CloseHandle(handle)
            return True
        return False
    except Exception:
        return False


def start_background_worker() -> None:
    """Detached continuous worker: collect → STT → analyze → notes to amo."""
    os.environ.setdefault("WRITE_AMO_CALL_NOTES", "1")
    if worker_alive():
        log("worker already running")
        return
    worker = ROOT / "worker_main.py"
    if not worker.exists():
        log("worker_main.py missing — skip continuous worker")
        return
    exe = py_exe(prefer_console=True)
    log(f"starting worker: {exe} worker_main.py")
    try:
        pid = spawn_detached(exe, worker)
        log(f"worker pid={pid}")
    except Exception as e:
        log(f"worker spawn failed: {e}")


def open_ui_window() -> None:
    ui_script = ROOT / "ui_main.py"
    exe = py_exe(prefer_console=False)
    log(f"starting UI: {exe} ui_main.py")
    try:
        spawn_detached(exe, ui_script)
    except Exception:
        # fallback: open UI in this process
        log("UI spawn failed — inline window")
        import ui_main

        ui_main.main()
        return

    # Wait a moment to confirm UI process / API still ok
    time.sleep(1.5)
    if not port_alive():
        log("WARNING: API died after UI start")
        try:
            import ctypes

            ctypes.windll.user32.MessageBoxW(
                0,
                "Сервер не отвечает после запуска.\n"
                f"См. логи:\n{LOG_DIR}",
                "CRM AI Desk",
                0x10,
            )
        except Exception:
            pass
    else:
        log("launch complete — API up, UI started")


def main() -> None:
    multiprocessing.freeze_support()
    log("=== CRM AI Desk launcher ===")
    try:
        from profiles import get_credentials, import_from_env

        if not get_credentials():
            import_from_env(ROOT / ".env")
    except Exception as e:
        log(f"profiles: {e}")

    start_api_process()
    if not port_alive():
        log("API not up — abort UI")
        try:
            import ctypes

            ctypes.windll.user32.MessageBoxW(
                0,
                f"Не удалось запустить сервер (порт {PORT}).\n"
                f"Log: {LOG}\nAPI log: {LOG_DIR / 'api.log'}",
                "CRM AI Desk",
                0x10,
            )
        except Exception:
            pass
        return

    # Worker only if we started fresh (or always light — ok either way)
    start_background_worker()
    open_ui_window()
    log("launcher exit (API keeps running)")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        log("FATAL\n" + traceback.format_exc())
        try:
            import ctypes

            ctypes.windll.user32.MessageBoxW(
                0,
                f"CRM AI Desk error.\n{LOG}",
                "CRM AI Desk",
                0x10,
            )
        except Exception:
            pass
        raise
