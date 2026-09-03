"""
One-click installer GUI for CRM AI Desk.
Double-click Setup → extract → shortcuts → launch.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import threading
import tkinter as tk
import zipfile
from pathlib import Path
from tkinter import messagebox, ttk


APP_NAME = "CRM AI Desk"
APP_VERSION = "1.0.0"
INSTALL_DIR_NAME = "CRMAIDesk"


def resource_path(*parts: str) -> Path:
    if getattr(sys, "frozen", False):
        base = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    else:
        base = Path(__file__).resolve().parent
    return base.joinpath(*parts)


def install_root() -> Path:
    local = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    return Path(local) / INSTALL_DIR_NAME


def find_payload_zip() -> Path:
    candidates = [
        resource_path("payload", "app.zip"),
        resource_path("release", "CRM-AI-Desk-Setup-1.0.0.zip"),
        Path(__file__).resolve().parent / "release" / "CRM-AI-Desk-Setup-1.0.0.zip",
        Path(sys.executable).resolve().parent / "payload" / "app.zip",
        Path(sys.executable).resolve().parent / "CRM-AI-Desk-Setup-1.0.0.zip",
    ]
    for p in candidates:
        if p.exists():
            return p
    raise FileNotFoundError(
        "Не найден пакет приложения (payload/app.zip). Пересоберите Setup."
    )


def create_shortcut(target: Path, link_path: Path, workdir: Path) -> None:
    try:
        import win32com.client  # type: ignore

        shell = win32com.client.Dispatch("WScript.Shell")
        sc = shell.CreateShortCut(str(link_path))
        sc.Targetpath = str(target)
        sc.WorkingDirectory = str(workdir)
        sc.Description = APP_NAME
        sc.save()
        return
    except Exception:
        pass
    # fallback VBS
    vbs = workdir / "_mk_shortcut.vbs"
    vbs.write_text(
        "\n".join(
            [
                'Set o = CreateObject("WScript.Shell")',
                f'Set s = o.CreateShortcut("{str(link_path).replace(chr(92), chr(92)+chr(92))}")',
                f's.TargetPath = "{str(target).replace(chr(92), chr(92)+chr(92))}"',
                f's.WorkingDirectory = "{str(workdir).replace(chr(92), chr(92)+chr(92))}"',
                f's.Description = "{APP_NAME}"',
                "s.Save",
            ]
        ),
        encoding="ascii",
        errors="replace",
    )
    subprocess.run(["cscript", "//nologo", str(vbs)], check=False, capture_output=True)
    try:
        vbs.unlink()
    except Exception:
        pass


def write_uninstaller(app_dir: Path) -> Path:
    un = app_dir / "Uninstall.ps1"
    desktop = Path.home() / "Desktop"
    onedrive = Path.home() / "OneDrive" / "Desktop"
    programs = Path(os.environ.get("APPDATA", "")) / "Microsoft" / "Windows" / "Start Menu" / "Programs"
    un.write_text(
        f"""$ErrorActionPreference = 'SilentlyContinue'
Remove-Item '{desktop / (APP_NAME + ".lnk")}' -Force
Remove-Item '{onedrive / (APP_NAME + ".lnk")}' -Force
Remove-Item '{programs / (APP_NAME + ".lnk")}' -Force
Remove-Item '{install_root()}' -Recurse -Force
Remove-Item 'HKCU:\\Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\CRMAIDesk' -Recurse -Force
Write-Host 'CRM AI Desk removed'
""",
        encoding="utf-8",
    )
    return un


def register_uninstall(app_dir: Path, uninstaller: Path) -> None:
    try:
        import winreg

        key = winreg.CreateKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Uninstall\CRMAIDesk",
        )
        winreg.SetValueEx(key, "DisplayName", 0, winreg.REG_SZ, APP_NAME)
        winreg.SetValueEx(key, "DisplayVersion", 0, winreg.REG_SZ, APP_VERSION)
        winreg.SetValueEx(key, "Publisher", 0, winreg.REG_SZ, "CRM AI Desk")
        winreg.SetValueEx(key, "InstallLocation", 0, winreg.REG_SZ, str(app_dir))
        winreg.SetValueEx(
            key,
            "UninstallString",
            0,
            winreg.REG_SZ,
            f'powershell.exe -ExecutionPolicy Bypass -File "{uninstaller}"',
        )
        winreg.CloseKey(key)
    except Exception:
        pass


def do_install(log) -> Path:
    log("Поиск пакета…")
    zpath = find_payload_zip()
    log(f"Пакет: {zpath.name}")

    root = install_root()
    app_dir = root / "App"
    if app_dir.exists():
        log("Удаляю предыдущую версию…")
        shutil.rmtree(app_dir, ignore_errors=True)
    app_dir.mkdir(parents=True, exist_ok=True)
    (root / "data").mkdir(exist_ok=True)
    (root / "logs").mkdir(exist_ok=True)

    log("Распаковка файлов…")
    with zipfile.ZipFile(zpath, "r") as zf:
        zf.extractall(app_dir)

    exe = app_dir / "CRMAIDesk.exe"
    if not exe.exists():
        # maybe nested folder
        for p in app_dir.rglob("CRMAIDesk.exe"):
            exe = p
            app_dir = p.parent
            break
    if not exe.exists():
        raise FileNotFoundError("CRMAIDesk.exe не найден после распаковки")

    log("Ярлыки…")
    desktop_dirs = [
        Path.home() / "Desktop",
        Path.home() / "OneDrive" / "Desktop",
        Path(os.environ.get("USERPROFILE", "")) / "Desktop",
    ]
    programs = (
        Path(os.environ.get("APPDATA", ""))
        / "Microsoft"
        / "Windows"
        / "Start Menu"
        / "Programs"
    )
    for d in desktop_dirs + [programs]:
        try:
            d.mkdir(parents=True, exist_ok=True)
            create_shortcut(exe, d / f"{APP_NAME}.lnk", app_dir)
        except Exception:
            pass

    un = write_uninstaller(app_dir)
    register_uninstall(app_dir, un)
    log("Готово.")
    return exe


class InstallerApp:
    def __init__(self) -> None:
        self.root = tk.Tk()
        self.root.title(f"{APP_NAME} — Установка")
        self.root.geometry("480x340")
        self.root.resizable(False, False)
        try:
            self.root.configure(bg="#0b1220")
        except Exception:
            pass

        frm = ttk.Frame(self.root, padding=20)
        frm.pack(fill="both", expand=True)

        title = tk.Label(
            frm,
            text=APP_NAME,
            font=("Segoe UI", 18, "bold"),
            fg="#e8eefc",
            bg="#0b1220",
        )
        title.pack(anchor="w")
        sub = tk.Label(
            frm,
            text="Помощник для amoCRM и Bitrix24 · RU/UZ\nНажмите «Установить» — всё настроится само.",
            font=("Segoe UI", 10),
            fg="#8b9bb8",
            bg="#0b1220",
            justify="left",
        )
        sub.pack(anchor="w", pady=(8, 16))

        self.progress = ttk.Progressbar(frm, mode="indeterminate", length=420)
        self.progress.pack(pady=8)

        self.log = tk.Text(
            frm,
            height=8,
            width=54,
            font=("Consolas", 9),
            bg="#111a2e",
            fg="#cbd5e1",
            relief="flat",
        )
        self.log.pack(fill="both", expand=True, pady=8)

        self.btn = tk.Button(
            frm,
            text="Установить",
            font=("Segoe UI", 12, "bold"),
            bg="#2563eb",
            fg="white",
            activebackground="#1d4ed8",
            activeforeground="white",
            relief="flat",
            padx=20,
            pady=10,
            cursor="hand2",
            command=self.start,
        )
        self.btn.pack(fill="x", pady=(4, 0))

        self.exe_path: Path | None = None

    def append(self, msg: str) -> None:
        self.log.insert("end", msg + "\n")
        self.log.see("end")
        self.root.update_idletasks()

    def start(self) -> None:
        self.btn.config(state="disabled", text="Установка…")
        self.progress.start(12)
        threading.Thread(target=self._worker, daemon=True).start()

    def _worker(self) -> None:
        try:
            exe = do_install(lambda m: self.root.after(0, self.append, m))
            self.exe_path = exe
            self.root.after(0, self._done_ok)
        except Exception as e:
            self.root.after(0, self._done_err, str(e))

    def _done_ok(self) -> None:
        self.progress.stop()
        self.btn.config(state="normal", text="Запустить приложение", command=self.launch)
        self.append("Установка завершена успешно.")
        messagebox.showinfo(APP_NAME, "Установка завершена.\nНажмите «Запустить приложение».")
        # auto launch
        self.launch()

    def _done_err(self, err: str) -> None:
        self.progress.stop()
        self.btn.config(state="normal", text="Установить", command=self.start)
        self.append("ОШИБКА: " + err)
        messagebox.showerror(APP_NAME, "Ошибка установки:\n" + err)

    def launch(self) -> None:
        if self.exe_path and self.exe_path.exists():
            subprocess.Popen([str(self.exe_path)], cwd=str(self.exe_path.parent))
        self.root.destroy()

    def run(self) -> None:
        self.root.mainloop()


def main() -> None:
    # if CLI silent
    if "--silent" in sys.argv:
        exe = do_install(print)
        subprocess.Popen([str(exe)], cwd=str(exe.parent))
        return
    InstallerApp().run()


if __name__ == "__main__":
    main()
