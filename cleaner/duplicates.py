"""Duplicate files: the same content in more than one place.

Compares in stages, cheapest first, so the disk is not read for nothing:
1. same size (comes from the scan, reads nothing);
2. hash of the start and end of each file (64 KB from each end);
3. hash of the whole file, only for files still tied at this point.
"""
import hashlib
import mimetypes
import os
import threading
from collections import defaultdict

from .rules import classify

CHUNK = 64 * 1024
MAX_GROUPS = 2000

dup = {"running": False, "stage": "", "done": 0, "total": 0, "groups": None, "min_size": 0,
       "error": None}
_gen = 0  # changes on every new scan, so an old search is discarded


def reset():
    global _gen
    _gen += 1
    dup.update(running=False, stage="", done=0, total=0, groups=None, error=None)


def _hash(path, partial):
    h = hashlib.blake2b(digest_size=20)
    with open(path, "rb") as f:
        if partial:
            h.update(f.read(CHUNK))
            if os.fstat(f.fileno()).st_size > 2 * CHUNK:
                f.seek(-CHUNK, os.SEEK_END)
                h.update(f.read(CHUNK))
            else:  # small file: read the rest, so the hash already covers the whole file
                h.update(f.read())
        else:
            for block in iter(lambda: f.read(1 << 20), b""):
                h.update(block)
    return h.hexdigest()


def find_duplicates(files_map, root, min_size=1, on_progress=None, cancelled=lambda: False):
    """Groups of identical files: [{"size", "files": [(relative path, mtime)]}].

    `files_map` is the scan's `_files`: relative folder -> [(name, size, mtime)].
    """
    by_size = defaultdict(list)
    for folder, fs in files_map.items():
        for name, size, mtime in fs:
            if size >= max(1, min_size):
                by_size[size].append((os.path.normpath(os.path.join(folder, name)), mtime))
    candidates = [(s, fs) for s, fs in by_size.items() if len(fs) > 1]

    def refine(groups, stage, partial):
        total = sum(len(fs) for _, fs in groups)
        done, out = 0, []
        for size, fs in groups:
            by_hash = defaultdict(list)
            for rel, mtime in fs:
                if cancelled():
                    return []
                try:
                    by_hash[_hash(os.path.join(root, rel), partial)].append((rel, mtime))
                except OSError:
                    pass  # gone or no permission: left out
                done += 1
                if on_progress and done % 50 == 0:
                    on_progress(stage, done, total)
            out += [(size, g) for g in by_hash.values() if len(g) > 1]
        if on_progress:
            on_progress(stage, total, total)
        return out

    # hardlinks are the same file on disk with two names: deleting one frees nothing
    unique = []
    for size, fs in candidates:
        seen, keep = set(), []
        for rel, mtime in fs:
            try:
                st = os.stat(os.path.join(root, rel), follow_symlinks=False)
            except OSError:
                continue
            if (st.st_dev, st.st_ino) in seen:
                continue
            seen.add((st.st_dev, st.st_ino))
            keep.append((rel, mtime))
        if len(keep) > 1:
            unique.append((size, keep))

    groups = refine(unique, "Comparing the start and end", partial=True)
    # small files were already read in full in the previous stage
    small = [g for g in groups if g[0] <= 2 * CHUNK]
    groups = small + refine([g for g in groups if g[0] > 2 * CHUNK], "Comparing the full content", partial=False)
    groups.sort(key=lambda g: -g[0] * (len(g[1]) - 1))
    return [{"size": s, "files": sorted(fs, key=lambda f: f[1])} for s, fs in groups]


def start(files_map, root, min_size):
    """Starts the search in the background. Returns False if one is already running."""
    if dup["running"]:
        return False
    gen = _gen
    dup.update(running=True, stage="Grouping by size", done=0, total=0, groups=None,
               min_size=min_size, error=None)
    snapshot = {k: list(v) for k, v in files_map.items()}

    def progress(stage, done, total):
        if gen == _gen:
            dup.update(stage=stage, done=done, total=total)

    def run():
        try:
            groups = find_duplicates(snapshot, root, min_size, progress, lambda: gen != _gen)
            if gen == _gen:
                dup["groups"] = groups
        except Exception as e:  # show the error on screen instead of hanging on "searching…"
            if gen == _gen:
                dup["error"] = str(e)
        finally:
            if gen == _gen:
                dup["running"] = False

    threading.Thread(target=run, daemon=True).start()
    return True


def report(root):
    """Result for the interface, without files that have moved since (Trash etc.)."""
    out = {k: dup[k] for k in ("running", "stage", "done", "total", "min_size", "error")}
    if dup["groups"] is None:
        out["groups"] = None
        return out
    groups = []
    for g in dup["groups"]:
        files = []
        for rel, mtime in g["files"]:
            p = os.path.join(root, rel)
            if not os.path.isfile(p):
                continue
            risk, reasons = classify(p, g["size"], mtime, True, root)
            files.append({"path": rel, "mtime": mtime, "risk": risk, "reasons": reasons,
                          "mime": mimetypes.guess_type(rel)[0] or ""})
        if len(files) > 1:
            groups.append({"size": g["size"], "files": files})
    out["groups"] = groups[:MAX_GROUPS]
    out["group_count"] = len(groups)
    out["wasted"] = sum(g["size"] * (len(g["files"]) - 1) for g in groups)
    out["extra_files"] = sum(len(g["files"]) - 1 for g in groups)
    return out


def groups_paths():
    """The groups as lists of paths, so the server can check "keep at least one copy"."""
    return [[rel for rel, _ in g["files"]] for g in dup["groups"] or []]
