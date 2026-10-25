"""Lägger en genväg till handläggar-UI:t på skrivbordet (Windows), med Artificiellalectas märke som ikon.

Genvägen kör scripts/web/open_ui.ps1 i den här checkouten: startar UI-servern
om den inte redan kör och öppnar sidan i webbläsaren. Ikonen (den indigofärgade
rutan, src/design/icon.py) skrivs till %LOCALAPPDATA%\\Artificiellalecta\\.
Kör igen för att uppdatera genvägen, t.ex. efter flytt av repot. Ingen databas,
inga modellanrop och inga ändringar i repot.

Användning (från huvudcheckouten, i .venv):
    python scripts/web/install_desktop_shortcut.py                 # vanlig genväg (Lakebase) och separat DEMO
    python scripts/web/install_desktop_shortcut.py --db demo       # bara DEMO-genvägen
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
from web.config import DEFAULT_PORTS  # noqa: E402

POWERSHELL = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe"
NAMES = {"demo": "Artificiellalecta – handläggare (DEMO)", "svc_test": "Artificiellalecta – handläggare (TEST)",
         "lakebase": "Artificiellalecta – handläggare"}


def _ps(script: str, capture: bool = False) -> str:
    encoded = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
    result = subprocess.run([str(POWERSHELL), "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded],
                            check=True, capture_output=True, text=True)
    return result.stdout.strip() if capture else ""


def _quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--db", choices=list(NAMES), help="Skapa bara den valda genvägen (standard: Lakebase och DEMO)")
    parser.add_argument("--port", type=int, help="Egen port; kräver --db (Lakebase 8765, test 8766, demo 8767)")
    parser.add_argument("--dry-run", action="store_true", help="Visa bara vad som skulle skapas")
    args = parser.parse_args()
    if os.name != "nt":
        parser.error("skrivbordsgenvägen finns bara för Windows")
    if args.port is not None and (args.db is None or not 1 <= args.port <= 65535):
        parser.error("--port kräver --db och ett portnummer mellan 1 och 65535")
    for database in [args.db] if args.db else ["lakebase", "demo"]:
        install_shortcut(database, args.port if args.port is not None else DEFAULT_PORTS[database], args.dry_run)


def install_shortcut(database: str, port: int, dry_run: bool) -> None:
    launcher = REPO_ROOT / "scripts" / "web" / "open_ui.ps1"
    icon = Path(os.environ["LOCALAPPDATA"]) / "Artificiellalecta" / "artificiellalecta.ico"
    desktop = Path(_ps("[Environment]::GetFolderPath('Desktop')", capture=True))
    link = desktop / f"{NAMES[database]}.lnk"
    arguments = (f'-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "{launcher}" '
                 f"-Db {database} -Port {port}")

    print(f"Genväg:  {link}\nKör:     {POWERSHELL} {arguments}\nIkon:    {icon}")
    if dry_run:
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
        f"$link.Description = {_quote('Startar och öppnar handläggar-UI:t (' + database + ')')}",
        "$link.WindowStyle = 7",
        "$link.Save()",
    ]))
    print("Klart – dubbelklicka på genvägen på skrivbordet.")


if __name__ == "__main__":
    main()
