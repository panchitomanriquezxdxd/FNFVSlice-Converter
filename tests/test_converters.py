import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fnfconv.cli import main  # noqa: E402
from fnfconv.converters.lua_stage import parse_lua_stage  # noqa: E402
from fnfconv.detect import detect_engine  # noqa: E402
from tests.fixtures import codename_mod, psych_mod  # noqa: E402


def J(p): return json.loads(Path(p).read_text(encoding="utf-8"))


class T(unittest.TestCase):
    def run_conv(self, builder):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        src, out = Path(self.tmp.name) / "mod", Path(self.tmp.name) / "out"
        builder(src)
        main(["convert", str(src), "-o", str(out), "--ai", "none"])
        return src, out

    def test_psych(self):
        src, out = self.run_conv(psych_mod)
        self.assertEqual(detect_engine(src)[0], "psych")
        ch = J(out / "data/songs/test-song/test-song-chart.json")
        notes = ch["notes"]["normal"]
        # section 1 mustHit: data 0 -> player lane 0 ; data 5 -> opponent lane 5
        self.assertEqual([(n["d"], n.get("k")) for n in notes[:2]], [(0, None), (5, "Hurt Note")])
        # section 2 not mustHit: data 1 -> opponent (5), data 6 -> player (2)
        self.assertEqual([n["d"] for n in notes[2:]], [5, 2])
        self.assertEqual(ch["scrollSpeed"]["hard"], 3)
        names = [e["e"] for e in ch["events"]]
        for n in ("FocusCamera", "AddCameraZoom", "ScreenShake", "WeirdThing"):
            self.assertIn(n, names)
        md = J(out / "data/songs/test-song/test-song-metadata.json")
        self.assertEqual(md["playData"]["stage"], "mystage")
        tc = md["timeChanges"]
        self.assertEqual(len(tc), 2); self.assertEqual(tc[1]["t"], 2400); self.assertEqual(tc[1]["bpm"], 200)
        self.assertEqual(md["playData"]["characters"]["playerVocals"], ["bf"])
        st = J(out / "data/stages/mystage.json")
        self.assertEqual(len(st["props"]), 2); self.assertGreater(st["props"][1]["zIndex"], 300)
        self.assertEqual(st["characters"]["bf"]["position"], [770 + 55, 100 + 210])  # frameWidth/2, frameHeight
        self.assertEqual(J(out / "data/levels/week1.json")["songs"], ["test-song"])
        self.assertTrue((out / "songs/test-song/Voices-bf.ogg").exists())
        self.assertTrue((out / "images/icons/bficon.png").exists())
        self.assertTrue((out / "scripts/mod/events/ScreenShakeEvent.hxc").exists())
        self.assertTrue((out / "scripts/mod/song/ScriptSong.hxc").exists())
        self.assertTrue((out / "scripts/mod/event/ZoomPulseEvent.hxc").exists())
        self.assertTrue((out / "_polymod_meta.json").exists())

    def test_codename(self):
        src, out = self.run_conv(codename_mod)
        self.assertEqual(detect_engine(src)[0], "codename")
        ch = J(out / "data/songs/cn-song/cn-song-chart.json")
        n = ch["notes"]["normal"]
        self.assertEqual([(x["d"], x.get("k")) for x in n], [(5, None), (2, "Alt Anim")])
        self.assertEqual(n[1]["l"], 500)  # 4 steps @120bpm = 500ms
        self.assertEqual([e["v"]["char"] for e in ch["events"] if e["e"] == "FocusCamera"], [0, 1])  # strumline1=player->0, strumline0=dad->1
        self.assertIn("MyEvent", [e["e"] for e in ch["events"]])
        md = J(out / "data/songs/cn-song/cn-song-metadata.json")
        self.assertEqual(md["timeChanges"][1]["bpm"], 240)
        c = J(out / "data/characters/bf.json")
        self.assertEqual(c["animations"][0]["frameIndices"], [0, 1, 2, 5])
        self.assertEqual(J(out / "data/stages/cnstage.json")["props"][0]["scroll"], [0.5, 0.5])

    def test_lua_parser(self):
        props, un = parse_lua_stage("makeAnimatedLuaSprite('a','img',1,2)\naddAnimationByPrefix('a','idle','p',24,true)\naddLuaSprite('a',false)\nrunTimer('x',1)")
        self.assertEqual(props[0]["startingAnimation"], "idle"); self.assertIn("runTimer", un)


if __name__ == "__main__":
    unittest.main()
