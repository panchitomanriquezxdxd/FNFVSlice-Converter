from __future__ import annotations

from pathlib import Path

from ..models import Report
from ..util import copy_file, copy_tree, ci_path, write_json, write_text
from .templates import COMPAT


class BaseConverter:
    ENGINE = ""

    def __init__(self, root, out, mod_id, report: Report, mirror_shared=False):
        self.root, self.out, self.mod_id, self.r = Path(root), Path(out), mod_id, report
        self.mirror_shared = mirror_shared
        self.script_tasks: list[dict] = []
        self.compat: set[str] = set()
        self.icons: set[str] = set()
        self.char_info: dict[str, dict] = {}
        self.stage_chars: dict[str, tuple] = {}
        self._warned_est = set()

    # ---- shared steps -------------------------------------------------
    def task(self, path, kind, **kw):
        self.script_tasks.append({"path": Path(path), "kind": kind, **kw})

    def feet_offset(self, cid, role):
        from .common import sprite_frame_size, FEET_ESTIMATE
        info = self.char_info.get(cid)
        if info:
            wh = sprite_frame_size(self.root / "images", info["image"], info.get("idle_prefix"))
            if wh:
                return wh[0] * info["scale"] / 2, wh[1] * info["scale"]
            self.r.warn(f"Could not measure sprite of '{cid}' (missing .xml); stage position estimated.")
        elif cid not in self._warned_est:
            self._warned_est.add(cid)
            self.r.warn(f"Character '{cid}' is not in the mod (base game?): stage position estimated for role '{role}'.")
        return FEET_ESTIMATE[role]

    def copy_assets(self):
        for sub in ("images", "sounds", "music", "videos", "fonts"):
            src = ci_path(self.root, sub)
            if src and src.is_dir():
                n = copy_tree(src, self.out / sub)
                self.r.bump(f"files_{sub}", n)
        src = ci_path(self.root, "shaders")
        if src and src.is_dir():
            copy_tree(src, self.out / "_fnfconv" / "unported" / "shaders")
            self.r.add_todo("Shaders found: V-Slice does not load Psych/Codename shaders. Copied to _fnfconv/unported/shaders for manual porting.")
        for icon in sorted(self.icons):
            for cand in (f"icons/icon-{icon}.png", f"icons/{icon}.png"):
                p = ci_path(self.root / "images", cand)
                if p:
                    copy_file(p, self.out / "images" / "icons" / f"{icon}icon.png")
                    copy_file(p, self.out / "images" / "icons" / f"icon-{icon}.png")
                    break
            else:
                self.r.warn(f"Health icon for '{icon}' not found in mod (assuming base game).")
        if self.mirror_shared and (self.out / "images").is_dir():
            copy_tree(self.out / "images", self.out / "shared" / "images")
            self.r.ok("Mirrored images/ into shared/images/ (--mirror-shared).")

    def emit_compat(self):
        for cid in sorted(self.compat):
            write_text(self.out / "scripts" / self.mod_id / "events" / f"{cid}Event.hxc", COMPAT[cid])
            self.r.ok(f"Generated compatibility event script: {cid} (no AI needed)")

    def write_polymod(self, title, description):
        write_json(self.out / "_polymod_meta.json", {
            "title": title, "description": description or "",
            "contributors": [{"name": "Unknown"}], "api_version": "0.1.0",
            "mod_version": "1.0.0", "license": "All-Rights-Reserved"})
        for icon in ("pack.png", "_polymod_icon.png"):
            p = ci_path(self.root, icon)
            if p:
                copy_file(p, self.out / "_polymod_icon.png")
                break
