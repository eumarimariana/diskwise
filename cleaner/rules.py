"""Risk rating: says whether a file or folder looks safe or dangerous to delete.

These are heuristics. They help you decide; they don't guarantee anything.
"""
import os
import sys
import time

from .config import DAY, HOME

SAFE_DIRS = {".cache", "cache", "Cache", "caches", "__pycache__", "node_modules", ".npm",
             ".pytest_cache", ".mypy_cache", "thumbnails", "Trash", "tmp", ".tmp", "temp",
             "CachedData", "GPUCache", "Code Cache", "Service Worker", "logs", ".gradle",
             "build", "dist", ".next", ".venv", "venv", "target", "shadercache",
             # macOS and Windows
             "Caches", ".Trash", "DerivedData", "Temp", "INetCache", "CrashDumps", "$Recycle.Bin"}
SAFE_EXT = {".log": "log file", ".tmp": "temporary file", ".pyc": "compiled Python",
            ".o": "compiled object", ".part": "unfinished download",
            ".crdownload": "unfinished download", ".bak": "old backup", ".old": "old copy"}
INSTALLER_EXT = {".deb", ".rpm", ".iso", ".exe", ".msi", ".dmg", ".appimage", ".run", ".pkg"}
DANGER_DIRS = {".ssh": "SSH keys (access to servers)", ".gnupg": "encryption keys",
               ".password-store": "passwords", "keyrings": "system password keyring",
               ".git": "Git history; deleting it breaks the repository", ".pki": "certificates",
               ".mozilla": "Firefox profile (passwords, bookmarks)",
               ".thunderbird": "your email", ".config": "program settings",
               "snap": "programs installed with Snap", ".local": "program data"}
DANGER_EXT = {".kdbx": "password database", ".pem": "key/certificate", ".key": "private key",
              ".gpg": "encrypted file", ".wallet": "wallet", ".p12": "certificate"}
DANGER_NAMES = {"id_rsa", "id_ed25519", "id_ecdsa", "authorized_keys", "known_hosts",
                "wallet.dat", ".env"}
if sys.platform == "win32":
    _windir = os.environ.get("SystemRoot", r"C:\Windows")
    SYSTEM_ROOTS = tuple({_windir, os.environ.get("ProgramFiles", r"C:\Program Files"),
                          os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"),
                          os.environ.get("ProgramData", r"C:\ProgramData")})
elif sys.platform == "darwin":
    SYSTEM_ROOTS = ("/System", "/Library", "/Applications", "/private", "/usr", "/bin", "/sbin",
                    "/opt", "/cores")
else:
    SYSTEM_ROOTS = ("/etc", "/usr", "/bin", "/sbin", "/lib", "/boot", "/var/lib", "/opt", "/root")
# home folders that hold program data and settings (macOS and Windows)
HOME_DANGER = {"Library": "app data and settings (macOS)",
               "AppData": "program data and settings (Windows)"}
# personal folder names in English and Portuguese (folder names depend on the system language)
PERSONAL = {"Documentos", "Documents", "Imagens", "Pictures", "Vídeos", "Videos",
            "Música", "Music", "Área de Trabalho", "Desktop"}
ARCHIVE_EXT = {".zip", ".tar", ".gz", ".tgz", ".7z", ".rar", ".xz", ".bz2"}


def classify(path, size=None, mtime=None, is_file=False, root=None):
    """Returns (level, reasons). level: 'safe' | 'caution' | 'danger' | 'neutral'."""
    rel_home = os.path.relpath(path, HOME) if path.startswith(HOME + os.sep) else None
    # the rules look at the path from the home folder (or the scanned folder), so that
    # a "/tmp" above the root doesn't mark everything as temporary
    base = rel_home or (os.path.relpath(path, root) if root and path.startswith(root) else path)
    parts = base.split(os.sep)
    dirs = parts[:-1] if is_file else parts
    name = parts[-1]
    ext = os.path.splitext(name)[1].lower()
    danger, safe, caution = [], [], []

    if rel_home is None and path.startswith(SYSTEM_ROOTS):
        danger.append("system file; deleting it can break your system")
    if is_file and rel_home and len(parts) == 1 and name.startswith("."):
        danger.append("your user settings (dotfile)")
    if is_file and (name in DANGER_NAMES or name.startswith("id_")):
        danger.append("credential / access key")
    if is_file and ext in DANGER_EXT:
        danger.append(DANGER_EXT[ext])

    hit_safe = next((d for d in dirs if d in SAFE_DIRS), None)
    if hit_safe:
        safe.append(f"inside '{hit_safe}': cache/temporary, it gets recreated automatically")
    for d in dirs:
        if d in DANGER_DIRS and not hit_safe and "steamapps" not in dirs:
            danger.append(DANGER_DIRS[d])
            break
    else:
        if rel_home and dirs and parts[0] in HOME_DANGER and not hit_safe and "steamapps" not in dirs:
            danger.append(HOME_DANGER[parts[0]])

    if is_file:
        if ext in SAFE_EXT:
            safe.append(SAFE_EXT[ext])
        if ext in INSTALLER_EXT or name.lower().endswith(".appimage"):
            safe.append("installer; usually not needed after installing")
        if name.endswith("~"):
            safe.append("editor auto-backup")
        if ext in ARCHIVE_EXT:
            caution.append("archive; it could be a backup")
        if mtime and time.time() - mtime < 30 * DAY:
            caution.append("changed in the last 30 days")
        if size and size > 1 << 30:
            caution.append("very large file (> 1 GB)")
    if not hit_safe and "steamapps" in dirs:
        caution.append("installed game file; to remove it, uninstall the game in Steam")
    if rel_home and parts[0] in PERSONAL:
        caution.append(f"personal folder '{parts[0]}': photos, documents…")
    if rel_home and parts[0] == "Downloads" and not safe:
        caution.append("Downloads: check whether you still need it")

    notes = []
    if is_file and mtime and time.time() - mtime > 2 * 365 * DAY:
        notes.append("not changed in over 2 years")

    if danger:
        return "danger", danger + notes
    if safe:
        return "safe", safe + caution + notes
    if caution:
        return "caution", caution + notes
    return "neutral", notes or ["no clues; review it yourself"]
