from __future__ import annotations

from ..util import pascal
from .common import ev
from .templates import COMPAT

TARGETS = {"bf": "bf", "boyfriend": "bf", "1": "bf", "gf": "gf", "girlfriend": "gf", "2": "gf",
           "dad": "dad", "opponent": "dad", "0": "dad"}
COMPAT_NAMES = {"add camera zoom": "AddCameraZoom", "screen shake": "ScreenShake"}


def _f(x, d=0.0):
    try:
        return float(str(x).strip())
    except (TypeError, ValueError):
        return d


def map_psych_event(name, v1, v2, t, bpm):
    """-> (list_of_vslice_events, status, event_id). status: mapped|compat|custom|skipped"""
    n = str(name).strip()
    s1, s2 = str(v1 if v1 is not None else "").strip(), str(v2 if v2 is not None else "").strip()
    if n == "Camera Follow Pos":
        if not s1 and not s2:
            return [], "skipped", "FocusCamera"
        return [ev(t, "FocusCamera", {"char": -1, "x": _f(s1), "y": _f(s2)})], "mapped", "FocusCamera"
    if n == "Play Animation":
        tgt = TARGETS.get(s2.lower(), "dad")
        return [ev(t, "PlayAnimation", {"target": tgt, "anim": s1, "force": True})], "mapped", "PlayAnimation"
    if n == "Hey!":
        w = s1.lower()
        out = []
        if w in ("bf", "boyfriend", "0") or w not in ("gf", "girlfriend", "1"):
            out.append(ev(t, "PlayAnimation", {"target": "bf", "anim": "hey", "force": True}))
        if w in ("gf", "girlfriend", "1") or w not in ("bf", "boyfriend", "0"):
            out.append(ev(t, "PlayAnimation", {"target": "gf", "anim": "cheer", "force": True}))
        return out, "mapped", "PlayAnimation"
    if n == "Change Scroll Speed":
        steps = _f(s2) * bpm * 4 / 60.0
        return [ev(t, "ScrollSpeed", {"scroll": _f(s1, 1.0), "duration": round(steps, 3),
                                      "ease": "linear", "absolute": False})], "mapped", "ScrollSpeed"
    if n == "Change BPM":
        return [], "skipped", "BPM"
    cid = COMPAT_NAMES.get(n.lower())
    if cid:
        return [ev(t, cid, {"value1": s1, "value2": s2})], "compat", cid
    cid = pascal(n)
    return [ev(t, cid, {"value1": s1, "value2": s2})], "custom", cid


__all__ = ["map_psych_event", "COMPAT"]
