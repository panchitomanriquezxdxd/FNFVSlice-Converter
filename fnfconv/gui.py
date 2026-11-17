"""Local web GUI (stdlib only). Binds to 127.0.0.1; POST endpoints require a custom header (anti-CSRF)."""
from __future__ import annotations

import io
import json
import tempfile
import threading
import traceback
import uuid
import webbrowser
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .core import resolve_root, run_convert
from .detect import detect_engine

WORK = Path(tempfile.mkdtemp(prefix="fnfconv_gui_"))
JOBS: dict[str, dict] = {}
MAX_UPLOAD = 4 * 1024 ** 3
HTML = Path(__file__).parent / "gui_static" / "index.html"


def safe_extract(zpath, dest):
    dest = Path(dest).resolve()
    with zipfile.ZipFile(zpath) as z:
        for m in z.infolist():
            target = (dest / m.filename).resolve()
            if dest != target and dest not in target.parents:
                raise ValueError(f"unsafe path in zip: {m.filename}")
        z.extractall(dest)


def inspect(path):
    root = resolve_root(path)
    if not root.is_dir():
        raise ValueError(f"Not a folder: {path}")
    engine, ev = detect_engine(root)
    files = [p for p in root.rglob("*") if p.is_file()]
    return {"root": str(root), "engine": engine, "evidence": ev, "files": len(files),
            "scripts": sum(1 for p in files if p.suffix.lower() in (".lua", ".hx", ".hscript"))}


def start_job(o):
    jid = uuid.uuid4().hex[:10]
    out = Path(o.get("save_to") or WORK / jid / "out")
    job = {"state": "running", "log": [], "out": str(out), "error": None}
    JOBS[jid] = job

    def work():
        try:
            rep = run_convert(o["path"], out, o.get("engine", "auto"), o.get("ai", "auto"), o.get("model") or None,
                              o.get("base_url") or None, o.get("api_key") or None, bool(o.get("ai_review")),
                              bool(o.get("mirror_shared")), bool(o.get("no_scripts")), o.get("mod_id") or None,
                              log=lambda m: job["log"].append(str(m)))
            job.update(report=rep.to_markdown(), stats=rep.stats, warnings=len(rep.warnings), todo=len(rep.todo),
                       engine=rep.engine, state="done")
        except Exception as e:  # noqa: BLE001
            job["log"].append(traceback.format_exc())
            job.update(state="error", error=str(e))

    threading.Thread(target=work, daemon=True).start()
    return jid


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a): pass

    def _send(self, code, body, ctype="application/json", extra=None):
        if isinstance(body, (dict, list)):
            body = json.dumps(body).encode()
        elif isinstance(body, str):
            body = body.encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _guard(self, post=False):
        host = (self.headers.get("Host") or "").rsplit(":", 1)[0].strip("[]")
        if host not in ("127.0.0.1", "localhost", "::1"):
            self._send(403, {"error": "forbidden host"}); return False
        if post and self.headers.get("X-FNFCONV") != "1":
            self._send(403, {"error": "missing header"}); return False
        return True

    def do_GET(self):
        if not self._guard():
            return
        u = urlparse(self.path)
        q = parse_qs(u.query)
        job = JOBS.get((q.get("job") or [""])[0])
        if u.path == "/":
            return self._send(200, HTML.read_bytes(), "text/html; charset=utf-8")
        if u.path == "/api/status" and job:
            return self._send(200, {k: v for k, v in job.items() if k != "out"} | {"log": job["log"][-400:]})
        if u.path == "/api/download" and job and job["state"] == "done":
            buf, out = io.BytesIO(), Path(job["out"])
            with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
                for f in sorted(out.rglob("*")):
                    if f.is_file():
                        z.write(f, f.relative_to(out).as_posix())
            return self._send(200, buf.getvalue(), "application/zip",
                              {"Content-Disposition": 'attachment; filename="vslice-mod.zip"'})
        self._send(404, {"error": "not found"})

    def do_POST(self):
        if not self._guard(post=True):
            return
        u = urlparse(self.path)
        try:
            n = int(self.headers.get("Content-Length") or 0)
            if u.path == "/api/upload":
                if n <= 0 or n > MAX_UPLOAD:
                    return self._send(400, {"error": "empty or too large upload"})
                name = Path((parse_qs(u.query).get("name") or ["mod.zip"])[0]).name
                if not name.lower().endswith(".zip"):
                    return self._send(400, {"error": "Please upload the mod as a .zip"})
                d = WORK / ("up_" + uuid.uuid4().hex[:8])
                d.mkdir(parents=True)
                zp = d / name
                with open(zp, "wb") as f:
                    left = n
                    while left:
                        chunk = self.rfile.read(min(1 << 20, left))
                        if not chunk:
                            break
                        f.write(chunk); left -= len(chunk)
                ex = d / "mod"
                safe_extract(zp, ex)
                zp.unlink()
                return self._send(200, {"path": str(ex), **inspect(ex)})
            body = json.loads(self.rfile.read(n) or b"{}")
            if u.path == "/api/inspect":
                return self._send(200, {"path": body["path"], **inspect(body["path"])})
            if u.path == "/api/convert":
                if not body.get("path"):
                    return self._send(400, {"error": "No mod selected"})
                return self._send(200, {"job": start_job(body)})
            self._send(404, {"error": "not found"})
        except (ValueError, KeyError, zipfile.BadZipFile, OSError) as e:
            self._send(400, {"error": str(e)})


def make_server(host="127.0.0.1", port=8765):
    return ThreadingHTTPServer((host, port), Handler)


def serve(host="127.0.0.1", port=8765, open_browser=True):
    srv = make_server(host, port)
    url = f"http://{host}:{srv.server_address[1]}/"
    print(f"FNFVSlice-Converter GUI -> {url}  (Ctrl+C to stop)")
    if open_browser:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        srv.server_close()
