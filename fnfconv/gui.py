"""Web GUI (stdlib only).

Two modes:

* local (default): binds to 127.0.0.1, accepts folder paths from this machine and "save to folder".
* web (``--web``, any non-loopback bind, or ``$PORT`` set): meant for hosting on a server. Folder paths and
  ``save_to`` are disabled (only uploaded .zip files are processed), uploads/results expire automatically,
  upload/unzip/concurrency limits apply and a custom AI ``base_url`` must be a public https endpoint.

POST endpoints always require a custom header (anti-CSRF).
"""
from __future__ import annotations

import io
import ipaddress
import json
import os
import shutil
import socket
import tempfile
import threading
import time
import traceback
import uuid
import webbrowser
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .core import resolve_root, run_convert
from .detect import detect_engine
from .util import slug


def _work_dir() -> Path:
    base = os.environ.get("FNFCONV_WORK")
    if base:
        Path(base).mkdir(parents=True, exist_ok=True)
    return Path(tempfile.mkdtemp(prefix="fnfconv_gui_", dir=base or None))


WORK = _work_dir()
JOBS: dict[str, dict] = {}
HTML = Path(__file__).parent / "gui_static" / "index.html"

MAX_UPLOAD = 4 * 1024 ** 3                                                              # local mode
WEB_MAX_UPLOAD = int(os.environ.get("FNFCONV_MAX_UPLOAD_MB", "512")) * 1024 ** 2         # web mode
WEB_MAX_UNZIPPED = int(os.environ.get("FNFCONV_MAX_UNZIPPED_MB", "2048")) * 1024 ** 2    # zip-bomb guard
WEB_MAX_FILES = int(os.environ.get("FNFCONV_MAX_FILES", "50000"))
WEB_MAX_JOBS = int(os.environ.get("FNFCONV_MAX_JOBS", "2"))                              # simultaneous conversions
WEB_TTL = int(os.environ.get("FNFCONV_TTL_MIN", "60")) * 60                              # uploads/results lifetime


def safe_extract(zpath, dest, max_bytes=None, max_files=None):
    dest = Path(dest).resolve()
    with zipfile.ZipFile(zpath) as z:
        infos = z.infolist()
        if max_files is not None and len(infos) > max_files:
            raise ValueError(f"zip has too many files (max {max_files})")
        if max_bytes is not None and sum(m.file_size for m in infos) > max_bytes:
            raise ValueError(f"zip is too large once extracted (max {max_bytes // 1024 ** 2} MB)")
        for m in infos:
            target = (dest / m.filename).resolve()
            if dest != target and dest not in target.parents:
                raise ValueError(f"unsafe path in zip: {m.filename}")
        z.extractall(dest)


def inside_work(path) -> bool:
    try:
        Path(path).resolve().relative_to(WORK.resolve())
        return True
    except (ValueError, OSError):
        return False


def check_base_url(url):
    """Web mode: the server itself calls this URL, so only public https endpoints are allowed (anti-SSRF)."""
    p = urlparse(url)
    if p.scheme != "https" or not p.hostname:
        raise ValueError("Custom AI URL must be a public https:// address")
    try:
        infos = socket.getaddrinfo(p.hostname, p.port or 443, proto=socket.IPPROTO_TCP)
    except socket.gaierror:
        raise ValueError("Custom AI URL: host not found")
    for info in infos:
        if not ipaddress.ip_address(info[4][0].split("%")[0]).is_global:
            raise ValueError("Custom AI URL must point to a public address (localhost/private networks are blocked on a hosted server)")


def inspect(path, web=False):
    root = resolve_root(path)
    if not root.is_dir():
        raise ValueError("Not a folder" if web else f"Not a folder: {path}")
    engine, ev = detect_engine(root)
    files = [p for p in root.rglob("*") if p.is_file()]
    return {"root": root.name if web else str(root), "engine": engine, "evidence": ev, "files": len(files),
            "scripts": sum(1 for p in files if p.suffix.lower() in (".lua", ".hx", ".hscript"))}


def start_job(o, web=False, max_jobs=0):
    if web:
        if not inside_work(o["path"]):
            raise ValueError("Only mods uploaded to this server can be converted")
        if o.get("base_url"):
            check_base_url(o["base_url"])
        if max_jobs and sum(1 for j in JOBS.values() if j["state"] == "running") >= max_jobs:
            raise BusyError("Server is busy converting other mods. Try again in a minute.")
    jid = uuid.uuid4().hex
    out = WORK / jid / "out" if web else Path(o.get("save_to") or WORK / jid / "out")
    mod_id = slug(o["mod_id"]) if o.get("mod_id") else None  # becomes a folder name -> never trust it raw
    job = {"state": "running", "log": [], "out": str(out), "error": None, "src": str(o["path"]), "created": time.time()}
    JOBS[jid] = job

    def work():
        try:
            rep = run_convert(o["path"], out, o.get("engine", "auto"), o.get("ai", "auto"), o.get("model") or None,
                              o.get("base_url") or None, o.get("api_key") or None, bool(o.get("ai_review")),
                              bool(o.get("mirror_shared")), bool(o.get("no_scripts")), mod_id,
                              log=lambda m: job["log"].append(str(m)))
            job.update(report=rep.to_markdown(), stats=rep.stats, warnings=len(rep.warnings), todo=len(rep.todo),
                       engine=rep.engine, state="done")
        except Exception as e:  # noqa: BLE001
            job["log"].append(str(e) if web else traceback.format_exc())
            job.update(state="error", error=str(e))
        finally:
            job["finished"] = time.time()

    threading.Thread(target=work, daemon=True).start()
    return jid


class BusyError(Exception):
    pass


def cleanup_expired(ttl):
    """Deletes finished jobs and uploads older than `ttl` seconds (web mode)."""
    now = time.time()
    running = [j["src"] for j in JOBS.values() if j["state"] == "running"]
    for jid, j in list(JOBS.items()):
        if j["state"] != "running" and now - j.get("finished", j["created"]) >= ttl:
            JOBS.pop(jid, None)
            shutil.rmtree(WORK / jid, ignore_errors=True)
    for d in list(WORK.glob("up_*")):
        try:
            old = now - d.stat().st_mtime >= ttl
        except OSError:
            continue
        if old and not any(s.startswith(str(d)) for s in running):
            shutil.rmtree(d, ignore_errors=True)


def _janitor(ttl):
    while True:
        time.sleep(60)
        try:
            cleanup_expired(ttl)
        except Exception:  # noqa: BLE001
            pass


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
        self.send_header("X-Content-Type-Options", "nosniff")
        if ctype.startswith("text/html"):
            self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'unsafe-inline'; "
                             "style-src 'unsafe-inline'; frame-ancestors 'none'; base-uri 'none'")
            self.send_header("X-Frame-Options", "DENY")
        else:
            self.send_header("Cache-Control", "no-store")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _guard(self, post=False):
        if not self.server.web:  # local mode: block DNS-rebinding by only answering to loopback host names
            host = (self.headers.get("Host") or "").rsplit(":", 1)[0].strip("[]")
            if host not in ("127.0.0.1", "localhost", "::1"):
                self._send(403, {"error": "forbidden host"}); return False
        if post and self.headers.get("X-FNFCONV") != "1":
            self._send(403, {"error": "missing header"}); return False
        return True

    def do_GET(self):
        u = urlparse(self.path)
        if u.path == "/healthz":
            return self._send(200, {"ok": True})
        if not self._guard():
            return
        q = parse_qs(u.query)
        job = JOBS.get((q.get("job") or [""])[0])
        if u.path == "/":
            return self._send(200, HTML.read_bytes(), "text/html; charset=utf-8")
        if u.path == "/api/config":
            return self._send(200, {"web": self.server.web, "max_upload": self.server.max_upload,
                                    "ttl_min": WEB_TTL // 60 if self.server.web else 0})
        if u.path == "/api/status" and job:
            return self._send(200, {k: v for k, v in job.items() if k not in ("out", "src")} | {"log": job["log"][-400:]})
        if u.path == "/api/download" and job and job["state"] == "done":
            buf, out = io.BytesIO(), Path(job["out"])
            with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
                for f in sorted(out.rglob("*")):
                    if f.is_file():
                        z.write(f, f.relative_to(out).as_posix())
            return self._send(200, buf.getvalue(), "application/zip",
                              {"Content-Disposition": 'attachment; filename="vslice-mod.zip"'})
        self._send(404, {"error": "not found or expired"})

    def do_POST(self):
        if not self._guard(post=True):
            return
        web = self.server.web
        u = urlparse(self.path)
        try:
            n = int(self.headers.get("Content-Length") or 0)
            if u.path == "/api/upload":
                if n <= 0:
                    return self._send(400, {"error": "empty upload"})
                if n > self.server.max_upload:
                    self.close_connection = True
                    return self._send(413, {"error": f"File too large (max {self.server.max_upload // 1024 ** 2} MB)"})
                name = Path((parse_qs(u.query).get("name") or ["mod.zip"])[0]).name
                if not name.lower().endswith(".zip"):
                    return self._send(400, {"error": "Please upload the mod as a .zip"})
                d = WORK / ("up_" + uuid.uuid4().hex)
                d.mkdir(parents=True)
                try:
                    zp = d / "mod.zip"
                    with open(zp, "wb") as f:
                        left = n
                        while left:
                            chunk = self.rfile.read(min(1 << 20, left))
                            if not chunk:
                                break
                            f.write(chunk); left -= len(chunk)
                    ex = d / "mod"
                    safe_extract(zp, ex, WEB_MAX_UNZIPPED if web else None, WEB_MAX_FILES if web else None)
                    zp.unlink()
                    return self._send(200, {"path": str(ex), **inspect(ex, web)})
                except BaseException:
                    shutil.rmtree(d, ignore_errors=True)
                    raise
            body = json.loads(self.rfile.read(n) or b"{}")
            if u.path == "/api/inspect":
                if web and not inside_work(body["path"]):
                    raise ValueError("Only mods uploaded to this server can be inspected")
                return self._send(200, {"path": body["path"], **inspect(body["path"], web)})
            if u.path == "/api/convert":
                if not body.get("path"):
                    return self._send(400, {"error": "No mod selected"})
                return self._send(200, {"job": start_job(body, web, self.server.max_jobs)})
            self._send(404, {"error": "not found"})
        except BusyError as e:
            self._send(429, {"error": str(e)})
        except (ValueError, KeyError, zipfile.BadZipFile, OSError) as e:
            self._send(400, {"error": str(e) if not web or isinstance(e, ValueError) else "Bad request"})


class Server(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, addr, web=False):
        super().__init__(addr, Handler)
        self.web = web
        self.max_upload = WEB_MAX_UPLOAD if web else MAX_UPLOAD
        self.max_jobs = WEB_MAX_JOBS if web else 0


def make_server(host="127.0.0.1", port=8765, web=False):
    return Server((host, port), web)


def is_loopback(host) -> bool:
    return host in ("127.0.0.1", "localhost", "::1")


def serve(host="127.0.0.1", port=8765, open_browser=True, web=False):
    web = web or not is_loopback(host)  # binding to a public interface always means web mode (safe defaults)
    srv = make_server(host, port, web)
    shown = "localhost" if host in ("0.0.0.0", "::") else host
    url = f"http://{shown}:{srv.server_address[1]}/"
    print(f"FNFVSlice-Converter GUI ({'web' if web else 'local'} mode) -> {url}  (Ctrl+C to stop)", flush=True)
    if web:
        threading.Thread(target=_janitor, args=(WEB_TTL,), daemon=True).start()
    elif open_browser:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        srv.server_close()
