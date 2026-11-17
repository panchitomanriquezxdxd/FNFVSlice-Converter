"""Conversion pipeline shared by the CLI and the GUI."""
from __future__ import annotations

from pathlib import Path

from .ai.analyzer import analyze
from .ai.client import AIClient, AIError
from .ai.script_translator import translate_all
from .converters.codename import CodenameConverter
from .converters.psych import PsychConverter
from .detect import detect_engine, find_mod_root
from .models import Report
from .util import slug, write_text

CACHE_DIR = Path.home() / ".fnfconv_cache"


def make_ai(provider="auto", model=None, base_url=None, api_key=None, log=print):
    try:
        ai = AIClient.create(provider, model, base_url, CACHE_DIR, api_key)
    except AIError as e:
        log(f"[!] AI disabled: {e}")
        return None
    log(f"[AI] {'%s (%s)' % (ai.provider, ai.model) if ai else 'offline mode (static analysis + stubs)'}")
    return ai


def resolve_root(path) -> Path:
    """Finds the real mod root (handles mods/<name>/ and zips with one wrapper folder)."""
    root = find_mod_root(path)
    if detect_engine(root)[0] == "unknown":
        subs = [d for d in root.iterdir() if d.is_dir() and not d.name.startswith("__")] if root.is_dir() else []
        if len(subs) == 1:
            return find_mod_root(subs[0])
    return root


def run_convert(mod, out, engine="auto", ai="auto", model=None, base_url=None, api_key=None, ai_review=False,
                mirror_shared=False, no_scripts=False, mod_id=None, log=print) -> Report:
    root = resolve_root(mod)
    if not root.is_dir():
        raise ValueError(f"Not a folder: {root}")
    evidence = []
    if engine == "auto":
        engine, evidence = detect_engine(root)
    if engine == "unknown":
        raise ValueError("Could not detect the engine (Psych/Codename). Choose it manually.")
    out = Path(out)
    aic = make_ai(ai, model, base_url, api_key, log)
    rep = Report(mod_name=root.name, engine=engine)
    log(f"[*] {root.name}: engine={engine} {evidence}")
    conv = (PsychConverter if engine == "psych" else CodenameConverter)(root, out, mod_id or slug(root.name),
                                                                       rep, mirror_shared=mirror_shared)
    log("[*] Converting charts, characters, stages, weeks, assets...")
    tasks = conv.run()
    log(f"[*] Analysing {len(tasks)} script(s)...")
    analyze(root, engine, tasks, aic, rep)
    if not no_scripts and tasks:
        log("[*] Translating scripts " + ("with AI..." if aic else "(offline stubs)..."))
        translate_all(tasks, aic, out, mod_id or slug(root.name), rep, review=ai_review)
    write_text(out / "_fnfconv" / "report.md", rep.to_markdown())
    write_text(out / "_fnfconv" / "report.json", rep.to_json())
    log(f"[OK] done | warnings: {len(rep.warnings)} | TODO: {len(rep.todo)}")
    return rep
