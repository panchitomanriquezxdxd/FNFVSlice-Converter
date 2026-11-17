from __future__ import annotations

from pathlib import Path


def find_mod_root(path) -> Path:
    p = Path(path)
    mods = p / "mods"
    if mods.is_dir():
        subs = [d for d in mods.iterdir() if d.is_dir()]
        if len(subs) == 1:
            return subs[0]
    return p


def _has_psych_chart(data: Path) -> bool:
    if not data.is_dir():
        return False
    for d in data.iterdir():
        if d.is_dir():
            for f in list(d.glob("*.json"))[:4]:
                try:
                    if "sectionNotes" in f.read_text(encoding="utf-8-sig", errors="ignore")[:400000]:
                        return True
                except OSError:
                    pass
    return False


def detect_engine(root: Path):
    """Returns (engine, evidence). engine in {'psych','codename','unknown'}."""
    s = {"psych": 0, "codename": 0}
    ev = []

    def hit(engine, pts, why):
        s[engine] += pts
        ev.append(f"{engine}+{pts}: {why}")

    if (root / "pack.json").exists(): hit("psych", 2, "pack.json")
    if (root / "weeks").is_dir(): hit("psych", 1, "weeks/")
    if list((root / "characters").glob("*.json")) if (root / "characters").is_dir() else []: hit("psych", 3, "characters/*.json")
    if list((root / "stages").glob("*.json")) if (root / "stages").is_dir() else []: hit("psych", 2, "stages/*.json")
    if _has_psych_chart(root / "data"): hit("psych", 4, "data/<song>/*.json with sectionNotes")
    songs = root / "songs"
    if songs.is_dir():
        if list(songs.glob("*/charts/*.json")): hit("codename", 4, "songs/*/charts/*.json")
        if list(songs.glob("*/meta.json")): hit("codename", 3, "songs/*/meta.json")
    d = root / "data"
    if d.is_dir():
        if list((d / "characters").glob("*.xml")): hit("codename", 3, "data/characters/*.xml")
        if list((d / "stages").glob("*.xml")): hit("codename", 2, "data/stages/*.xml")
        if (d / "weeks" / "weeks").is_dir(): hit("codename", 2, "data/weeks/weeks/")
    best = max(s, key=s.get)
    if s[best] < 3 or s["psych"] == s["codename"]:
        return "unknown", ev
    return best, ev
