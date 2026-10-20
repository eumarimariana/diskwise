""""About this folder" summary: explains oddly named folders from the path,
the name pattern and the contents."""
import os
import re
import time
from collections import defaultdict

from .config import DAY, HOME

# folder name (lowercase) -> (program/topic, what it usually holds)
KNOWN = {
    ".cache": ("General cache", "caches from many programs; everything here gets recreated automatically"),
    ".local": ("Program data", "data and programs installed just for your user"),
    "share": ("Program data", "data that programs keep (history, databases, games…)"),
    ".config": ("Settings", "program preferences and settings"),
    "trash": ("Trash", "files you already sent to the Trash"),
    ".trash": ("Trash", "files you already sent to the Trash"),
    "$recycle.bin": ("Windows Recycle Bin", "files you already sent to the Recycle Bin"),
    "library": ("macOS Library", "data, preferences and caches of Mac apps"),
    "caches": ("Caches", "app caches; everything here gets recreated automatically"),
    "deriveddata": ("Xcode", "Xcode builds and indexes; recreated automatically"),
    "appdata": ("Windows app data", "program settings, caches and data"),
    "temp": ("Temporary files", "temporary program files; safe to clean"),
    "thumbnails": ("Thumbnails", "image previews made by the file manager"),
    ".mozilla": ("Firefox", "Firefox profile: bookmarks, passwords, history, extensions"),
    "cache2": ("Firefox cache", "site pages and images kept to load faster"),
    "google-chrome": ("Google Chrome", "Chrome profile: bookmarks, passwords, history, extensions"),
    "chromium": ("Chromium", "Chromium browser profile"),
    "brave-browser": ("Brave", "Brave browser profile"),
    "bravesoftware": ("Brave", "Brave browser profile"),
    "microsoft-edge": ("Microsoft Edge", "Edge browser profile"),
    "opera": ("Opera", "Opera browser profile"),
    "code": ("VS Code", "VS Code editor data (cache, state, extensions)"),
    ".vscode": ("VS Code", "VS Code extensions"),
    ".vscode-server": ("VS Code (remote)", "VS Code server used for remote connections"),
    "cursor": ("Cursor", "Cursor editor data"),
    "jetbrains": ("JetBrains", "JetBrains IDE data (IntelliJ, PyCharm…)"),
    "steam": ("Steam", "Steam games and data"),
    ".steam": ("Steam", "Steam games and data"),
    "steamapps": ("Steam games", "installed games; deleting uninstalls the game"),
    "shadercache": ("Shader cache", "precompiled game graphics; recreated automatically"),
    "compatdata": ("Proton (Steam)", "a 'fake Windows' for each game, with saves for some games"),
    ".wine": ("Wine", "a 'fake Windows' for running Windows programs"),
    "lutris": ("Lutris", "Lutris games and settings"),
    "heroic": ("Heroic", "Epic/GOG games through Heroic"),
    "snap": ("Snap", "programs installed with Snap and their data"),
    ".var": ("Flatpak", "data of programs installed with Flatpak"),
    "flatpak": ("Flatpak", "installed Flatpak programs"),
    "discord": ("Discord", "Discord cache and data"),
    "slack": ("Slack", "Slack cache and data"),
    "spotify": ("Spotify", "downloaded songs/Spotify cache"),
    "telegramdesktop": ("Telegram", "Telegram data"),
    "telegram desktop": ("Telegram", "files downloaded by Telegram"),
    "zoom": ("Zoom", "Zoom data and recordings"),
    "obsidian": ("Obsidian", "Obsidian data"),
    "libreoffice": ("LibreOffice", "LibreOffice settings and backups"),
    "evolution": ("Evolution", "Evolution email, contacts and calendar"),
    "tracker3": ("GNOME indexer", "file search index; recreated automatically"),
    "gnome-shell": ("GNOME", "GNOME desktop extensions and data"),
    "keyrings": ("Keyring", "saved system passwords; don't delete"),
    "fontconfig": ("Fonts", "font cache; recreated automatically"),
    "fonts": ("Fonts", "fonts you installed"),
    "icons": ("Icons", "icon themes"),
    "applications": ("App shortcuts", "shortcuts (.desktop) that show up in the menu"),
    "node_modules": ("Node.js dependencies", "libraries downloaded by npm; `npm install` downloads them again"),
    ".npm": ("npm", "npm package cache; recreated automatically"),
    ".nvm": ("nvm", "installed Node.js versions"),
    ".yarn": ("Yarn", "Yarn package cache"),
    "pnpm": ("pnpm", "pnpm package store"),
    "pip": ("pip", "Python package cache; recreated automatically"),
    "__pycache__": ("Compiled Python", "Python cache; recreated automatically"),
    "site-packages": ("Python libraries", "installed Python libraries"),
    ".venv": ("Python environment", "Python virtual environment; can be recreated with pip install"),
    "venv": ("Python environment", "Python virtual environment; can be recreated with pip install"),
    ".conda": ("Conda", "Conda environments and packages"),
    "anaconda3": ("Anaconda", "Anaconda Python distribution"),
    "miniconda3": ("Miniconda", "Miniconda Python distribution"),
    ".cargo": ("Rust", "Rust packages and tools"),
    ".rustup": ("Rust", "Rust compiler versions"),
    "target": ("Build", "compiled files; made again when you build"),
    "go": ("Go", "Go language packages"),
    ".gradle": ("Gradle", "Java/Android build cache"),
    ".m2": ("Maven", "downloaded Java libraries"),
    ".android": ("Android", "Android SDK/emulators"),
    "android": ("Android", "Android SDK"),
    ".docker": ("Docker", "Docker settings"),
    ".git": ("Git", "project history; deleting it loses the history"),
    "objects": ("Objects", "chunks of data stored under hash names"),
    ".ssh": ("SSH", "keys for accessing servers; don't delete"),
    ".gnupg": ("GPG", "encryption keys; don't delete"),
    "indexeddb": ("Site database", "data that sites/apps keep in the browser"),
    "local storage": ("Site data", "data saved by sites"),
    "service worker": ("Site cache", "site cache for working offline"),
    "code cache": ("Code cache", "precompiled JavaScript; recreated automatically"),
    "gpucache": ("GPU cache", "graphics cache; recreated automatically"),
    "blob_storage": ("Site data", "temporary site files"),
    "crashpad": ("Crash reports", "crash records; safe to delete"),
    "crash reports": ("Crash reports", "crash records; safe to delete"),
    "logs": ("Logs", "activity records; safe to delete"),
    "downloads": ("Downloads", "what you downloaded from the internet"),
    "dist": ("Build", "generated version of a project; can be recreated"),
    "build": ("Build", "files generated when building; can be recreated"),
}
EXT_GROUPS = {
    "images": {".jpg", ".jpeg", ".png", ".gif", ".webp", ".heic", ".bmp", ".svg", ".tiff", ".raw", ".cr2", ".ico"},
    "videos": {".mp4", ".mkv", ".avi", ".mov", ".webm", ".wmv", ".flv", ".m4v"},
    "audio": {".mp3", ".flac", ".wav", ".ogg", ".m4a", ".aac", ".opus"},
    "documents": {".pdf", ".doc", ".docx", ".odt", ".xls", ".xlsx", ".ods", ".ppt", ".pptx", ".odp", ".txt", ".md", ".epub", ".rtf", ".csv"},
    "code": {".py", ".js", ".ts", ".tsx", ".jsx", ".java", ".c", ".h", ".cpp", ".rs", ".go", ".rb", ".php", ".html", ".css", ".sh", ".lua", ".kt", ".cs", ".vue"},
    "archives": {".zip", ".tar", ".gz", ".tgz", ".7z", ".rar", ".xz", ".bz2", ".zst"},
    "programs/libraries": {".so", ".dll", ".exe", ".bin", ".appimage", ".deb", ".rpm", ".jar", ".node", ".wasm", ".pak", ".dat"},
    "program data": {".json", ".db", ".sqlite", ".sqlite3", ".ldb", ".log", ".xml", ".yaml", ".yml", ".ini", ".conf", ".toml", ".cache", ".lock", ".pb"},
}
MARKERS = {
    "package.json": "a JavaScript/Node.js project", "requirements.txt": "a Python project",
    "pyproject.toml": "a Python project", "setup.py": "a Python project", "cargo.toml": "a Rust project",
    "go.mod": "a Go project", "pom.xml": "a Java (Maven) project", "build.gradle": "a Java/Android project",
    "makefile": "a code project (Makefile)", "cmakelists.txt": "a C/C++ project",
    "dockerfile": "a project with Docker", "index.html": "a website / web page",
    "manifest.json": "a browser extension or web app", "prefs.js": "a Firefox profile",
    "places.sqlite": "a Firefox profile (history and bookmarks)",
    "preferences": "a Chromium browser profile", "history": "browser history",
    "steam_appid.txt": "a Steam game", "user.reg": "a Wine 'fake Windows'",
}
HEX_RE = re.compile(r"^[0-9a-f]{12,}$|^[0-9a-f]{2}$|^[0-9a-f]{8}-[0-9a-f]{4}-", re.I)
DOMAIN_RE = re.compile(r"^(com|org|io|net|dev|app|me|de|br)\.[\w-]+\.[\w.-]+$", re.I)


def plural(n, word, many=None):
    return f"{n} {word if n == 1 else many or word + 's'}"


def ago(ts):
    d = (time.time() - ts) / DAY
    if d < 1: return "today"
    if d < 60: return plural(int(d), "day") + " ago"
    if d < 730: return plural(int(d / 30), "month") + " ago"
    return plural(int(d / 365), "year") + " ago"


def known_context(path):
    """Recognized parts of the path, from outermost to innermost.
    E.g. .vscode/extensions/ms-python.pylance/.cache -> VS Code › extension 'pylance' › Cache."""
    base = os.path.relpath(path, HOME) if path.startswith(HOME + os.sep) else path
    parts = base.split(os.sep)
    chain = []
    for i, part in enumerate(parts):
        k = KNOWN.get(part.lower())
        parent = parts[i - 1].lower() if i else ""
        if k:
            chain.append((part, *k))
        elif DOMAIN_RE.match(part):
            app = part.split(".")[-1]
            chain.append((part, app, f"folder of the '{app}' app (Flatpak/Snap)"))
        elif parent == "extensions" and "." in part:
            ext = re.sub(r"-\d[\w.]*$", "", part.split(".", 1)[1])
            chain.append((part, f"extension {ext}", f"'{ext}' extension installed in the editor/browser"))
        elif parent == "node_modules" and not part.startswith("."):
            chain.append((part, f"package {part}", f"'{part}' library downloaded by npm"))
        elif parent == "common" and i > 1 and parts[i - 2].lower() == "steamapps":
            chain.append((part, f"game {part}", f"files of the game '{part}'; deleting them breaks the game, "
                                                  "uninstall it in Steam instead"))
    # no repeated labels (e.g. Steam › … › Steam)
    seen, out = set(), []
    for c in chain:
        if c[1] not in seen:
            seen.add(c[1])
            out.append(c)
    return out


def describe_folder(path, files):
    """Builds a plain-English summary of what the folder seems to be."""
    name = os.path.basename(path) or path
    lines = []
    chain = known_context(path)
    if chain:
        part, label, desc = chain[-1]
        if part == name:
            lines.append(f"**{label}**: {desc}.")
        else:
            lines.append(f"It's inside **{part}** ({label}): {desc}.")
        if len(chain) > 1:
            lines.append("Path: " + " › ".join(c[1] for c in chain) + ".")

    if HEX_RE.match(name):
        lines.append("The name is a random code (hash/ID): folders like this are created automatically "
                     "by programs, usually for cache or internal storage, not by you.")
    elif DOMAIN_RE.match(name):
        lines.append(f"Name in 'company.program' format: it's the folder of the **{name.split('.')[-1]}** app.")
    elif ".default" in name:
        lines.append("Looks like a browser profile (Firefox/Thunderbird).")

    try:
        subdirs = [e.name for e in os.scandir(path) if e.is_dir(follow_symlinks=False)]
    except OSError:
        subdirs = []
    entries = {n.lower() for n, _, _ in files} | {d.lower() for d in subdirs}
    marks = sorted({v for k, v in MARKERS.items() if k in entries})
    if ".git" in entries:
        marks.append("a Git repository")
    if marks:
        lines.append("Clues: looks like " + ", ".join(marks) + ".")

    # README: the first useful line says what the project is
    readme = next((n for n, _, _ in files if n.lower().startswith("readme")), None)
    if readme:
        try:
            with open(os.path.join(path, readme), errors="ignore") as f:
                first = next((l.strip("# \n") for l in f.read(4000).splitlines() if l.strip("# \n")), "")
            if first:
                lines.append(f"The README says: “{first[:140]}”.")
        except OSError:
            pass

    total = sum(f[1] for f in files)
    groups = defaultdict(int)
    noext = 0
    for n, s, _ in files:
        ext = os.path.splitext(n)[1].lower()
        g = next((g for g, exts in EXT_GROUPS.items() if ext in exts), None)
        if not ext:
            noext += 1
        groups[g or ("no extension" if not ext else "other")] += s
    comp = [(g, s / total * 100) for g, s in sorted(groups.items(), key=lambda x: -x[1]) if total and s / total >= 0.05]
    if files:
        lines.append(f"Has {plural(len(files), 'direct file')} ({', '.join(f'{p:.0f}% {g}' for g, p in comp[:3])})"
                     + (f" and {plural(len(subdirs), 'subfolder')}." if subdirs else "."))
        if noext / len(files) > 0.7 and len(files) > 5:
            lines.append("Almost all files have no extension and random names, a typical cache pattern.")
        mt = [f[2] for f in files]
        lines.append(f"Last changed {ago(max(mt))}; the oldest file is from {ago(min(mt))}.")
    elif subdirs:
        lines.append(f"Has no files directly inside, only {plural(len(subdirs), 'subfolder')}.")

    if not lines:
        lines.append("I found no clues about this folder.")
    return {"label": chain[-1][1] if chain else None, "lines": lines,
            "subdirs": sorted(subdirs)[:12], "samples": [n for n, _, _ in files[:6]]}
