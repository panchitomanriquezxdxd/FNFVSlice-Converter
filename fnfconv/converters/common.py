"""Builders for V-Slice (Funkin' 0.3+) data structures."""
from __future__ import annotations

from ..util import num

GENERATED_BY = "FNFVSlice-Converter"
BASE_STAGES = {
    "stage": "mainStage", "spooky": "spookyMansion", "philly": "phillyTrain", "limo": "limoRide",
    "mall": "mall", "mallevil": "mallEvil", "school": "school", "schoolevil": "schoolEvil",
    "tank": "tankmanBattlefield",
}
DIFF_RATING = {"easy": 1, "normal": 2, "hard": 3, "erect": 4, "nightmare": 5}
# Approximate (Psych top-left -> V-Slice feet-origin) deltas for base-game sprites we cannot measure.
FEET_ESTIMATE = {"bf": (219, 785), "dad": (235, 785), "gf": (351, 657)}


def ev(t, name, value):
    return {"t": num(t), "e": name, "v": value}


def bpm_at(changes, t):
    cur = changes[0][1]
    for ct, b in sorted(changes):
        if ct <= t:
            cur = b
    return cur


def time_changes(bpm_changes):
    out, beat, prev_t, prev_bpm = [], 0.0, 0.0, None
    seen = set()
    for t, bpm in sorted(bpm_changes):
        if t in seen:
            continue
        seen.add(t)
        if prev_bpm is not None:
            beat += (t - prev_t) * prev_bpm / 60000.0
        out.append({"t": num(t), "b": round(beat, 4), "bpm": num(bpm), "n": 4, "d": 4, "bt": [4, 4, 4, 4]})
        prev_t, prev_bpm = t, bpm
    return out


def make_metadata(name, artist, charter, bpm_changes, diffs, player, opponent, gf, stage,
                  player_vocals, opp_vocals):
    return {
        "version": "2.2.4", "songName": name, "artist": artist or "Unknown", "charter": charter or "",
        "divisions": 96, "looped": False,
        "offsets": {"instrumental": 0, "altInstrumentals": {}, "vocals": {}, "altVocals": {}},
        "playData": {
            "songVariations": [], "difficulties": diffs,
            "characters": {"player": player, "girlfriend": gf, "opponent": opponent, "instrumental": "",
                           "opponentVocals": opp_vocals, "playerVocals": player_vocals},
            "stage": stage, "noteStyle": "funkin",
            "ratings": {d: DIFF_RATING.get(d, 1) for d in diffs},
            "previewStart": 0, "previewEnd": 15000,
        },
        "generatedBy": GENERATED_BY, "timeFormat": "ms", "timeChanges": time_changes(bpm_changes),
    }


def make_chart(speeds, events, notes_by_diff):
    default = speeds.get("normal", next(iter(speeds.values()), 1.0))
    return {
        "version": "2.0.0",
        "scrollSpeed": {"default": num(default), **{k: num(v) for k, v in speeds.items()}},
        "events": sorted(events, key=lambda e: e["t"]),
        "notes": {d: sorted(n, key=lambda x: (x["t"], x["d"])) for d, n in notes_by_diff.items()},
        "generatedBy": GENERATED_BY,
    }


def make_character(cid, asset, anims, *, scale=1, flip_x=False, icon=None, offsets=(0, 0),
                   cam=(0, 0), sing_time=4.0, is_pixel=False):
    names = {a["name"] for a in anims}
    out = []
    for a in anims:
        d = {"name": a["name"], "prefix": a["prefix"],
             "offsets": [num(a["offsets"][0]), num(a["offsets"][1])],
             "looped": bool(a["loop"]), "frameRate": num(a["fps"])}
        if a.get("indices"):
            d["frameIndices"] = [int(i) for i in a["indices"]]
        out.append(d)
    return {
        "version": "1.0.0", "name": cid.replace("-", " ").title(), "renderType": "sparrow",
        "assetPath": asset, "scale": num(scale),
        "healthIcon": {"id": icon or cid, "scale": 1, "flipX": False, "isPixel": is_pixel, "offsets": [0, 0]},
        "offsets": [num(offsets[0]), num(offsets[1])], "cameraOffsets": [num(cam[0]), num(cam[1])],
        "isPixel": is_pixel, "danceEvery": 1 if {"danceLeft", "danceRight"} <= names else 2,
        "singTime": sing_time, "flipX": bool(flip_x), "animations": out,
    }


def make_stage(name, zoom, chars, props):
    return {"version": "1.0.0", "name": name, "cameraZoom": num(zoom), "props": props,
            "characters": chars, "directory": "shared"}


def make_level(name, songs, title_asset, props, background):
    return {"version": "1.0.0", "name": name, "titleAsset": title_asset, "props": props,
            "background": background, "songs": songs}


def sprite_frame_size(images_dir, image, prefix=None):
    """Untrimmed size of the first matching Sparrow frame (used to convert top-left -> feet origin)."""
    import xml.etree.ElementTree as ET
    from ..util import ci_path
    xml = ci_path(images_dir, image + ".xml")
    if not xml:
        return None
    try:
        for st in ET.parse(xml).getroot().iter("SubTexture"):
            if prefix is None or st.get("name", "").startswith(prefix):
                w = st.get("frameWidth") or st.get("width")
                h = st.get("frameHeight") or st.get("height")
                return float(w), float(h)
    except (ET.ParseError, TypeError, ValueError):
        return None
    return None
