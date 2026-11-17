from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__
from .ai.analyzer import analyze
from .converters.codename import CodenameConverter
from .converters.psych import PsychConverter
from .core import make_ai, resolve_root, run_convert
from .detect import detect_engine
from .models import Report
from .util import slug


def convert(a):
    try:
        rep = run_convert(a.mod, a.out, a.engine, a.ai, a.model, a.base_url, None, a.ai_review,
                          a.mirror_shared, a.no_scripts, a.mod_id)
    except ValueError as e:
        sys.exit(str(e))
    print(f"report: {Path(a.out) / '_fnfconv' / 'report.md'}")
    return rep


def analyze_cmd(a):
    root = resolve_root(a.mod)
    engine = detect_engine(root)[0] if a.engine == "auto" else a.engine
    ai = make_ai(a.ai, a.model, a.base_url)
    rep = Report(mod_name=root.name, engine=engine)
    if engine != "unknown":
        conv = (PsychConverter if engine == "psych" else CodenameConverter)(root, Path("."), slug(root.name), rep)
        conv.collect_scripts()
        # song/stage scripts live next to charts; scan them without writing anything
        for d in (root / "data").glob("*/") if (root / "data").is_dir() else []:
            conv.script_tasks += [{"path": f, "kind": "song"} for f in d.glob("*") if f.suffix in (".lua", ".hx")]
        analyze(root, engine, conv.script_tasks, ai, rep)
    print(rep.to_markdown())


def gui_cmd(a):
    from .gui import serve
    serve(a.host, a.port, not a.no_browser)


def main(argv=None):
    p = argparse.ArgumentParser(prog="fnfconv", description="Psych/Codename -> V-Slice mod converter with AI-assisted script analysis")
    p.add_argument("--version", action="version", version=__version__)
    sub = p.add_subparsers(dest="cmd", required=True)
    for name in ("convert", "analyze"):
        s = sub.add_parser(name)
        s.add_argument("mod", help="mod folder (or a folder containing mods/<mod>)")
        s.add_argument("--engine", choices=["auto", "psych", "codename"], default="auto")
        s.add_argument("--ai", choices=["auto", "anthropic", "openai", "none"], default="auto")
        s.add_argument("--model")
        s.add_argument("--base-url", help="OpenAI-compatible endpoint, e.g. http://localhost:11434/v1 (Ollama)")
        if name == "convert":
            s.add_argument("-o", "--out", required=True)
            s.add_argument("--mod-id")
            s.add_argument("--no-scripts", action="store_true")
            s.add_argument("--ai-review", action="store_true", help="second AI pass to fix invented APIs")
            s.add_argument("--mirror-shared", action="store_true", help="also copy images/ to shared/images/")
    g = sub.add_parser("gui", help="open the local web GUI")
    g.add_argument("--host", default="127.0.0.1")
    g.add_argument("--port", type=int, default=8765)
    g.add_argument("--no-browser", action="store_true")
    a = p.parse_args(argv)
    {"convert": convert, "analyze": analyze_cmd, "gui": gui_cmd}[a.cmd](a)


if __name__ == "__main__":
    main()
