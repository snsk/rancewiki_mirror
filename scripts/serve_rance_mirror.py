from __future__ import annotations

import json
import mimetypes
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit


WORKSPACE = Path(__file__).resolve().parents[1]
OUTPUT_ROOT = WORKSPACE / "rance-world-note"
MANIFEST_PATH = OUTPUT_ROOT / "_mirror" / "manifest.json"
HOST = "127.0.0.1"
PORT = 8000


def load_manifest() -> dict[str, object]:
    if not MANIFEST_PATH.exists():
        raise SystemExit(
            f"Manifest not found: {MANIFEST_PATH}\n"
            "Run `python scripts/build_rance_mirror.py` first."
        )
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


MANIFEST = load_manifest()
ROUTES: dict[str, str] = MANIFEST["routes"]  # type: ignore[assignment]


class MirrorHandler(BaseHTTPRequestHandler):
    server_version = "RanceMirrorHTTP/1.0"

    def do_GET(self) -> None:
        self._serve(send_body=True)

    def do_HEAD(self) -> None:
        self._serve(send_body=False)

    def _serve(self, *, send_body: bool) -> None:
        request_path = urlsplit(self.path).path
        if request_path == "/":
            self.send_response(HTTPStatus.FOUND)
            self.send_header("Location", "/rance-world-note/")
            self.end_headers()
            return

        relative = ROUTES.get(request_path)
        if relative is None and request_path.endswith("/"):
            relative = ROUTES.get(request_path.rstrip("/"))
        elif relative is None:
            relative = ROUTES.get(request_path + "/")

        if relative is None and request_path.startswith("/assets/"):
            relative = request_path.lstrip("/")
        elif relative is None and request_path.startswith("/rance-world-note/assets/"):
            relative = request_path[len("/rance-world-note/") :]

        if relative is None:
            self.send_error(HTTPStatus.NOT_FOUND, "Not found")
            return

        target = (OUTPUT_ROOT / relative).resolve()
        try:
            target.relative_to(OUTPUT_ROOT.resolve())
        except ValueError:
            self.send_error(HTTPStatus.FORBIDDEN, "Forbidden")
            return

        if not target.exists() or not target.is_file():
            self.send_error(HTTPStatus.NOT_FOUND, "File missing")
            return

        content = target.read_bytes()
        content_type = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        if target.suffix in {".html", ".css", ".js", ".json"}:
            content_type = f"{content_type}; charset=utf-8"

        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        if send_body:
            self.wfile.write(content)


def main() -> None:
    httpd = ThreadingHTTPServer((HOST, PORT), MirrorHandler)
    print(f"Serving Rance mirror on http://{HOST}:{PORT}/rance-world-note/")
    print("Press Ctrl+C to stop.")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()


if __name__ == "__main__":
    main()
