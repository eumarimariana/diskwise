"""Disk scan: sizes per folder and per type, and the largest files."""
import os
from collections import defaultdict

from .config import HOME
from .describe import known_context
from .rules import SAFE_DIRS, classify


def is_junction(entry):
    # Windows "junctions" look like normal folders but point somewhere else
    f = getattr(entry, "is_junction", None)
    return bool(f and f())


def folder_entry(d, root, files):
    """Summary of a folder (direct files only) for the list on the Clean screen."""
    risk, reasons = classify(d, root=root)
    chain = known_context(d)
    return {"path": os.path.relpath(d, root), "size": sum(f[1] for f in files),
            "count": len(files), "risk": risk, "reasons": reasons,
            "label": " › ".join(c[1] for c in chain[-2:]) or None}


def scan(root, on_progress=None):
    """Walks the tree (without following links) and adds up sizes."""
    root = os.path.realpath(root)
    dir_files = defaultdict(list)    # folder -> [(name, size, mtime)]
    dir_total = defaultdict(int)     # folder -> recursive size
    dir_count = defaultdict(int)     # folder -> recursive file count
    by_ext = defaultdict(lambda: [0, 0])
    count = 0
    stack = [root]
    while stack:
        d = stack.pop()
        try:
            entries = list(os.scandir(d))
        except OSError:
            continue
        for e in entries:
            try:
                if e.is_symlink() or is_junction(e):
                    continue
                if e.is_dir():
                    stack.append(e.path)
                elif e.is_file():
                    st = e.stat()
                    dir_files[d].append((e.name, st.st_size, st.st_mtime))
                    ext = os.path.splitext(e.name)[1].lower() or "(no extension)"
                    by_ext[ext][0] += st.st_size
                    by_ext[ext][1] += 1
                    count += 1
                    if on_progress and count % 2000 == 0:
                        on_progress(count)
            except OSError:
                continue

    # recursive sum: each folder adds its direct size to all its ancestors
    for d, files in dir_files.items():
        size = sum(f[1] for f in files)
        p = d
        while True:
            dir_total[p] += size
            dir_count[p] += len(files)
            if p == root:
                break
            p = os.path.dirname(p)

    rel = lambda p: os.path.relpath(p, root)
    folders, safe_spots = [], defaultdict(int)
    for d, fs in dir_files.items():
        entry = folder_entry(d, root, fs)
        folders.append(entry)
        size = entry["size"]
        if entry["risk"] == "safe":
            # group by the top cache folder (e.g. ~/.cache), not by each subfolder
            parts = d.split(os.sep)
            base = HOME if d.startswith(HOME + os.sep) else root
            sub = os.path.relpath(d, base).split(os.sep)
            i = next((i for i, p in enumerate(sub) if p in SAFE_DIRS), len(sub) - 1)
            spot = os.path.join(base, *sub[:i + 1])
            safe_spots[os.path.relpath(spot, root) if spot.startswith(root) else spot] += size
    folders.sort(key=lambda x: -x["size"])
    all_files = [(os.path.join(d, n), s, m) for d, fs in dir_files.items() for n, s, m in fs]
    all_files.sort(key=lambda f: -f[1])
    # top-level folders under the root, for the main chart
    top_level = sorted(
        ((rel(d), t) for d, t in dir_total.items() if os.path.dirname(d) == root),
        key=lambda x: -x[1])
    return {
        "root": root,
        "total": dir_total.get(root, 0),
        "file_count": count,
        "top_level": top_level[:20],
        "heaviest": sorted(((rel(d), t) for d, t in dir_total.items() if d != root),
                           key=lambda x: -x[1])[:30],
        "by_ext": sorted(((k, v[0], v[1]) for k, v in by_ext.items()), key=lambda x: -x[1])[:20],
        "largest_files": [(rel(p), s) for p, s, _ in all_files[:30]],
        # for the Clean screen: folders with direct files, largest first
        "folders": folders,
        "safe_total": sum(f["size"] for f in folders if f["risk"] == "safe"),
        "safe_spots": sorted(safe_spots.items(), key=lambda x: -x[1])[:15],
        "_files": {rel(d): sorted(fs, key=lambda f: -f[1]) for d, fs in dir_files.items()},
        # recursive totals, for the Explore screen
        "_totals": {rel(d): [t, dir_count[d]] for d, t in dir_total.items()},
    }
