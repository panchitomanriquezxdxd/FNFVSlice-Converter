from __future__ import annotations

from pathlib import Path

from ..util import ci_path, copy_file, pascal, read_json, slug, write_json, num
from .base import BaseConverter
from .common import (BASE_STAGES, bpm_at, ev, make_character, make_chart, make_level,
                     make_metadata, make_stage)
from .events import map_psych_event
from .lua_stage import parse_lua_stage

SCRIPT_EXT = (".lua", ".hx")


class PsychConverter(BaseConverter):
    ENGINE = "psych"

    def run(self):
        self.convert_songs()
        self.convert_characters()
        self.convert_stages()
        self.convert_weeks()
        self.copy_assets()
        self.collect_scripts()
        self.emit_compat()
        pack = {}
        if (self.root / "pack.json").exists():
            pack = read_json(self.root / "pack.json")
        self.write_polymod(pack.get("name") or self.root.name, pack.get("description"))
        return self.script_tasks

    # ---- songs --------------------------------------------------------
    def convert_songs(self):
        data = self.root / "data"
        if not data.is_dir():
            self.r.warn("No data/ folder: no charts found.")
            return
        for sdir in sorted(d for d in data.iterdir() if d.is_dir()):
            charts = self._load_charts(sdir)
            if charts:
                self._convert_song(sdir, charts)

    def _load_charts(self, sdir):
        charts = {}
        for f in sorted(sdir.glob("*.json")):
            if f.stem.lower() == "events":
                continue
            try:
                j = read_json(f)
            except Exception as e:  # noqa: BLE001
                self.r.warn(f"{f.relative_to(self.root)}: invalid JSON ({e})")
                continue
            s = j.get("song") if isinstance(j, dict) else None
            if not isinstance(s, dict) or "notes" not in s:
                continue
            stem, base = f.stem.lower(), sdir.name.lower()
            if stem == base:
                diff = "normal"
            elif stem.startswith(base + "-"):
                diff = stem[len(base) + 1:]
            else:
                diff = stem.rsplit("-", 1)[-1] if "-" in stem else "normal"
            charts[diff] = s
        return charts

    def _extra_events(self, sdir):
        f = sdir / "events.json"
        if not f.exists():
            return []
        try:
            j = read_json(f)
            return (j.get("song") or j).get("events", [])
        except Exception as e:  # noqa: BLE001
            self.r.warn(f"events.json of {sdir.name} unreadable: {e}")
            return []

    def _convert_chart(self, s, extra_events, primary):
        cur = float(s.get("bpm", 100))
        bpms, t = [(0.0, cur)], 0.0
        notes, events, kinds, raw = [], [], set(), []
        last_focus = None
        for i, sec in enumerate(s.get("notes", [])):
            if sec.get("changeBPM") and sec.get("bpm") and float(sec["bpm"]) != cur:
                cur = float(sec["bpm"])
                if i == 0:
                    bpms[0] = (0.0, cur)
                else:
                    bpms.append((t, cur))
            must, gf = bool(sec.get("mustHitSection")), bool(sec.get("gfSection"))
            focus = 2 if gf else (0 if must else 1)
            if focus != last_focus:
                events.append(ev(t, "FocusCamera", {"char": focus, "x": 0, "y": 0}))
                last_focus = focus
            for n in sec.get("sectionNotes", []):
                if len(n) < 3:
                    continue
                nt, data = float(n[0]), int(n[1])
                if data < 0:  # legacy event stored as a note
                    raw.append((nt, str(n[2]), n[3] if len(n) > 3 else "", n[4] if len(n) > 4 else ""))
                    continue
                sus = float(n[2]) if n[2] not in (None, "") else 0.0
                kind = n[3] if len(n) > 3 else ""
                if isinstance(kind, (int, float)) and not isinstance(kind, bool):
                    kind = "" if kind == 0 else str(kind)
                kind = str(kind or "")
                is_player = (data < 4) == must
                if gf and data < 4 and not kind:
                    kind = "GF Sing"
                if sec.get("altAnim") and not kind:
                    kind = "Alt Animation"
                note = {"t": num(nt), "d": data % 4 if is_player else data % 4 + 4, "l": num(max(sus, 0)), "p": []}
                if kind:
                    note["k"] = kind
                    kinds.add(kind)
                notes.append(note)
            beats = float(sec.get("sectionBeats") or sec.get("lengthInSteps", 16) / 4)
            t += beats * 60000.0 / cur
        for item in list(s.get("events", [])) + list(extra_events):
            if not isinstance(item, list) or len(item) < 2:
                continue
            if isinstance(item[1], str):
                raw.append((float(item[0]), item[1], item[2] if len(item) > 2 else "", item[3] if len(item) > 3 else ""))
            else:
                for e in item[1]:
                    raw.append((float(item[0]), e[0], e[1] if len(e) > 1 else "", e[2] if len(e) > 2 else ""))
        stats = {}
        for rt, name, v1, v2 in raw:
            if str(name).strip() == "Change BPM":
                try:
                    bpms.append((rt, float(v1)))
                except (TypeError, ValueError):
                    pass
                continue
            out, status, cid = map_psych_event(name, v1, v2, rt, bpm_at(bpms, rt))
            events.extend(out)
            if status == "compat":
                self.compat.add(cid)
            if primary:
                stats[(status, cid, name)] = stats.get((status, cid, name), 0) + 1
        return notes, events, bpms, kinds, stats

    def _stage_id(self, name):
        name = name or "stage"
        if ci_path(self.root / "stages", name + ".json") or ci_path(self.root / "stages", name + ".lua"):
            return slug(name)
        mapped = BASE_STAGES.get(name.lower())
        if mapped:
            return mapped
        self.r.warn(f"Stage '{name}' not found in mod nor mapped to a base-game stage.")
        return slug(name)

    def _convert_song(self, sdir, charts):
        sid = slug(sdir.name)
        primary = "normal" if "normal" in charts else sorted(charts)[0]
        notes_by, speeds, events, bpms, all_kinds = {}, {}, [], None, set()
        extra = self._extra_events(sdir)
        for diff, s in charts.items():
            n, e, b, k, st = self._convert_chart(s, extra, diff == primary)
            notes_by[diff] = n
            speeds[diff] = float(s.get("speed", 1.0))
            all_kinds |= k
            if diff == primary:
                events, bpms = e, b
                for (status, cid, name), cnt in st.items():
                    if status == "custom":
                        self.r.warn(f"[{sid}] custom event '{name}' x{cnt} kept as '{cid}' (needs a script).")
                    self.r.bump(f"events_{status}", cnt)
        s0 = charts[primary]
        p1 = slug(s0.get("player1") or "bf")
        p2 = slug(s0.get("player2") or "dad")
        gfv = slug(s0.get("gfVersion") or s0.get("player3") or "gf")
        stage = self._stage_id(s0.get("stage"))
        self.stage_chars.setdefault(stage, (p1, p2, gfv))
        pv, ov = self._copy_audio(sdir, sid, p1, p2)
        diffs = sorted(charts, key=lambda d: ["easy", "normal", "hard"].index(d) if d in ("easy", "normal", "hard") else 9)
        meta = make_metadata(str(s0.get("song") or sdir.name), "", "", bpms, diffs, p1, p2, gfv, stage, pv, ov)
        write_json(self.out / "data" / "songs" / sid / f"{sid}-metadata.json", meta)
        write_json(self.out / "data" / "songs" / sid / f"{sid}-chart.json", make_chart(speeds, events, notes_by))
        self.r.ok(f"Song '{sid}': {len(diffs)} difficulties, {sum(len(v) for v in notes_by.values())} notes, "
                  f"{len(events)} events, {len(bpms)} BPM section(s).")
        self.r.bump("songs")
        if all_kinds:
            self.r.warn(f"[{sid}] note kinds kept in 'k': {sorted(all_kinds)} (need modules to behave like Psych).")
        for f in sorted(sdir.iterdir()):
            if f.suffix.lower() in SCRIPT_EXT:
                self.task(f, "song", song=sid)

    def _copy_audio(self, sdir, sid, p1, p2):
        adir = ci_path(self.root / "songs", sdir.name)
        if not adir:
            self.r.warn(f"[{sid}] no songs/{sdir.name}/ audio folder.")
            return [p1], [p2]
        dst = self.out / "songs" / sid
        inst = ci_path(adir, "Inst.ogg")
        if inst:
            copy_file(inst, dst / "Inst.ogg")
        else:
            self.r.warn(f"[{sid}] Inst.ogg missing.")
        pv, ov = [], []
        vp, vo, vc = (ci_path(adir, n) for n in ("Voices-Player.ogg", "Voices-Opponent.ogg", "Voices.ogg"))
        if vp:
            copy_file(vp, dst / f"Voices-{p1}.ogg"); pv.append(p1)
        if vo:
            copy_file(vo, dst / f"Voices-{p2}.ogg"); ov.append(p2)
        if vc and not vp:
            copy_file(vc, dst / f"Voices-{p1}.ogg"); pv.append(p1)
            self.r.warn(f"[{sid}] combined Voices.ogg assigned to player '{p1}' (V-Slice wants split vocals).")
        return pv, ov

    # ---- characters ---------------------------------------------------
    def convert_characters(self):
        cdir = self.root / "characters"
        if not cdir.is_dir():
            return
        for f in sorted(cdir.glob("*.json")):
            try:
                j = read_json(f)
            except Exception as e:  # noqa: BLE001
                self.r.warn(f"characters/{f.name}: invalid JSON ({e})")
                continue
            cid = slug(f.stem)
            anims = []
            for a in j.get("animations", []):
                idx = a.get("indices", [])
                if isinstance(idx, str):
                    idx = [int(x) for x in idx.split(",") if x.strip().lstrip("-").isdigit()]
                anims.append({"name": a["anim"], "prefix": a["name"], "fps": a.get("fps", 24),
                              "loop": a.get("loop", False), "indices": idx, "offsets": a.get("offsets", [0, 0])})
            icon = slug(j.get("healthicon") or cid)
            self.icons.add(icon)
            idle = next((a for a in anims if a["name"] in ("idle", "danceLeft")), anims[0] if anims else None)
            self.char_info[cid] = {"image": j.get("image", f"characters/{f.stem}"), "scale": float(j.get("scale", 1)),
                                   "idle_prefix": idle["prefix"] if idle else None}
            data = make_character(
                cid, j.get("image", f"characters/{f.stem}"), anims, scale=j.get("scale", 1),
                flip_x=j.get("flip_x", False), icon=icon, offsets=j.get("position", [0, 0]),
                cam=j.get("camera_position", [0, 0]), sing_time=round(float(j.get("sing_duration", 4)) * 1.1, 2))
            write_json(self.out / "data" / "characters" / f"{cid}.json", data)
            self.r.bump("characters")
            if j.get("healthbar_colors"):
                self.r.add_todo(f"Character '{cid}': V-Slice has no per-character health bar color (Psych had {j['healthbar_colors']}).")
            for ext in SCRIPT_EXT:
                if f.with_suffix(ext).exists():
                    self.task(f.with_suffix(ext), "global")
        self.r.ok(f"{self.r.stats.get('characters', 0)} characters converted (JSON -> V-Slice).")

    # ---- stages -------------------------------------------------------
    def convert_stages(self):
        sdir = self.root / "stages"
        if not sdir.is_dir():
            return
        stems = sorted({f.stem for f in sdir.iterdir() if f.suffix.lower() in (".json", ".lua", ".hx")})
        for stem in stems:
            sid = slug(stem)
            jf = ci_path(sdir, stem + ".json")
            j = read_json(jf) if jf else {}
            props, unhandled = [], set()
            lua = ci_path(sdir, stem + ".lua")
            if lua:
                props, unhandled = parse_lua_stage(lua.read_text(encoding="utf-8", errors="replace"))
                self.r.ok(f"Stage '{sid}': {len(props)} static sprites extracted from Lua (deterministic).")
                if unhandled:
                    self.task(lua, "stage", stage=sid)
                    self.r.warn(f"Stage '{sid}': Lua has dynamic logic ({', '.join(sorted(unhandled)[:8])}...) -> sent to script translator.")
            hx = ci_path(sdir, stem + ".hx")
            if hx:
                self.task(hx, "stage", stage=sid)
            bf, dad, gf = self.stage_chars.get(sid, ("bf", "dad", "gf"))
            defaults = {"boyfriend": [770, 100], "opponent": [100, 100], "girlfriend": [400, 130]}
            chars = {}
            for key, vkey, cid, camkey, z in (("boyfriend", "bf", bf, "camera_boyfriend", 300),
                                              ("opponent", "dad", dad, "camera_opponent", 200),
                                              ("girlfriend", "gf", gf, "camera_girlfriend", 100)):
                pos = j.get(key, defaults[key])
                fx, fy = self.feet_offset(cid, vkey)
                chars[vkey] = {"zIndex": z, "position": [round(pos[0] + fx), round(pos[1] + fy)],
                               "cameraOffsets": j.get(camkey, [0, 0])}
            stage = make_stage(stem.replace("-", " ").title(), j.get("defaultZoom", 0.9), chars, props)
            write_json(self.out / "data" / "stages" / f"{sid}.json", stage)
            self.r.bump("stages")
            if j.get("isPixelStage"):
                self.r.add_todo(f"Stage '{sid}' is a pixel stage: set \"isPixel\": true on its props and use a pixel noteStyle.")
            if j.get("hide_girlfriend"):
                self.r.add_todo(f"Stage '{sid}' hides GF in Psych: remove the 'gf' entry in its V-Slice JSON.")

    # ---- weeks --------------------------------------------------------
    def convert_weeks(self):
        wdir = self.root / "weeks"
        if not wdir.is_dir():
            return
        for f in sorted(wdir.glob("*.json")):
            try:
                j = read_json(f)
            except Exception as e:  # noqa: BLE001
                self.r.warn(f"weeks/{f.name}: invalid JSON ({e})")
                continue
            lid = slug(f.stem)
            songs = [slug(s[0]) for s in j.get("songs", []) if s]
            title = ci_path(self.root / "images" / "storymenu", f.stem + ".png")
            title_asset = f"storymenu/titles/{lid}"
            if title:
                copy_file(title, self.out / "images" / "storymenu" / "titles" / f"{lid}.png")
            else:
                self.r.warn(f"Week '{lid}': story title image not found.")
            props = []
            for c in j.get("weekCharacters", []):
                if not c:
                    continue
                for ext in (".png", ".xml"):
                    p = ci_path(self.root / "images" / "menucharacters", c + ext)
                    if p:
                        copy_file(p, self.out / "images" / "storymenu" / "props" / f"{slug(c)}{ext}")
                props.append({"assetPath": f"storymenu/props/{slug(c)}", "scale": 1.0, "offsets": [0, 0]})
            col = j.get("freeplayColor")
            bg = "#%02X%02X%02X" % tuple(int(x) for x in col[:3]) if col and len(col) >= 3 else "#F9CF51"
            write_json(self.out / "data" / "levels" / f"{lid}.json",
                       make_level(j.get("storyName") or j.get("weekName") or lid, songs, title_asset, props, bg))
            self.r.bump("levels")
            self.r.add_todo(f"Level '{lid}': check story-menu prop animation prefixes (idle/confirm) and offsets.")

    # ---- scripts ------------------------------------------------------
    def collect_scripts(self):
        for sub, kind in (("scripts", "global"), ("custom_events", "event"), ("custom_notetypes", "notetype")):
            d = ci_path(self.root, sub)
            if not d:
                continue
            for f in sorted(d.iterdir()):
                if f.suffix.lower() not in SCRIPT_EXT:
                    continue
                if kind == "event":
                    if pascal(f.stem) in self.compat or f.stem.lower() in ("add camera zoom", "screen shake"):
                        continue
                    self.task(f, "event", name=pascal(f.stem), title=f.stem, params="value")
                elif kind == "notetype":
                    self.task(f, "notetype", name=f.stem)
                else:
                    self.task(f, "global")
