import io
import json
import shutil
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fnfconv import gui  # noqa: E402
from fnfconv.gui import check_base_url, cleanup_expired, make_server, safe_extract  # noqa: E402
from tests.fixtures import psych_mod  # noqa: E402

H = {"X-FNFCONV": "1"}


class T(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv = make_server("127.0.0.1", 0)
        cls.base = f"http://127.0.0.1:{cls.srv.server_address[1]}"
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown(); cls.srv.server_close()

    def req(self, path, data=None, headers=H, method=None):
        r = urllib.request.Request(self.base + path, data=data, headers=headers, method=method or ("POST" if data is not None else "GET"))
        with urllib.request.urlopen(r) as resp:
            return resp.status, resp.read(), resp.headers

    def test_full_flow(self):
        st, body, h = self.req("/", headers={})
        self.assertIn(b"FNFVSlice-Converter", body)
        tmp = Path(tempfile.mkdtemp()); self.addCleanup(shutil.rmtree, tmp, True)
        psych_mod(tmp / "MyMod")
        zp = tmp / "m.zip"
        with zipfile.ZipFile(zp, "w") as z:  # wrapped in a single folder, as users usually zip it
            for f in (tmp / "MyMod").rglob("*"):
                if f.is_file():
                    z.write(f, "MyMod/" + f.relative_to(tmp / "MyMod").as_posix())
        _, b, _ = self.req("/api/upload?name=m.zip", zp.read_bytes(), {**H, "Content-Type": "application/octet-stream"})
        info = json.loads(b)
        self.assertEqual(info["engine"], "psych")
        _, b, _ = self.req("/api/convert", json.dumps({"path": info["path"], "ai": "none"}).encode(), {**H, "Content-Type": "application/json"})
        job = json.loads(b)["job"]
        for _ in range(100):
            j = json.loads(self.req(f"/api/status?job={job}", headers={})[1])
            if j["state"] != "running":
                break
            time.sleep(0.1)
        self.assertEqual(j["state"], "done", j)
        self.assertEqual(j["stats"]["songs"], 1)
        _, zbytes, _ = self.req(f"/api/download?job={job}", headers={})
        names = zipfile.ZipFile(io.BytesIO(zbytes)).namelist()
        self.assertIn("data/songs/test-song/test-song-chart.json", names)
        self.assertIn("_polymod_meta.json", names)

    def test_security(self):
        with self.assertRaises(urllib.error.HTTPError) as c:  # no custom header -> blocked (CSRF)
            self.req("/api/inspect", b"{}", {"Content-Type": "application/json"})
        self.assertEqual(c.exception.code, 403)
        with self.assertRaises(urllib.error.HTTPError) as c:  # foreign Host header -> blocked (DNS rebinding)
            self.req("/", headers={"Host": "evil.example.com"})
        self.assertEqual(c.exception.code, 403)

    def test_zip_slip(self):
        tmp = Path(tempfile.mkdtemp()); self.addCleanup(shutil.rmtree, tmp, True)
        zp = tmp / "bad.zip"
        with zipfile.ZipFile(zp, "w") as z:
            z.writestr("../evil.txt", "x")
        with self.assertRaises(ValueError):
            safe_extract(zp, tmp / "d")


class WebMode(unittest.TestCase):
    """Hosted mode: what must differ from the local GUI."""

    @classmethod
    def setUpClass(cls):
        cls.srv = make_server("127.0.0.1", 0, web=True)
        cls.base = f"http://127.0.0.1:{cls.srv.server_address[1]}"
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown(); cls.srv.server_close()

    def req(self, path, data=None, headers=H, method=None):
        r = urllib.request.Request(self.base + path, data=data, headers=headers, method=method or ("POST" if data is not None else "GET"))
        with urllib.request.urlopen(r) as resp:
            return resp.status, resp.read(), resp.headers

    def post_json(self, path, obj):
        return self.req(path, json.dumps(obj).encode(), {**H, "Content-Type": "application/json"})

    def upload(self, root, name="m.zip"):
        tmp = Path(tempfile.mkdtemp()); self.addCleanup(shutil.rmtree, tmp, True)
        psych_mod(tmp / "MyMod")
        zp = tmp / name
        with zipfile.ZipFile(zp, "w") as z:
            for f in (tmp / "MyMod").rglob("*"):
                if f.is_file():
                    z.write(f, f.relative_to(tmp / "MyMod").as_posix())
        return self.req(f"/api/upload?name={name}", zp.read_bytes(), {**H, "Content-Type": "application/octet-stream"})

    def test_public_host_and_config(self):
        _, body, h = self.req("/", headers={"Host": "mi-app.onrender.com"})  # would be 403 in local mode
        self.assertIn(b"FNFVSlice-Converter", body)
        self.assertIn("frame-ancestors 'none'", h["Content-Security-Policy"])
        cfg = json.loads(self.req("/api/config", headers={"Host": "mi-app.onrender.com"})[1])
        self.assertTrue(cfg["web"])
        self.assertEqual(json.loads(self.req("/healthz", headers={})[1]), {"ok": True})

    def test_local_server_reports_local(self):
        srv = make_server("127.0.0.1", 0)
        self.addCleanup(srv.server_close)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        self.addCleanup(srv.shutdown)
        r = urllib.request.urlopen(f"http://127.0.0.1:{srv.server_address[1]}/api/config")
        self.assertFalse(json.loads(r.read())["web"])

    def test_upload_convert_download_and_hides_server_paths(self):
        _, b, _ = self.upload("MyMod")
        info = json.loads(b)
        self.assertEqual(info["engine"], "psych")
        self.assertEqual(info["root"], "mod")  # not an absolute server path
        # mod_id is sanitized, save_to is ignored, result always goes to the job's own folder
        evil = str(Path(tempfile.gettempdir()) / "fnfconv_should_not_exist")
        _, b, _ = self.post_json("/api/convert", {"path": info["path"], "ai": "none", "mod_id": "../../x y", "save_to": evil})
        job = json.loads(b)["job"]
        for _ in range(100):
            j = json.loads(self.req(f"/api/status?job={job}", headers={})[1])
            if j["state"] != "running":
                break
            time.sleep(0.1)
        self.assertEqual(j["state"], "done", j)
        self.assertNotIn("src", j)
        self.assertFalse(Path(evil).exists())
        names = zipfile.ZipFile(io.BytesIO(self.req(f"/api/download?job={job}", headers={})[1])).namelist()
        self.assertIn("data/songs/test-song/test-song-chart.json", names)
        self.assertTrue(all(".." not in n for n in names))
        self.assertTrue(any(n.startswith("scripts/x-y/") for n in names), names)

    def test_rejects_paths_outside_uploads(self):
        for ep, body in (("/api/inspect", {"path": "/etc"}), ("/api/convert", {"path": "/etc", "ai": "none"})):
            with self.assertRaises(urllib.error.HTTPError) as c:
                self.post_json(ep, body)
            self.assertEqual(c.exception.code, 400)

    def test_ssrf_blocked(self):
        _, b, _ = self.upload("MyMod")
        path = json.loads(b)["path"]
        for url in ("http://8.8.8.8/v1", "https://127.0.0.1/v1", "https://10.0.0.5/v1", "https://169.254.169.254/latest", "https://[::1]/v1"):
            with self.assertRaises(urllib.error.HTTPError, msg=url) as c:
                self.post_json("/api/convert", {"path": path, "ai": "openai", "model": "x", "base_url": url})
            self.assertEqual(c.exception.code, 400)
        check_base_url("https://8.8.8.8/v1")  # public https literal is fine

    def test_upload_limit_and_zip_bomb(self):
        old = self.srv.max_upload
        self.srv.max_upload = 10
        self.addCleanup(setattr, self.srv, "max_upload", old)
        with self.assertRaises(urllib.error.HTTPError) as c:
            self.upload("MyMod")
        self.assertEqual(c.exception.code, 413)
        tmp = Path(tempfile.mkdtemp()); self.addCleanup(shutil.rmtree, tmp, True)
        zp = tmp / "big.zip"
        with zipfile.ZipFile(zp, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("a.bin", b"0" * 5000)
        with self.assertRaises(ValueError):
            safe_extract(zp, tmp / "d", max_bytes=1000)
        with self.assertRaises(ValueError):
            safe_extract(zp, tmp / "d2", max_files=0)

    def test_busy_and_cleanup(self):
        _, b, _ = self.upload("MyMod")
        path = json.loads(b)["path"]
        gui.JOBS["fake"] = {"state": "running", "log": [], "out": "", "error": None, "src": "x", "created": time.time()}
        self.addCleanup(gui.JOBS.pop, "fake", None)
        self.srv.max_jobs = 1
        self.addCleanup(setattr, self.srv, "max_jobs", gui.WEB_MAX_JOBS)
        with self.assertRaises(urllib.error.HTTPError) as c:
            self.post_json("/api/convert", {"path": path, "ai": "none"})
        self.assertEqual(c.exception.code, 429)
        gui.JOBS.pop("fake")
        up = Path(path).parent
        self.assertTrue(up.is_dir())
        cleanup_expired(0)
        self.assertFalse(up.exists())  # expired upload removed


if __name__ == "__main__":
    unittest.main()
