from __future__ import annotations

import json
import re
import shutil
from pathlib import Path


def read_json(path):
    """Tolerant JSON reader (BOM, NUL padding and trailing garbage are common in FNF charts)."""
    raw = Path(path).read_bytes().decode("utf-8-sig", errors="replace").strip().strip("\x00")
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return json.loads(raw[: raw.rfind("}") + 1])


def write_json(path, data):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def write_text(path, text):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def slug(name) -> str:
    return re.sub(r"[^a-z0-9]+", "-", str(name).lower()).strip("-") or "unnamed"


def pascal(name) -> str:
    parts = [w for w in re.split(r"[^A-Za-z0-9]+", str(name)) if w]
    return "".join(w[0].upper() + w[1:] for w in parts) or "Unnamed"


def num(x):
    x = float(x)
    return int(x) if x.is_integer() else round(x, 3)


def ci_path(base, rel):
    """Case-insensitive path lookup (mods made on Windows often mix casing)."""
    cur = Path(base)
    for part in Path(rel).parts:
        if not cur.is_dir():
            return None
        nxt = next((c for c in cur.iterdir() if c.name.lower() == part.lower()), None)
        if nxt is None:
            return None
        cur = nxt
    return cur


def copy_file(src, dst):
    Path(dst).parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)


def copy_tree(src, dst) -> int:
    n = 0
    src = Path(src)
    for p in src.rglob("*"):
        if p.is_file():
            copy_file(p, Path(dst) / p.relative_to(src))
            n += 1
    return n
