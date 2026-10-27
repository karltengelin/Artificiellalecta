"""Operatören sätter själv sin lösenfras; inga hemligheter till terminalutmatningen."""

import argparse
import getpass
import secrets
import sys
from pathlib import Path

from argon2 import PasswordHasher
from dotenv import set_key

from web.config import REPO_ROOT, WebSettings
from web.operator_auth import MAX_PASSWORD_LENGTH


def configure_operator(path: Path, operator_id: str, password: str) -> None:
    if path.name != ".env":
        raise ValueError("Lösenordshashen får bara skrivas till en lokal .env-fil")
    WebSettings(operator_id=operator_id)
    if not 12 <= len(password) <= MAX_PASSWORD_LENGTH:
        raise ValueError(f"Välj en lösenfras på 12–{MAX_PASSWORD_LENGTH} tecken")
    encoded = PasswordHasher().hash(password)
    set_key(path, "OPERATOR_ID", operator_id)
    set_key(path, "OPERATOR_PASSWORD_HASH", encoded)


def main() -> None:
    parser = argparse.ArgumentParser(description="Sätt operatörens Argon2id-lösenfras i lokal .env, utan att skriva ut den")
    parser.add_argument("--operator", default="karl", help="Namngiven operatör (standard karl)")
    parser.add_argument("--env-file", type=Path, default=REPO_ROOT / ".env", help="Lokal .env (standard reporoten)")
    args = parser.parse_args()
    if not sys.stdin.isatty():
        parser.error("Kör skriptet i en interaktiv terminal så att lösenfrasen kan matas in dolt")
    try:
        password = getpass.getpass("Ny lösenfras: ")
        confirmation = getpass.getpass("Upprepa lösenfrasen: ")
        if not secrets.compare_digest(password.encode(), confirmation.encode()):
            raise ValueError("Lösenfraserna stämmer inte överens")
        configure_operator(args.env_file, args.operator, password)
    except (ValueError, OSError) as exc:
        parser.error(str(exc) if isinstance(exc, ValueError) else "Kunde inte skriva den lokala .env-filen")
    print("Operatörsinloggningen är konfigurerad. Starta om webbservern för att använda den.")


if __name__ == "__main__":
    main()
