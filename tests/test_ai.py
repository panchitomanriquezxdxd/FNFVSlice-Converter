import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fnfconv.ai.client import AIError  # noqa: E402
from fnfconv.ai.script_translator import translate_all, strip_fences  # noqa: E402
from fnfconv.models import Report  # noqa: E402

GOOD = "```haxe\nclass X extends Module {\n  public function new() { super('x', 1); }\n}\n```"


class Fake:
    def __init__(self, reply): self.reply, self.prompts = reply, []
    def complete(self, system, user, max_tokens=0):
        self.prompts.append(user)
        if isinstance(self.reply, Exception): raise self.reply
        return self.reply


class T(unittest.TestCase):
    def run_kinds(self, ai):
        tmp = Path(tempfile.mkdtemp())
        files = {}
        for k in ("song", "stage", "event", "notetype", "global"):
            f = tmp / f"{k}.lua"; f.write_text("function onCreate() end"); files[k] = f
        tasks = [{"path": files["song"], "kind": "song", "song": "s1"}, {"path": files["stage"], "kind": "stage", "stage": "st"},
                 {"path": files["event"], "kind": "event", "name": "Ev", "title": "Ev", "params": "value"},
                 {"path": files["notetype"], "kind": "notetype", "name": "Hurt"}, {"path": files["global"], "kind": "global"}]
        rep = Report()
        translate_all(tasks, ai, tmp / "out", "m", rep)
        return tmp, rep

    def test_ai_ok(self):
        ai = Fake(GOOD)
        tmp, rep = self.run_kinds(ai)
        self.assertEqual(rep.stats["scripts_AI"], 5)
        self.assertIn("currentSong.id == 's1'", ai.prompts[0])
        self.assertTrue(next((tmp / "out/scripts/m/song").glob("*.hxc")).read_text().startswith("// Auto-generated"))

    def test_ai_failure_falls_back(self):
        for reply in (AIError("boom"), "not code at all"):
            _, rep = self.run_kinds(Fake(reply))
            self.assertEqual(rep.stats["scripts_stub"], 5)

    def test_fences(self):
        self.assertTrue(strip_fences(GOOD).startswith("class X"))


if __name__ == "__main__":
    unittest.main()
