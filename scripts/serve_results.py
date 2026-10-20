"""Read-only local result viewer; no model calls."""
import functools
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
root=Path(__file__).resolve().parents[1]/"results"
print("Open http://127.0.0.1:8788/ (Ctrl+C to stop)",flush=True)
ThreadingHTTPServer(("127.0.0.1",8788),functools.partial(SimpleHTTPRequestHandler,directory=str(root))).serve_forever()
