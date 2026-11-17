from __future__ import annotations

import xml.etree.ElementTree as ET

from ..util import ci_path, copy_file, pascal, read_json, slug, write_json, num
from .base import BaseConverter
from .common import (BASE_STAGES, bpm_at, ev, make_character, make_chart, make_level,
                     make_metadata, make_stage)

SCRIPT_EXT = (".hx", ".hscript", ".hxs")


def _indices(s):
    out = []
    for part in (s or "").split(","):
        part = part.strip()
        if ".." in part:
            a, b = part.split("..", 1)
            out += list(range(int(a), int(b) + 1))
        elif part.lstrip("-").isdigit():
            out.append(int(part))
    return out


def _f(x, d=0.0):
    try:
        return float(x)
    except (TypeError, ValueError):
        return d


class CodenameConverter(BaseConverter):
    ENGINE = "codename"

    def __init__(self, *a, sustain_in_steps=True, **kw):
        super().__init__(*a, **kw)
        self.sustain_in_steps = sustain_in_steps

    def run(self):
        self.convert_songs()
        self.convert_characters()
        self.convert_stages()
        self.convert_weeks()
        self.copy_assets()
        self.collect_scripts()
        self.emit_compat()
        self.write_polymod(self.root.name, "")
        return self.script_tasks

    # ---- songs --------------------------------------------------------
    def convert_songs(self):
        songs = self.root / "songs"
        if not songs.is_dir():
            self.r.warn("No songs/ folder.")
            return
        for sdir in sorted(d for d in songs.iterdir() if d.is_dir()):
            cdir = sdir / "charts"
            if cdir.is_dir() and list(cdir.glob("*.json")):
                self._convert_song(sdir, cdir)

    def _convert_song(self, sdir, cdir):
        sid = slug(sdir.name)
        meta = read_json(sdir / "meta.json") if (sdir / "meta.json").exists() else {}
        bpm0 = float(meta.get("bpm", 100))
        charts = {f.stem.lower(): read_json(f) for f in sorted(cdir.glob("*.json"))}
        primary = "normal" if "normal" in charts else sorted(charts)[0]
        # BPM changes from primary chart
        bpms = [(0.0, bpm0)]
        for e in charts[primary].get("events", []):
            if e.get("name") == "BPM Change" and e.get("params"):
                bpms.append((float(e["time"]), float(e["params"][0])))
        notes_by, speeds, events, all_kinds = {}, {}, [], set()
        info = {}
        for diff, c in charts.items():
            sls = c.get("strumLines", [])
            types = [s.get("type", 0) for s in sls]
            nts = c.get("noteTypes", [])
            notes = []
            for sl in sls:
                typ = sl.get("type", 0)
                for n in sl.get("notes", []):
                    t = float(n["time"])
                    lane = int(n.get("id", 0)) % 4
                    tid = int(n.get("type", 0) or 0)
                    kind = nts[tid - 1] if 0 < tid <= len(nts) else ""
                    sus = _f(n.get("sLen", 0))
                    if self.sustain_in_steps:
                        sus = sus * 60000.0 / bpm_at(bpms, t) / 4
                    if typ == 2 and not kind:
                        kind = "GF Sing"
                    note = {"t": num(t), "d": lane if typ == 1 else lane + 4, "l": num(max(sus, 0)), "p": []}
                    if kind:
                        note["k"] = kind
                        all_kinds.add(kind)
                    notes.append(note)
            notes_by[diff] = notes
            speeds[diff] = float(c.get("scrollSpeed", 1.0))
            if diff == primary:
                info = {"sls": sls, "stage": c.get("stage", "stage")}
                for e in c.get("events", []):
                    events += self._map_event(e, types, sid)
        sls = info["sls"]

        def first(typ, default):
            for s in sls:
                if s.get("type") == typ and s.get("characters"):
                    return slug(s["characters"][0])
            return default
        p1, p2, gfv = first(1, "bf"), first(0, "dad"), first(2, "gf")
        if sum(1 for s in sls if s.get("type") in (0, 1)) > 2:
            self.r.warn(f"[{sid}] more than 2 playable strumlines: extra ones were merged into opponent/player lanes.")
        stage_name = info["stage"] or "stage"
        stage = slug(stage_name) if ci_path(self.root / "data" / "stages", stage_name + ".xml") \
            else BASE_STAGES.get(stage_name.lower(), slug(stage_name))
        self.stage_chars.setdefault(stage, (p1, p2, gfv))
        pv, ov = self._copy_audio(sdir, sid, sls, p1, p2)
        diffs = meta.get("difficulties") or sorted(charts)
        diffs = [d.lower() for d in diffs if d.lower() in charts] or sorted(charts)
        md = make_metadata(meta.get("displayName") or meta.get("name") or sdir.name, "", "", bpms, diffs,
                           p1, p2, gfv, stage, pv, ov)
        write_json(self.out / "data" / "songs" / sid / f"{sid}-metadata.json", md)
        write_json(self.out / "data" / "songs" / sid / f"{sid}-chart.json", make_chart(speeds, events, notes_by))
        self.r.ok(f"Song '{sid}': {len(diffs)} difficulties, {sum(len(v) for v in notes_by.values())} notes, {len(events)} events.")
        self.r.bump("songs")
        if all_kinds:
            self.r.warn(f"[{sid}] note types kept in 'k': {sorted(all_kinds)}.")
        for f in sorted((sdir / "scripts").glob("*")) if (sdir / "scripts").is_dir() else []:
            if f.suffix.lower() in SCRIPT_EXT:
                self.task(f, "song", song=sid)

    def _map_event(self, e, types, sid):
        name, p, t = e.get("name", ""), e.get("params", []) or [], float(e.get("time", 0))
        if name == "BPM Change":
            return []
        if name == "Camera Movement":
            idx = int(p[0]) if p else 0
            typ = types[idx] if 0 <= idx < len(types) else 1
            return [ev(t, "FocusCamera", {"char": {1: 0, 0: 1, 2: 2}.get(typ, 0), "x": 0, "y": 0})]
        cid = pascal(name)
        self.r.warn(f"[{sid}] event '{name}' kept as '{cid}' with param0..N (needs a script).")
        self.r.bump("events_custom")
        return [ev(t, cid, {f"param{i}": v for i, v in enumerate(p)})]

    def _copy_audio(self, sdir, sid, sls, p1, p2):
        adir = ci_path(sdir, "song")
        if not adir:
            self.r.warn(f"[{sid}] no song/ audio folder.")
            return [p1], [p2]
        dst = self.out / "songs" / sid
        inst = ci_path(adir, "Inst.ogg")
        if inst:
            copy_file(inst, dst / "Inst.ogg")
        else:
            self.r.warn(f"[{sid}] Inst.ogg missing.")
        pv, ov, used = [], [], set()
        for sl in sorted(sls, key=lambda s: s.get("type") != 1):
            typ = sl.get("type")
            if typ not in (0, 1) or not sl.get("characters"):
                continue
            char = slug(sl["characters"][0])
            f = ci_path(adir, f"Voices{sl.get('vocalsSuffix', '')}.ogg")
            if f and f not in used:
                used.add(f)
                copy_file(f, dst / f"Voices-{char}.ogg")
                (pv if typ == 1 else ov).append(char)
        return pv, ov

    # ---- characters / stages / weeks ----------------------------------
    def convert_characters(self):
        d = self.root / "data" / "characters"
        for f in sorted(d.glob("*.xml")) if d.is_dir() else []:
            try:
                r = ET.parse(f).getroot()
            except ET.ParseError as e:
                self.r.warn(f"{f.name}: invalid XML ({e})")
                continue
            cid = slug(f.stem)
            sprite = r.get("sprite", f.stem)
            asset = sprite if sprite.startswith("characters/") else "characters/" + sprite
            anims = [{"name": a.get("name"), "prefix": a.get("anim"), "fps": _f(a.get("fps"), 24),
                      "loop": a.get("loop", "false").lower() == "true", "indices": _indices(a.get("indices")),
                      "offsets": [_f(a.get("x")), _f(a.get("y"))]} for a in r.iter("anim")]
            icon = slug(r.get("icon") or cid)
            self.icons.add(icon)
            idle = next((a for a in anims if a["name"] in ("idle", "danceLeft")), anims[0] if anims else None)
            self.char_info[cid] = {"image": asset, "scale": _f(r.get("scale"), 1),
                                   "idle_prefix": idle["prefix"] if idle else None}
            write_json(self.out / "data" / "characters" / f"{cid}.json", make_character(
                cid, asset, anims, scale=_f(r.get("scale"), 1), flip_x=r.get("flipX", "false").lower() == "true",
                icon=icon, offsets=[_f(r.get("x")), _f(r.get("y"))], cam=[_f(r.get("camx")), _f(r.get("camy"))],
                sing_time=round(_f(r.get("holdTime"), 4) * 1.1, 2)))
            self.r.bump("characters")
            if f.with_suffix(".hx").exists():
                self.task(f.with_suffix(".hx"), "global")

    def convert_stages(self):
        d = self.root / "data" / "stages"
        for f in sorted(d.glob("*.xml")) if d.is_dir() else []:
            try:
                r = ET.parse(f).getroot()
            except ET.ParseError as e:
                self.r.warn(f"{f.name}: invalid XML ({e})")
                continue
            sid = slug(f.stem)
            folder = (r.get("folder") or f"stages/{f.stem}").strip("/")
            props, z = [], 10
            for sp in r.iter("sprite"):
                if sp.get("type", "").lower() in ("solid", "bg"):
                    self.r.warn(f"Stage '{sid}': sprite of type '{sp.get('type')}' skipped (no V-Slice equivalent).")
                    continue
                sc = _f(sp.get("scroll"), 1)
                p = {"zIndex": z, "position": [num(_f(sp.get("x"))), num(_f(sp.get("y")))],
                     "scale": [num(_f(sp.get("scalex") or sp.get("scale"), 1)), num(_f(sp.get("scaley") or sp.get("scale"), 1))],
                     "name": sp.get("name") or sp.get("sprite"), "assetPath": f"{folder}/{sp.get('sprite')}",
                     "isPixel": False, "scroll": [num(_f(sp.get("scrollx"), sc)), num(_f(sp.get("scrolly"), sc))],
                     "alpha": num(_f(sp.get("alpha"), 1))}
                anims = [{"name": a.get("name"), "prefix": a.get("anim"), "frameRate": num(_f(a.get("fps"), 24)),
                          "looped": a.get("loop", "true").lower() == "true"} for a in sp.iter("anim")]
                if anims:
                    p.update({"animType": "sparrow", "animations": anims, "startingAnimation": anims[0]["name"]})
                props.append(p)
                z += 1
            bf, dad, gf = self.stage_chars.get(sid, ("bf", "dad", "gf"))
            chars = {}
            for tags, vkey, cid, zi in ((("boyfriend", "bf"), "bf", bf, 300), (("dad", "opponent"), "dad", dad, 200),
                                        (("girlfriend", "gf"), "gf", gf, 100)):
                el = next((e for t in tags for e in r.iter(t)), None)
                if el is None:
                    el = next((e for e in r.iter("character") if e.get("name") in tags + ("boyfriend",) and e.get("name") in tags), None)
                x, y = (_f(el.get("x")), _f(el.get("y"))) if el is not None else (0, 0)
                fx, fy = self.feet_offset(cid, vkey)
                chars[vkey] = {"zIndex": zi, "position": [round(x + fx), round(y + fy)],
                               "cameraOffsets": [_f(el.get("camxoffset")) if el is not None else 0,
                                                 _f(el.get("camyoffset")) if el is not None else 0]}
            write_json(self.out / "data" / "stages" / f"{sid}.json",
                       make_stage(r.get("name") or f.stem, _f(r.get("zoom"), 0.9), chars, props))
            self.r.bump("stages")
            if f.with_suffix(".hx").exists():
                self.task(f.with_suffix(".hx"), "stage", stage=sid)

    def convert_weeks(self):
        d = self.root / "data" / "weeks" / "weeks"
        for f in sorted(d.glob("*.xml")) if d.is_dir() else []:
            try:
                r = ET.parse(f).getroot()
            except ET.ParseError:
                continue
            lid = slug(f.stem)
            songs = [slug(s.get("name")) for s in r.iter("song") if s.get("name")]
            write_json(self.out / "data" / "levels" / f"{lid}.json",
                       make_level(r.get("name") or lid, songs, f"storymenu/titles/{lid}", [], "#F9CF51"))
            self.r.bump("levels")
            self.r.add_todo(f"Level '{lid}': add story-menu title image and props manually.")

    def collect_scripts(self):
        for sub, kind in (("data/events", "event"), ("data/notes", "notetype"), ("data/scripts", "global")):
            d = ci_path(self.root, sub)
            for f in sorted(d.iterdir()) if d and d.is_dir() else []:
                if f.suffix.lower() in SCRIPT_EXT:
                    if kind == "event":
                        self.task(f, "event", name=pascal(f.stem), title=f.stem, params="param")
                    elif kind == "notetype":
                        self.task(f, "notetype", name=f.stem)
                    else:
                        self.task(f, "global")
        if (self.root / "data" / "states").is_dir():
            self.r.add_todo("data/states/ (menu/state scripts) has no V-Slice equivalent: port by hand.")
