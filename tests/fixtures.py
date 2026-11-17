import json
from pathlib import Path


def w(p, text):
    p = Path(p); p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text if isinstance(text, str) else json.dumps(text), encoding="utf-8")


XML = '<TextureAtlas imagePath="x.png"><SubTexture name="BF idle dance0000" x="0" y="0" width="100" height="200" frameX="-5" frameY="0" frameWidth="110" frameHeight="210"/></TextureAtlas>'


def psych_mod(root):
    root = Path(root)
    w(root / "pack.json", {"name": "Test Psych", "description": "d"})
    chart = {"song": {"song": "Test Song", "bpm": 100, "speed": 2.0, "player1": "bf", "player2": "dad", "stage": "mystage",
        "notes": [
            {"sectionNotes": [[0, 0, 0], [500, 5, 250, "Hurt Note"]], "mustHitSection": True, "lengthInSteps": 16},
            {"sectionNotes": [[2400, 1, 0], [2500, 6, 0]], "mustHitSection": False, "changeBPM": True, "bpm": 200, "lengthInSteps": 16}],
        "events": [[1000, [["Add Camera Zoom", "0.03", "0.05"], ["Camera Follow Pos", "100", "200"], ["Screen Shake", "1, 0.05", ""], ["Weird Thing", "a", "b"]]]]}}
    w(root / "data/test-song/test-song.json", chart)
    chart["song"]["speed"] = 3.0
    w(root / "data/test-song/test-song-hard.json", chart)
    w(root / "data/test-song/script.lua", "function onBeatHit()\n  cameraShake('game',0.01,0.1)\nend\n")
    w(root / "songs/test-song/Inst.ogg", "x"); w(root / "songs/test-song/Voices.ogg", "x")
    w(root / "characters/bf.json", {"animations": [{"anim": "idle", "name": "BF idle dance", "fps": 24, "loop": False, "indices": [], "offsets": [0, 0]},
        {"anim": "singLEFT", "name": "BF NOTE LEFT0", "fps": 24, "loop": False, "indices": [], "offsets": [5, -6]}],
        "image": "characters/BOYFRIEND", "scale": 1, "healthicon": "bf", "flip_x": True, "sing_duration": 4, "position": [0, 0], "camera_position": [0, 0]})
    w(root / "images/characters/BOYFRIEND.xml", XML); w(root / "images/characters/BOYFRIEND.png", "png")
    w(root / "images/icons/icon-bf.png", "png")
    w(root / "stages/mystage.json", {"defaultZoom": 0.8, "boyfriend": [770, 100], "opponent": [100, 100], "girlfriend": [400, 130]})
    w(root / "stages/mystage.lua", "function onCreate()\n makeLuaSprite('bg','stageback',-600,-200)\n setScrollFactor('bg',0.9,0.9)\n addLuaSprite('bg',false)\n makeLuaSprite('fg','front',0,500)\n addLuaSprite('fg',true)\nend\n")
    w(root / "weeks/week1.json", {"songs": [["Test Song", "dad", [1, 2, 3]]], "weekCharacters": ["dad", "bf", "gf"], "storyName": "Week One", "freeplayColor": [255, 0, 0]})
    w(root / "custom_events/Zoom Pulse.lua", "function onEvent(name,v1,v2) end")


def codename_mod(root):
    root = Path(root)
    w(root / "songs/cn-song/meta.json", {"name": "cn-song", "bpm": 120, "displayName": "CN Song", "difficulties": ["normal"]})
    w(root / "songs/cn-song/charts/normal.json", {"stage": "cnstage", "scrollSpeed": 2.2, "noteTypes": ["Alt Anim"],
        "strumLines": [
            {"type": 0, "characters": ["dad"], "notes": [{"time": 0, "id": 1, "sLen": 0, "type": 0}]},
            {"type": 1, "characters": ["bf"], "notes": [{"time": 500, "id": 2, "sLen": 4, "type": 1}]},
            {"type": 2, "characters": ["gf"], "notes": []}],
        "events": [{"time": 0, "name": "Camera Movement", "params": [1]}, {"time": 1000, "name": "Camera Movement", "params": [0]},
                   {"time": 2000, "name": "BPM Change", "params": [240]}, {"time": 3000, "name": "My Event", "params": ["a", 2]}]})
    w(root / "songs/cn-song/song/Inst.ogg", "x"); w(root / "songs/cn-song/song/Voices.ogg", "x")
    w(root / "songs/cn-song/scripts/s.hx", "function create() {}\nfunction beatHit(b) {}")
    w(root / "data/characters/bf.xml", '<character x="1" y="2" camx="3" camy="4" holdTime="4" flipX="true" icon="bf" sprite="bf"><anim name="idle" anim="BF idle dance" fps="24" loop="false" x="0" y="0" indices="0..2,5"/></character>')
    w(root / "images/characters/bf.xml", XML); w(root / "images/characters/bf.png", "png")
    w(root / "data/stages/cnstage.xml", '<stage zoom="0.7" name="cnstage"><sprite sprite="bg" x="-10" y="-20" scroll="0.5"/><boyfriend x="700" y="50"/><dad x="50" y="60"/></stage>')
    w(root / "data/weeks/weeks/w1.xml", '<week name="CN Week"><song name="cn-song"/></week>')
