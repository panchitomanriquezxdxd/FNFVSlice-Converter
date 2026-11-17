"""Deterministic extraction of static stage sprites from Psych Lua stage scripts."""
from __future__ import annotations

import re

from ..util import num

CALL_RE = re.compile(r"\b([A-Za-z_]\w*)\s*\(([^()]*)\)")
IGNORE = {"function", "if", "elseif", "while", "for", "return", "onCreate", "onCreatePost", "print",
          "debugPrint", "precacheImage", "precacheSound", "updateHitbox", "setObjectOrder",
          "ipairs", "pairs", "tostring", "tonumber"}


def _split(s):
    out, cur, q = [], "", None
    for ch in s:
        if q:
            cur += ch
            if ch == q:
                q = None
        elif ch in "'\"":
            q = ch
            cur += ch
        elif ch == ",":
            out.append(cur.strip())
            cur = ""
        else:
            cur += ch
    if cur.strip():
        out.append(cur.strip())
    return out


def _val(tok):
    tok = tok.strip()
    if len(tok) >= 2 and tok[0] in "'\"" and tok[-1] == tok[0]:
        return tok[1:-1]
    if tok == "true":
        return True
    if tok == "false":
        return False
    try:
        return float(tok)
    except ValueError:
        return None


def parse_lua_stage(text):
    """-> (props, unhandled_calls). Anything not in unhandled_calls was fully converted."""
    text = re.sub(r"--\[\[.*?\]\]", "", text, flags=re.S)
    text = re.sub(r"--[^\n]*", "", text)
    sprites, order, unhandled = {}, [], set()
    for m in CALL_RE.finditer(text):
        fn = m.group(1)
        a = [_val(x) for x in _split(m.group(2))]
        g = lambda i, d=None: a[i] if i < len(a) and a[i] is not None else d
        tag = g(0)
        if fn in ("makeLuaSprite", "makeAnimatedLuaSprite"):
            if tag is None or g(1) is None:
                unhandled.add(fn + "(non-literal)")
                continue
            sprites[tag] = {"image": g(1), "x": g(2, 0), "y": g(3, 0), "animated": fn == "makeAnimatedLuaSprite",
                            "scroll": [1, 1], "scale": [1, 1], "anims": [], "front": False, "alpha": 1}
        elif fn == "setScrollFactor" and tag in sprites:
            sprites[tag]["scroll"] = [g(1, 1), g(2, g(1, 1))]
        elif fn == "scaleObject" and tag in sprites:
            sprites[tag]["scale"] = [g(1, 1), g(2, g(1, 1))]
        elif fn == "addAnimationByPrefix" and tag in sprites:
            sprites[tag]["anims"].append({"name": g(1, "idle"), "prefix": g(2, ""), "frameRate": g(3, 24),
                                          "looped": bool(g(4, True))})
        elif fn == "addLuaSprite" and tag in sprites:
            sprites[tag]["front"] = bool(g(1, False))
            order.append(tag)
        elif fn == "setProperty" and isinstance(tag, str) and tag.split(".")[0] in sprites:
            attr = tag.split(".")[-1]
            if attr == "alpha" and g(1) is not None:
                sprites[tag.split(".")[0]]["alpha"] = g(1)
            elif attr not in ("antialiasing",):
                unhandled.add(f"setProperty(.{attr})")
        elif fn in IGNORE:
            continue
        else:
            unhandled.add(fn)
    props, back, front = [], 0, 0
    for tag in order:
        sp = sprites[tag]
        if sp["front"]:
            z, front = 400 + front, front + 1
        else:
            z, back = 10 + back, back + 1
        p = {"zIndex": z, "position": [num(sp["x"]), num(sp["y"])], "scale": [num(v) for v in sp["scale"]],
             "name": tag, "assetPath": sp["image"], "isPixel": False,
             "scroll": [num(v) for v in sp["scroll"]], "alpha": num(sp["alpha"])}
        if sp["animated"]:
            p["animType"] = "sparrow"
            p["animations"] = [{"name": x["name"], "prefix": x["prefix"], "frameRate": num(x["frameRate"]),
                                "looped": x["looped"]} for x in sp["anims"]]
            if sp["anims"]:
                p["startingAnimation"] = sp["anims"][0]["name"]
        props.append(p)
    return props, unhandled
