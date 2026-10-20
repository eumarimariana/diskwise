"""Global app settings."""
import os
import secrets
from pathlib import Path

HOST = "127.0.0.1"
PORT = int(os.environ.get("CLEANER_PORT", 8765))
TOKEN = secrets.token_urlsafe(16)  # stops other websites from calling the API
STATIC = Path(__file__).resolve().parent / "static"

HOME = os.path.realpath(str(Path.home()))
DAY = 86400
