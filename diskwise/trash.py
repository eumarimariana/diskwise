"""System Trash: send files/folders to the Trash and restore them later.

Works on Linux (the freedesktop standard, same as GNOME/KDE/XFCE), macOS (Finder)
and Windows (Explorer Recycle Bin). Nothing here deletes anything for good.

Each item sent to the Trash becomes a pair (original_path, hint). The hint says where
the item ended up inside the Trash, when that is known right away; when it is not
(e.g. `gio` doesn't report it), it is None and the item is looked up when restoring.
"""
import ctypes
import os
import shutil
import struct
import subprocess
import sys
import time
from urllib.parse import quote, unquote


class TrashError(Exception):
    pass


def _gone(path):
    return not os.path.lexists(path)


def _move_back(src, dest):
    """Moves `src` (inside the Trash) back to `dest`, without overwriting anything."""
    if os.path.lexists(dest):
        raise TrashError(f"something already exists at {dest}")
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    try:
        os.rename(src, dest)
    except OSError:
        shutil.move(src, dest)  # another disk: copy and remove


# --------------------------------------------------------------------------- Linux
class FreedesktopTrash:
    """Linux Trash: ~/.local/share/Trash, or <disk>/.Trash-<uid> on other disks.

    Uses `gio` to trash things when it exists, since it already handles every special
    case. Without `gio`, follows the specification itself.
    """

    def __init__(self, use_gio=None, home_trash=None):
        self.use_gio = shutil.which("gio") is not None if use_gio is None else use_gio
        data_home = os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share")
        self.home_trash = home_trash or os.path.join(data_home, "Trash")

    # ---- send to the Trash
    def trash(self, paths):
        if self.use_gio:
            return self._trash_gio(paths)
        done, errors = [], []
        for p in paths:
            try:
                done.append((p, self._trash_native(p)))
            except OSError as e:
                errors.append(f"{os.path.basename(p)}: {e.strerror or e}")
        return done, errors

    def _trash_gio(self, paths):
        done, errors = [], []
        for i in range(0, len(paths), 200):  # gio takes many paths per call
            batch = paths[i:i + 200]
            r = subprocess.run(["gio", "trash", "--", *batch], capture_output=True, text=True)
            if r.returncode == 0:
                # we can't check whether a folder is "gone": open programs recreate folders
                # like ~/.cache right away. If gio says it worked, trust it.
                done += [(p, None) for p in batch]
            else:
                done += [(p, None) for p in batch if _gone(p)]
                errors.append(r.stderr.strip() or "could not move it to the Trash")
        return done, errors

    def _trash_dir_for(self, path):
        home_trash = self.home_trash
        os.makedirs(home_trash, mode=0o700, exist_ok=True)
        if os.stat(os.path.dirname(path)).st_dev == os.stat(home_trash).st_dev:
            return home_trash, None
        top = _mount_point(path)
        return os.path.join(top, f".Trash-{os.getuid()}"), top

    def _trash_native(self, path):
        tdir, top = self._trash_dir_for(path)
        files, info = os.path.join(tdir, "files"), os.path.join(tdir, "info")
        os.makedirs(files, mode=0o700, exist_ok=True)
        os.makedirs(info, mode=0o700, exist_ok=True)
        base = os.path.basename(path)
        stem, ext = os.path.splitext(base)
        # unique name inside the Trash: reserve the .trashinfo first (O_EXCL avoids races)
        for n in range(1, 10_000):
            name = base if n == 1 else f"{stem}.{n}{ext}"
            info_path = os.path.join(info, name + ".trashinfo")
            try:
                fd = os.open(info_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            except FileExistsError:
                continue
            if os.path.lexists(os.path.join(files, name)):
                os.close(fd)
                os.remove(info_path)
                continue
            break
        else:
            raise TrashError("could not find a free name in the Trash")
        orig = os.path.relpath(path, top) if top else path
        with os.fdopen(fd, "w") as f:
            f.write(f"[Trash Info]\nPath={quote(orig)}\n"
                    f"DeletionDate={time.strftime('%Y-%m-%dT%H:%M:%S')}\n")
        try:
            os.rename(path, os.path.join(files, name))
        except OSError:
            os.remove(info_path)
            raise
        return os.path.join(files, name)

    # ---- restore
    def _candidate_dirs(self, path):
        dirs = [(self.home_trash, None)]
        top = _mount_point(path)
        dirs += [(os.path.join(top, ".Trash", str(os.getuid())), top),
                 (os.path.join(top, f".Trash-{os.getuid()}"), top)]
        return [d for d in dirs if os.path.isdir(os.path.join(d[0], "info"))]

    def locate(self, paths):
        """For each original path, the newest item in the Trash: {orig: file}."""
        wanted, found, seen = set(paths), {}, set()
        for p in paths:
            for tdir, top in self._candidate_dirs(p):
                if tdir in seen:
                    continue
                seen.add(tdir)
                for orig, date, item in _read_trashinfo_dir(tdir, top):
                    if orig in wanted and (orig not in found or date > found[orig][0]):
                        found[orig] = (date, item)
        return {k: v[1] for k, v in found.items()}

    def restore(self, items):
        missing = [orig for orig, tok in items if not (tok and os.path.lexists(tok))]
        located = self.locate(missing) if missing else {}
        restored, errors = [], []
        for orig, tok in items:
            src = tok if tok and os.path.lexists(tok) else located.get(orig)
            if not src:
                errors.append(f"{os.path.basename(orig)} is no longer in the Trash")
                continue
            try:
                _move_back(src, orig)
            except (OSError, TrashError) as e:
                errors.append(f"{os.path.basename(orig)}: {e}")
                continue
            info = os.path.join(os.path.dirname(os.path.dirname(src)), "info",
                                os.path.basename(src) + ".trashinfo")
            try:
                os.remove(info)
            except OSError:
                pass
            restored.append(orig)
        return restored, errors


def _mount_point(path):
    p = os.path.realpath(path)
    while not os.path.exists(p):  # the item is gone from there: go up until a folder exists
        p = os.path.dirname(p)
    while not os.path.ismount(p):
        p = os.path.dirname(p)
    return p


def _read_trashinfo_dir(tdir, top):
    """(original path, date, file in the Trash) for each .trashinfo in a Trash folder."""
    info_dir = os.path.join(tdir, "info")
    try:
        names = os.listdir(info_dir)
    except OSError:
        return
    for n in names:
        if not n.endswith(".trashinfo"):
            continue
        info_path = os.path.join(info_dir, n)
        orig, date = parse_trashinfo(info_path)
        if orig is None:
            continue
        if not os.path.isabs(orig) and top:
            orig = os.path.join(top, orig)
        # the date only has seconds; the .trashinfo mtime breaks ties within the same second
        try:
            ns = os.stat(info_path).st_mtime_ns
        except OSError:
            ns = 0
        yield os.path.normpath(orig), (date, ns), os.path.join(tdir, "files", n[:-len(".trashinfo")])


def parse_trashinfo(path):
    orig = date = None
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            for line in f:
                if line.startswith("Path="):
                    orig = unquote(line[5:].rstrip("\n"))
                elif line.startswith("DeletionDate="):
                    date = line[13:].strip()
    except OSError:
        pass
    return orig, date or ""


# --------------------------------------------------------------------------- macOS
_FINDER_SCRIPT = """
on run argv
  set out to ""
  repeat with p in argv
    try
      set a to (POSIX file (p as text)) as alias
      tell application "Finder" to set t to (delete a) as alias
      set out to out & "+" & (POSIX path of t) & linefeed
    on error e
      set out to out & "!" & e & linefeed
    end try
  end repeat
  return out
end run
"""


class MacTrash:
    """macOS Trash through Finder, so Finder's "Put Back" also works."""

    def __init__(self, user_trash=None):
        self.user_trash = user_trash or os.path.expanduser("~/.Trash")

    def trash(self, paths):
        done, errors = [], []
        for i in range(0, len(paths), 100):
            batch = paths[i:i + 100]
            r = subprocess.run(["osascript", "-e", _FINDER_SCRIPT, *batch],
                               capture_output=True, text=True)
            lines = r.stdout.splitlines() if r.returncode == 0 else []
            if len(lines) != len(batch):
                # Finder unavailable (e.g. automation permission denied): move directly
                for p in batch:
                    try:
                        done.append((p, self._move_to_trash(p)))
                    except OSError as e:
                        errors.append(f"{os.path.basename(p)}: {e.strerror or e}")
                continue
            for p, line in zip(batch, lines):
                if line.startswith("+"):
                    done.append((p, line[1:].rstrip("/")))
                else:
                    errors.append(f"{os.path.basename(p)}: {line[1:]}")
        return done, errors

    def _move_to_trash(self, path):
        os.makedirs(self.user_trash, exist_ok=True)
        base = os.path.basename(path)
        stem, ext = os.path.splitext(base)
        dest, n = os.path.join(self.user_trash, base), 1
        while os.path.lexists(dest):
            n += 1
            dest = os.path.join(self.user_trash, f"{stem} {n}{ext}")
        shutil.move(path, dest)
        return dest

    def restore(self, items):
        restored, errors = [], []
        for orig, tok in items:
            if not tok or not os.path.lexists(tok):
                errors.append(f"{os.path.basename(orig)} is no longer in the Trash")
                continue
            try:
                _move_back(tok, orig)
                restored.append(orig)
            except (OSError, TrashError) as e:
                errors.append(f"{os.path.basename(orig)}: {e}")
        return restored, errors


# --------------------------------------------------------------------------- Windows
class WindowsTrash:
    """Windows Recycle Bin: sends with SHFileOperationW and restores by reading the $I files."""

    FO_DELETE = 3
    # FOF_ALLOWUNDO (Recycle Bin) | FOF_NOCONFIRMATION | FOF_SILENT | FOF_NOERRORUI |
    # FOF_WANTNUKEWARNING: if the file doesn't fit in the Recycle Bin, Windows asks before
    # deleting it for good, instead of deleting it silently
    FLAGS = 0x40 | 0x10 | 0x04 | 0x400 | 0x4000

    def trash(self, paths):
        from ctypes import wintypes

        class SHFILEOPSTRUCTW(ctypes.Structure):
            _fields_ = [("hwnd", wintypes.HWND), ("wFunc", wintypes.UINT),
                        ("pFrom", wintypes.LPCWSTR), ("pTo", wintypes.LPCWSTR),
                        ("fFlags", ctypes.c_uint16), ("fAnyOperationsAborted", wintypes.BOOL),
                        ("hNameMappings", ctypes.c_void_p), ("lpszProgressTitle", wintypes.LPCWSTR)]

        done, errors = [], []
        for i in range(0, len(paths), 200):
            batch = [os.path.abspath(p) for p in paths[i:i + 200]]
            op = SHFILEOPSTRUCTW(wFunc=self.FO_DELETE, pFrom="\0".join(batch) + "\0\0",
                                 fFlags=self.FLAGS)
            rc = ctypes.windll.shell32.SHFileOperationW(ctypes.byref(op))
            if rc == 0 and not op.fAnyOperationsAborted:
                done += [(p, None) for p in batch]
            else:
                done += [(p, None) for p in batch if _gone(p)]
                errors.append(f"Windows could not move everything (code {rc:#x})")
        return done, errors

    def _bins(self, path):
        drive = os.path.splitdrive(os.path.abspath(path))[0]
        base = os.path.join(drive + os.sep, "$Recycle.Bin")
        try:  # one subfolder per user (SID); only yours can be opened
            return [os.path.join(base, d) for d in os.listdir(base)]
        except OSError:
            return []

    def locate(self, paths, bins=None):
        key = lambda p: os.path.normcase(os.path.normpath(p))
        wanted, found, seen = {key(p): p for p in paths}, {}, set()
        for p in paths:
            for b in (bins if bins is not None else self._bins(p)):
                if b in seen:
                    continue
                seen.add(b)
                try:
                    names = os.listdir(b)
                except OSError:
                    continue
                for n in names:
                    if not n.startswith("$I"):
                        continue
                    try:
                        with open(os.path.join(b, n), "rb") as f:
                            orig, when = parse_recycle_info(f.read())
                    except (OSError, ValueError):
                        continue
                    k = key(orig)
                    if k in wanted and (k not in found or when >= found[k][0]):
                        found[k] = (when, os.path.join(b, "$R" + n[2:]), os.path.join(b, n))
        return {wanted[k]: (v[1], v[2]) for k, v in found.items()}

    def restore(self, items, bins=None):
        located = self.locate([orig for orig, _ in items], bins)
        restored, errors = [], []
        for orig, _ in items:
            hit = located.get(orig)
            if not hit or not os.path.lexists(hit[0]):
                errors.append(f"{os.path.basename(orig)} is no longer in the Trash")
                continue
            try:
                _move_back(hit[0], orig)
                os.remove(hit[1])
                restored.append(orig)
            except (OSError, TrashError) as e:
                errors.append(f"{os.path.basename(orig)}: {e}")
        return restored, errors


def parse_recycle_info(data):
    """Reads a Windows Recycle Bin $I file: (original path, date as FILETIME).

    Version 1 (Vista to 8.1): fixed 260-character path starting at byte 24.
    Version 2 (Windows 10+): path length at byte 24, path starting at byte 28.
    """
    if len(data) < 28:
        raise ValueError("$I file too short")
    version, _size, when = struct.unpack_from("<qqq", data, 0)
    if version == 1:
        raw = data[24:24 + 520]
    elif version == 2:
        (n,) = struct.unpack_from("<i", data, 24)
        raw = data[28:28 + 2 * n]
    else:
        raise ValueError(f"unknown version: {version}")
    return raw.decode("utf-16-le").split("\0", 1)[0], when


# ---------------------------------------------------------------------------
def get_backend():
    if sys.platform == "darwin":
        return MacTrash()
    if sys.platform == "win32":
        return WindowsTrash()
    return FreedesktopTrash()


_backend = None


def backend():
    global _backend
    if _backend is None:
        _backend = get_backend()
    return _backend


def trash(paths):
    """Sends the paths to the Trash. Returns ([(path, hint)], [errors])."""
    return backend().trash(list(paths))


def restore(items):
    """Restores [(path, hint)] to their original place. Returns ([restored], [errors])."""
    return backend().restore(list(items))
