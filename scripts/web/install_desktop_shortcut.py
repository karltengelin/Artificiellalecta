"""Lägger en genväg till handläggar-UI:t på skrivbordet (Windows), med Artificiellalectas märke som ikon.

Genvägen kör scripts/web/open_ui.ps1 i den här checkouten: startar UI-servern
om den inte redan kör och öppnar sidan i webbläsaren. Ikonen (den indigofärgade
rutan, src/design/icon.py) skrivs till %LOCALAPPDATA%\\Artificiellalecta\\.
Kör igen för att uppdatera genvägen, t.ex. efter flytt av repot. Ingen databas,
inga modellanrop och inga ändringar i repot.

Användning (från huvudcheckouten, i .venv):
    python scripts/web/install_desktop_shortcut.py                 # demodatabasen
    python scripts/web/install_desktop_shortcut.py --db lakebase   # egen genväg mot Lakebase-beståndet
    python scripts/web/install_desktop_shortcut.py --dry-run       # visa vad som skulle skapas
"""

from __future__ import annotations

import argparse
import base64
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

from design.icon import brand_mark_ico  # noqa: E402

POWERSHELL = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe"
NAMES = {"demo": "Artificiellalecta – handläggare", "svc_test": "Artificiellalecta – handläggare (svc_test)",
         "lakebase": "Artificiellalecta – handläggare (Lakebase)"}


def _ps(script: str, capture: bool = False) -> str:
    encoded = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
    result = subprocess.run([str(POWERSHELL), "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded],
                            check=True, capture_output=True, text=True)
    return result.stdout.strip() if capture else ""


def _quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--db", choices=list(NAMES), default="demo", help="Databas för UI:t (standard demo)")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--dry-run", action="store_true", help="Visa bara vad som skulle skapas")
    args = parser.parse_args()
    if os.name != "nt":
        parser.error("skrivbordsgenvägen finns bara för Windows")

    launcher = REPO_ROOT / "scripts" / "web" / "open_ui.ps1"
    icon = Path(os.environ["LOCALAPPDATA"]) / "Artificiellalecta" / "artificiellalecta.ico"
    desktop = Path(_ps("[Environment]::GetFolderPath('Desktop')", capture=True))
    link = desktop / f"{NAMES[args.db]}.lnk"
    arguments = (f'-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "{launcher}" '
                 f"-Db {args.db} -Port {args.port}")

    print(f"Genväg:  {link}\nKör:     {POWERSHELL} {arguments}\nIkon:    {icon}")
    if args.dry_run:
        return

    icon.parent.mkdir(parents=True, exist_ok=True)
    icon.write_bytes(brand_mark_ico())
    _ps("\n".join([
        "$shell = New-Object -ComObject WScript.Shell",
        f"$link = $shell.CreateShortcut({_quote(str(link))})",
        f"$link.TargetPath = {_quote(str(POWERSHELL))}",
        f"$link.Arguments = {_quote(arguments)}",
        f"$link.WorkingDirectory = {_quote(str(REPO_ROOT))}",
        f"$link.IconLocation = {_quote(str(icon) + ',0')}",
        f"$link.Description = {_quote('Startar och öppnar handläggar-UI:t (' + args.db + ')')}",
        "$link.WindowStyle = 7",
        "$link.Save()",
    ]))
    print("Klart – dubbelklicka på genvägen på skrivbordet.")


if __name__ == "__main__":
    main()
