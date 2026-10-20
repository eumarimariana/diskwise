"""Disk actions: list, browse and send files/folders to the Trash."""
import mimetypes
import os
from collections import defaultdict

from . import trash
from .config import HOME
from .describe import known_context, plural
from .rules import classify
from .scanner import folder_entry
from .state import (add_back, adjust_totals, inside, last_undo, lock, push_undo, safe_path,
                    state, subtree, undo_stack)


def list_files(folder):
    """Direct files of a folder, with their risk, for the Clean screen."""
    out = []
    for n, s, m in (state["data"] or {}).get("_files", {}).get(folder, []):
        risk, reasons = classify(os.path.normpath(os.path.join(state["root"], folder, n)),
                                 s, m, True, state["root"])
        out.append({"name": n, "size": s, "mtime": m, "risk": risk, "reasons": reasons,
                    "mime": mimetypes.guess_type(n)[0] or ""})
    return out


def _forget_file(folder, name):
    """Removes a file from the in-memory totals. Returns its size."""
    files = state["data"]["_files"].get(folder, [])
    size = next((f[1] for f in files if f[0] == name), 0)
    state["data"]["_files"][folder] = [f for f in files if f[0] != name]
    state["freed"] += size
    state["trashed"] += 1
    adjust_totals(folder, -size, -1)
    return size


def trash_file(folder, name, path):
    """Sends a file to the Trash and updates the totals."""
    done, errors = trash.trash([path])
    if not done:
        return {"error": (errors or ["could not move it"])[0]}, 500
    with lock:
        size = _forget_file(folder, name)
        undo = push_undo(name, [(path, done[0][1], size, 1)])
    return {"ok": True, "freed": state["freed"], "undo": undo}, 200


def trash_paths(relpaths, groups=None):
    """Sends a list of files (relative paths) to the Trash as a single operation.

    `groups`: duplicate groups; refuses to delete every copy in a group.
    """
    targets = []
    for rel in dict.fromkeys(relpaths):  # no repeats, same order
        p = safe_path(rel)
        if not p or not os.path.isfile(p) or os.path.islink(p):
            return {"error": f"invalid file: {rel}"}, 400
        targets.append((os.path.relpath(p, state["root"]), p))
    chosen = {rel for rel, _ in targets}
    for g in groups or []:
        alive = [f for f in g if os.path.lexists(os.path.join(state["root"], f))]
        if alive and all(f in chosen for f in alive):
            return {"error": "keep at least one copy of each duplicate file"}, 400
    done, errors = trash.trash([p for _, p in targets])
    tokens = dict(done)
    items, touched = [], set()
    with lock:
        for rel, p in targets:
            if p not in tokens:
                continue
            folder = os.path.dirname(rel) or "."
            size = _forget_file(folder, os.path.basename(rel))
            items.append((p, tokens[p], size, 1))
            touched.add(folder)
        undo = push_undo(plural(len(items), "file"), items)
    return {"ok": True, "trashed": len(items), "freed_now": sum(i[2] for i in items),
            "freed": state["freed"], "errors": errors[:3], "undo": undo,
            "folders": folder_entries(touched)}, 200


def folder_entries(folders):
    """Updated summary of each folder (so the interface can refresh the Clean screen list)."""
    root, files_map = state["root"], state["data"]["_files"]
    return [folder_entry(os.path.normpath(os.path.join(root, f)), root, files_map.get(f, []))
            for f in sorted(folders)]


def undo(op_id=None):
    """Takes back out of the Trash what operation `op_id` deleted (default: the latest one)."""
    with lock:
        op = next((o for o in reversed(undo_stack) if op_id is None or o["id"] == op_id), None)
        if op is None:
            return {"error": "nothing to undo"}, 404
        undo_stack.remove(op)
    restored, errors = trash.restore([(p, tok) for p, tok, _, _ in op["items"]])
    restored = set(restored)
    touched, left = set(), []
    with lock:
        for item in op["items"]:
            p, _, size, count = item
            if p not in restored:
                left.append(item)
                continue
            touched |= add_back(p)
            state["freed"] = max(0, state["freed"] - size)
            state["trashed"] = max(0, state["trashed"] - count)
        if left:  # whatever could not be restored stays available to try again
            undo_stack.append({**op, "items": left})
        root = state["root"]
        rel = [os.path.relpath(p, root) for p in restored if root and inside(p, root)]
    if not restored:
        return {"error": (errors or ["could not restore it"])[0], "undo": last_undo()}, 500
    return {"ok": True, "undone": op["id"], "restored": len(restored), "paths": rel, "errors": errors[:3],
            "freed": state["freed"], "trashed": state["trashed"], "undo": last_undo(),
            "folders": folder_entries(touched) if state["data"] else []}, 200


def file_risks(folder):
    root = state["root"]
    for n, s, m in state["data"]["_files"].get(folder, []):
        yield n, s, classify(os.path.normpath(os.path.join(root, folder, n)), s, m, True, root)[0]


def bulk_files_stats(folder):
    by = defaultdict(lambda: [0, 0])
    for _, s, r in file_risks(folder):
        by[r][0] += 1
        by[r][1] += s
    return {"by_risk": by, "count": sum(v[0] for v in by.values()), "size": sum(v[1] for v in by.values())}


def bulk_tree_stats(folder):
    by = defaultdict(lambda: [0, 0])
    folders = subtree(folder)
    per_file = sum(len(state["data"]["_files"][k]) for k in folders) <= 100_000
    for k in folders:
        if per_file:
            for _, s, r in file_risks(k):
                by[r][0] += 1
                by[r][1] += s
        else:  # huge tree: risk per subfolder, so it does not freeze
            fs = state["data"]["_files"][k]
            r = classify(os.path.normpath(os.path.join(state["root"], k)), root=state["root"])[0]
            by[r][0] += len(fs)
            by[r][1] += sum(f[1] for f in fs)
    return {"by_risk": by, "count": sum(v[0] for v in by.values()), "size": sum(v[1] for v in by.values()),
            "subfolders": len(folders) - 1}


def trash_bulk(folder, mode, include_danger):
    """Sends the folder's direct files ('files') or the whole folder ('tree') to the Trash."""
    p = safe_path(folder)
    if not p or not os.path.isdir(p):
        return {"error": "invalid folder"}, 400
    files_map = state["data"]["_files"]

    if mode == "files":
        targets = [(n, s) for n, s, r in file_risks(folder) if include_danger or r != "danger"]
        done, errors = trash.trash([os.path.join(p, n) for n, _ in targets])
        tokens = dict(done)
        items = [(os.path.join(p, n), tokens[os.path.join(p, n)], s, 1)
                 for n, s in targets if os.path.join(p, n) in tokens]
        gone = {os.path.basename(i[0]) for i in items}
        freed = sum(i[2] for i in items)
        with lock:
            files_map[folder] = [f for f in files_map.get(folder, []) if f[0] not in gone]
            state["freed"] += freed
            state["trashed"] += len(gone)
            adjust_totals(folder, -freed, -len(gone))
            undo = push_undo(f"{plural(len(gone), 'file')} from {os.path.basename(p)}", items)
        return {"ok": True, "trashed": len(gone), "freed_now": freed, "freed": state["freed"],
                "skipped": len(files_map[folder]), "errors": errors[:3], "undo": undo}, 200

    if mode == "tree":
        if p == state["root"] or p == HOME:
            return {"error": "you can't delete the whole scanned folder or your home folder"}, 400
        stats = bulk_tree_stats(folder)
        if stats["by_risk"].get("danger") and not include_danger:
            return {"error": "the folder has dangerous content; tick the confirmation to continue"}, 400
        done, errors = trash.trash([p])
        if not done:
            return {"error": (errors or ["could not move it"])[0]}, 500
        with lock:
            for k in subtree(folder):
                files_map.pop(k, None)
            totals = state["data"]["_totals"]
            for k in [k for k in totals if k == folder or k.startswith(folder + os.sep)]:
                del totals[k]
            adjust_totals(os.path.dirname(folder) or ".", -stats["size"], -stats["count"])
            state["freed"] += stats["size"]
            state["trashed"] += stats["count"]
            undo = push_undo(f"folder {os.path.basename(p)}", [(p, done[0][1], stats["size"], stats["count"])])
        return {"ok": True, "trashed": stats["count"], "freed_now": stats["size"],
                "freed": state["freed"], "undo": undo}, 200

    return {"error": "invalid mode"}, 400


def browse(folder, p):
    """Folder contents for the Explore screen: subfolders (with recursive totals) and files."""
    data, root = state["data"], state["root"]
    totals = data["_totals"]
    subdirs = []
    try:
        names = [e.name for e in os.scandir(p) if e.is_dir(follow_symlinks=False)]
    except OSError:
        names = []
    for n in names:
        rel = os.path.normpath(os.path.join(folder, n))
        size, count = totals.get(rel, [0, 0])
        absd = os.path.join(p, n)
        chain = known_context(absd)
        subdirs.append({"name": n, "path": rel, "size": size, "count": count,
                        "risk": classify(absd, root=root)[0],
                        "label": chain[-1][1] if chain else None})
    subdirs.sort(key=lambda d: -d["size"])
    files = []
    for n, s, m in data["_files"].get(folder, []):
        risk, reasons = classify(os.path.join(p, n), s, m, True, root)
        files.append({"name": n, "size": s, "mtime": m, "risk": risk, "reasons": reasons,
                      "mime": mimetypes.guess_type(n)[0] or ""})
    total, count = totals.get(folder, [0, 0])
    return {"path": folder, "total": total, "count": count, "subdirs": subdirs, "files": files}
