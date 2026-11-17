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
from fnfconv.gui import make_server, safe_extract  # noqa: E402
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


if __name__ == "__main__":
    unittest.main()
