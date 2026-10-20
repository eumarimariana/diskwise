"""In-memory app state (result of the last scan) and path helpers."""
import itertools
import os
import threading

from .duplicates import reset as reset_duplicates
from .scanner import scan

state = {"root": None, "scanning": False, "progress": 0, "data": None, "freed": 0, "trashed": 0}
lock = threading.Lock()

# what went to the Trash in this session, oldest to newest, so it can be undone.
# Each operation: {"id", "label", "items": [(absolute path, Trash hint, size, file count)]}
undo_stack = []
UNDO_LIMIT = 50
_ids = itertools.count(1)


def start_scan(root):
    state.update(scanning=True, progress=0)
    threading.Thread(target=run_scan, args=(root,), daemon=True).start()


def run_scan(root):
    try:
        data = scan(root, on_progress=lambda n: state.update(progress=n))
        with lock:
            state.update(data=data, root=data["root"], freed=0, trashed=0)
            reset_duplicates()
    finally:
        state["scanning"] = False


def inside(path, root):
    """`path` is `root` or inside it (also works with root = "/" or "C:\\")."""
    return path == root or path.startswith(os.path.join(root, ""))


def safe_path(relpath):
    """Resolves a relative path, making sure it stays inside the scanned root."""
    root = state["root"]
    if not root or relpath is None:
        return None
    p = os.path.realpath(os.path.join(root, relpath))
    return p if inside(p, root) else None


def adjust_totals(folder, size, count):
    """Adds (or subtracts, with negative values) to `folder` and every folder above it."""
    totals = state["data"]["_totals"]
    f = os.path.normpath(folder)
    while True:
        t = totals.setdefault(f, [0, 0])
        t[0] += size
        t[1] += count
        if f == ".":
            break
        f = os.path.dirname(f) or "."


def subtree(folder):
    """Relative folders in the tree that starts at `folder`, including it."""
    files = state["data"]["_files"]
    if folder in (".", ""):
        return list(files)
    return [k for k in files if k == folder or k.startswith(folder + os.sep)]


def push_undo(label, items):
    """Stores a Trash operation so it can be undone. Returns its summary."""
    if not items:
        return last_undo()
    op = {"id": next(_ids), "label": label, "items": items}
    undo_stack.append(op)
    del undo_stack[:-UNDO_LIMIT]
    return summary(op)


def summary(op):
    return {"id": op["id"], "label": op["label"], "count": sum(i[3] for i in op["items"]),
            "size": sum(i[2] for i in op["items"])}


def last_undo():
    return summary(undo_stack[-1]) if undo_stack else None


def add_back(path):
    """Adds a file or folder that came back from the Trash to the totals again.

    Returns the relative folders that got files back. Outside the current root it does
    nothing (undo still works after scanning another folder).
    """
    root, data = state["root"], state["data"]
    if not data or not inside(path, root):
        return set()
    files_map, touched = data["_files"], set()

    def add_file(d, name):
        try:
            st = os.stat(os.path.join(d, name), follow_symlinks=False)
        except OSError:
            return
        rel = os.path.relpath(d, root)
        fs = files_map.get(rel, [])
        old = next((f for f in fs if f[0] == name), None)
        if old:  # already in the list: replace it without counting it twice
            fs = [f for f in fs if f is not old]
            adjust_totals(rel, -old[1], -1)
        fs.append((name, st.st_size, st.st_mtime))
        fs.sort(key=lambda f: -f[1])
        files_map[rel] = fs
        adjust_totals(rel, st.st_size, 1)
        touched.add(rel)

    if os.path.isdir(path) and not os.path.islink(path):
        for d, _, names in os.walk(path):
            for n in names:
                if not os.path.islink(os.path.join(d, n)):
                    add_file(d, n)
    else:
        add_file(os.path.dirname(path), os.path.basename(path))
    return touched
