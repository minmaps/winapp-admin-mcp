"""User-scoped Windows DPAPI credentials; never log the cleartext token."""
from pathlib import Path
import secrets
import win32crypt

ROOT = Path(__file__).resolve().parent
TOKEN_FILE = ROOT / "state" / "token.dpapi"


def load_token() -> str:
    return win32crypt.CryptUnprotectData(
        TOKEN_FILE.read_bytes(), None, None, None, 1
    )[1].decode("ascii")


def create_token() -> None:
    TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
    if TOKEN_FILE.exists():
        load_token()  # Fail rather than silently replace another user's credential.
        return
    encrypted = win32crypt.CryptProtectData(
        secrets.token_urlsafe(48).encode("ascii"), "WinApp admin MCP", None, None, None, 1
    )
    with TOKEN_FILE.open("xb") as out:
        out.write(encrypted)
