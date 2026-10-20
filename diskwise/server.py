"""Local HTTP server: serves the interface and the JSON API it uses."""
import json
import mimetypes
import os
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from . import actions, duplicates
from .config import HOST, STATIC, TOKEN
from .describe import describe_folder
from .state import last_undo, safe_path, start_scan, state


mimetypes.add_type("font/woff2", ".woff2")
mimetypes.add_type("text/javascript", ".js")  # Windows sometimes registers .js with another type


def static_file(name):
    """A file inside the static folder (subfolders are fine, going up is not)."""
    f = (STATIC / name).resolve()
    return f if f.is_file() and STATIC in f.parents else None


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def send_json(self, obj, code=200):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_bytes(self, body, mime):
        self.send_response(200)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def authorized(self, qs):
        return self.headers.get("X-Token") == TOKEN or qs.get("t", [""])[0] == TOKEN

    def do_GET(self):
        self.safely(self.handle_get)

    def do_POST(self):
        self.safely(self.handle_post)

    def safely(self, fn):
        # an unexpected error becomes an error response instead of dropping the connection
        try:
            fn()
        except Exception as e:
            traceback.print_exc()
            self.send_json({"error": f"internal error: {e}"}, 500)

    def handle_get(self):
        url = urlparse(self.path)
        qs = parse_qs(url.query)
        if url.path == "/":
            body = (STATIC / "index.html").read_bytes().replace(b"__TOKEN__", TOKEN.encode())
            return self.send_bytes(body, "text/html; charset=utf-8")
        if url.path.startswith("/static/"):
            f = static_file(url.path[len("/static/"):])
            if f:
                mime = mimetypes.guess_type(f.name)[0] or "application/octet-stream"
                return self.send_bytes(f.read_bytes(), mime)
            return self.send_json({"error": "not found"}, 404)
        if not self.authorized(qs):
            return self.send_json({"error": "invalid token"}, 403)

        if url.path == "/api/status":
            d = state["data"]
            report = {k: v for k, v in d.items() if not k.startswith("_")} if d else None
            if report:
                report["folders"] = report["folders"][:1000]
            return self.send_json({"scanning": state["scanning"], "progress": state["progress"],
                                   "report": report, "freed": state["freed"],
                                   "trashed": state["trashed"], "home": str(Path.home()),
                                   "sep": os.sep, "undo": last_undo()})
        if url.path == "/api/duplicates":
            return self.send_json(duplicates.report(state["root"]))
        if url.path == "/api/files":
            return self.send_json(actions.list_files(qs.get("folder", [""])[0]))
        if url.path == "/api/folder_info":
            folder = qs.get("folder", [""])[0]
            p = safe_path(folder)
            if not p or not os.path.isdir(p):
                return self.send_json({"error": "folder not found"}, 404)
            files = (state["data"] or {}).get("_files", {}).get(folder, [])
            return self.send_json(describe_folder(p, files))
        if url.path == "/api/browse":
            folder = os.path.normpath(qs.get("folder", ["."])[0] or ".")
            p = safe_path(folder)
            if not p or not os.path.isdir(p):
                return self.send_json({"error": "folder not found"}, 404)
            return self.send_json(actions.browse(folder, p))
        if url.path == "/api/bulk_preview":
            folder = qs.get("folder", [""])[0]
            if not safe_path(folder):
                return self.send_json({"error": "invalid folder"}, 400)
            return self.send_json({"files": actions.bulk_files_stats(folder),
                                   "tree": actions.bulk_tree_stats(folder),
                                   "is_root": folder in (".", "")})
        if url.path == "/api/preview":
            return self.send_preview(safe_path(qs.get("path", [None])[0]))
        self.send_json({"error": "unknown route"}, 404)

    def send_preview(self, p):
        if not p or not os.path.isfile(p):
            return self.send_json({"error": "not found"}, 404)
        mime = mimetypes.guess_type(p)[0] or "application/octet-stream"
        size = os.path.getsize(p)
        limit = 50_000 if mime.startswith("text") else 200_000_000
        self.send_response(200)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(min(size, limit)))
        self.end_headers()
        try:
            with open(p, "rb") as f:
                self.wfile.write(f.read(limit))
        except OSError:
            pass

    def handle_post(self):
        url = urlparse(self.path)
        if not self.authorized({}):
            return self.send_json({"error": "invalid token"}, 403)
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length) or b"{}")

        if url.path == "/api/scan":
            root = os.path.expanduser(body.get("root") or "~")
            if not os.path.isdir(root):
                return self.send_json({"error": "folder does not exist"}, 400)
            if state["scanning"]:
                return self.send_json({"error": "already scanning"}, 409)
            start_scan(root)
            return self.send_json({"ok": True})

        if url.path == "/api/trash":
            folder, name = body.get("folder"), body.get("name")
            p = safe_path(os.path.join(folder or "", name or ""))
            if not p or not os.path.isfile(p):
                return self.send_json({"error": "invalid file"}, 400)
            return self.send_json(*actions.trash_file(folder, name, p))

        if url.path == "/api/trash_paths":
            paths = body.get("paths")
            if not isinstance(paths, list) or not paths or not state["data"]:
                return self.send_json({"error": "no files"}, 400)
            return self.send_json(*actions.trash_paths(paths, duplicates.groups_paths()))

        if url.path == "/api/undo":
            return self.send_json(*actions.undo(body.get("id")))

        if url.path == "/api/duplicates":
            if not state["data"] or state["scanning"]:
                return self.send_json({"error": "scan a folder first"}, 400)
            min_size = max(1, int(body.get("min_size") or 1))
            if not duplicates.start(state["data"]["_files"], state["root"], min_size):
                return self.send_json({"error": "already searching"}, 409)
            return self.send_json({"ok": True})

        if url.path == "/api/trash_bulk":
            return self.send_json(*actions.trash_bulk(body.get("folder") or "", body.get("mode"),
                                                      bool(body.get("include_danger"))))

        self.send_json({"error": "unknown route"}, 404)


def make_server(port):
    return ThreadingHTTPServer((HOST, port), Handler)
