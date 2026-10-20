"""Entry point: cleaner [folder] [--port N] [--no-browser]  (or python3 -m cleaner)"""
import argparse
import threading
import webbrowser
from pathlib import Path

from . import __version__
from .config import HOST, PORT
from .server import make_server
from .state import start_scan


def main():
    parser = argparse.ArgumentParser(prog="cleaner", description="See what is taking up space and clean up your folders.")
    parser.add_argument("folder", nargs="?", default=str(Path.home()), help="folder to scan (default: your home folder)")
    parser.add_argument("--port", type=int, default=PORT, help=f"local server port (default: {PORT})")
    parser.add_argument("--no-browser", action="store_true", help="don't open the browser automatically")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    args = parser.parse_args()

    start_scan(args.folder)
    try:
        server = make_server(args.port)
    except OSError:
        parser.exit(1, f"Port {args.port} is already in use. Is Cleaner already open? "
                       f"Use --port to pick another one.\n")
    url = f"http://{HOST}:{args.port}/"
    print(f"Cleaner running at {url}  (Ctrl+C to quit)")
    if not args.no_browser:
        threading.Timer(0.5, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nBye!")


if __name__ == "__main__":
    main()
