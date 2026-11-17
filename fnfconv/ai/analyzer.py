"""Static scan (always) + optional LLM analysis of a mod's structure and scripts."""
from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

from .client import AIError
from .prompts import SYSTEM_ANALYST, analyst_prompt

RISKS = {
    "shader": r"initLuaShader|setSpriteShader|FlxRuntimeShader|setShaders|CustomShader",
    "video": r"startVideo|VideoSprite|MP4Handler|FlxVideo",
    "inline_haxe": r"runHaxeCode|runHaxeFunction|addHaxeLibrary",
    "character_change": r"changeCharacter|addCharacterToList|Change Character",
    "custom_text/ui": r"makeLuaText|FlxText",
    "state_switch": r"switchState|FlxG\.switchState|loadSong\(",
}
FUNC_RE = re.compile(r"function\s+(\w+)\s*\(")
CALL_RE = re.compile(r"\b([A-Za-z_]\w*)\s*\(")
SKIP = {"function", "if", "for", "while", "return", "elseif", "switch", "catch"}


def scan_script(path: Path):
    text = path.read_text(encoding="utf-8", errors="replace")
    calls = Counter(c for c in CALL_RE.findall(text) if c not in SKIP)
    return {"file": path.name, "lines": text.count("\n") + 1,
            "callbacks": sorted(set(FUNC_RE.findall(text)))[:20],
            "top_calls": [c for c, _ in calls.most_common(12)],
            "risks": [k for k, rx in RISKS.items() if re.search(rx, text)]}


def build_inventory(root: Path, engine, tasks):
    counts = Counter(p.suffix.lower() for p in root.rglob("*") if p.is_file())
    scripts = [{**scan_script(t["path"]), "kind": t["kind"], "rel": str(t["path"].relative_to(root))}
               for t in tasks if Path(t["path"]).exists()]
    return {"engine_guess": engine, "file_types": dict(counts.most_common(15)),
            "top_dirs": sorted(d.name for d in root.iterdir() if d.is_dir())[:30], "scripts": scripts[:80]}


def analyze(root, engine, tasks, ai, report):
    inv = build_inventory(Path(root), engine, tasks)
    static_risks = sorted({r for s in inv["scripts"] for r in s["risks"]})
    report.analysis = {"summary": f"{len(inv['scripts'])} scripts found. Static risk flags: {static_risks or 'none'}.",
                       "risks": [f"{r}: no direct V-Slice equivalent" for r in static_risks], "inventory": inv}
    if ai is None:
        return report.analysis
    try:
        raw = ai.complete(SYSTEM_ANALYST, analyst_prompt(json.dumps(inv, indent=1)[:40000]), max_tokens=3000)
        j = json.loads(raw[raw.find("{"): raw.rfind("}") + 1])
        report.analysis.update({k: j[k] for k in ("summary", "risks", "unsupported_features", "script_plan") if k in j})
        report.analysis["risks"] = list(dict.fromkeys(report.analysis.get("risks", []) +
                                                      [f"{r}: no direct V-Slice equivalent" for r in static_risks]))
        if engine == "unknown" and j.get("engine") in ("psych", "codename"):
            report.ai(f"AI guessed engine: {j['engine']}")
    except (AIError, ValueError) as e:
        report.ai(f"AI analysis skipped: {e}")
    return report.analysis
