"""Provisionera lokala webbkonton med dold inmatning."""

import argparse
import getpass
import secrets
import sys
from pathlib import Path
from tempfile import NamedTemporaryFile

from argon2 import PasswordHasher
from dotenv import dotenv_values, set_key

from web.config import REPO_ROOT, WebSettings
from web.operator_auth import MAX_PASSWORD_LENGTH


def configure_operator(path: Path, operator_id: str, password: str) -> None:
    _configure(path, "OPERATOR_ID", "OPERATOR_PASSWORD_HASH", operator_id, password)


def configure_handler(path: Path, handler_id: str, password: str) -> None:
    _configure(path, "HANDLAGGARE_LOGIN_ID", "HANDLAGGARE_PASSWORD_HASH", handler_id, password)


def _configure(path: Path, id_key: str, hash_key: str, user_id: str, password: str) -> None:
    if path.name != ".env":
        raise ValueError("Lösenordshashen får bara skrivas till en lokal .env-fil")
    if not user_id:
        raise ValueError("Användarnamnet måste anges")
    if not 12 <= len(password) <= MAX_PASSWORD_LENGTH:
        raise ValueError(f"Välj en lösenfras på 12–{MAX_PASSWORD_LENGTH} tecken")
    encoded = PasswordHasher().hash(password)
    values = dotenv_values(path, interpolate=False)
    values.update({id_key: user_id, hash_key: encoded})
    WebSettings(
        operator_id=values.get("OPERATOR_ID") or "karl",
        operator_password_hash=values.get("OPERATOR_PASSWORD_HASH") or None,
        handler_login_id=values.get("HANDLAGGARE_LOGIN_ID") or "handlaggare",
        handler_password_hash=values.get("HANDLAGGARE_PASSWORD_HASH") or None,
    )
    with NamedTemporaryFile(dir=path.parent, prefix=".env.", delete=False) as handle:
        staged = Path(handle.name)
    try:
        if path.exists():
            staged.write_bytes(path.read_bytes())
        set_key(staged, id_key, user_id)
        set_key(staged, hash_key, encoded)
        staged.replace(path)
    finally:
        staged.unlink(missing_ok=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Sätt ett lokalt webbkontos lösenfras med dold inmatning")
    role = parser.add_mutually_exclusive_group()
    role.add_argument("--operator", default="karl", help="Namngiven operatör (standard karl)")
    role.add_argument("--handlaggare", metavar="NAMN", help="Sätt lösenfrasen för ett separat handläggarkonto")
    parser.add_argument("--env-file", type=Path, default=REPO_ROOT / ".env", help="Lokal .env (standard reporoten)")
    args = parser.parse_args()
    if not sys.stdin.isatty():
        parser.error("Kör skriptet i en interaktiv terminal så att lösenfrasen kan matas in dolt")
    try:
        password = getpass.getpass("Ny lösenfras: ")
        confirmation = getpass.getpass("Upprepa lösenfrasen: ")
        if not secrets.compare_digest(password.encode(), confirmation.encode()):
            raise ValueError("Lösenfraserna stämmer inte överens")
        if args.handlaggare is not None:
            configure_handler(args.env_file, args.handlaggare, password)
        else:
            configure_operator(args.env_file, args.operator, password)
    except (ValueError, OSError) as exc:
        parser.error(str(exc) if isinstance(exc, ValueError) else "Kunde inte skriva den lokala .env-filen")
    print("Inloggningen är konfigurerad. Starta om webbservern för att använda den.")


if __name__ == "__main__":
    main()
