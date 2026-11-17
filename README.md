# FNFVSlice-Converter

Convierte mods de **Psych Engine** y **Codename Engine** al formato de **V-Slice** (Friday Night Funkin' 0.3+),
con una capa de **IA** que analiza la estructura del mod y traduce los scripts (Lua/HScript → `.hxc`).

> ⚠️ Estado: v0.1. Los formatos se generaron según la documentación/estructura conocida de V-Slice y se
> probaron con mods de ejemplo, **no contra el juego real**. Prueba con un mod pequeño y revisa `_fnfconv/report.md`.

## Qué convierte

| Origen | Destino V-Slice | Método |
|---|---|---|
| Charts Psych (`data/<song>/*.json`, `events.json`) | `data/songs/<id>/<id>-chart.json` + `-metadata.json` | Determinista (mustHit → carriles 0-3 jugador / 4-7 oponente, cambios de BPM, cámara por sección, dificultades) |
| Charts Codename (`songs/<s>/charts/*.json`, `meta.json`) | igual | Determinista (strumLines, noteTypes, `sLen` en steps, BPM Change, Camera Movement) |
| Personajes Psych `.json` / Codename `.xml` | `data/characters/<id>.json` | Determinista |
| Stages `.json`/`.xml` + sprites en Lua (`makeLuaSprite`…) | `data/stages/<id>.json` | Determinista (posición top-left → origen en los pies usando el `.xml` del sprite) |
| Weeks | `data/levels/<id>.json` | Determinista (revisar props) |
| Audio, imágenes, iconos, sonidos | `songs/<id>/Inst.ogg`, `Voices-<char>.ogg`, `images/…` | Copia |
| Eventos `Add Camera Zoom`, `Screen Shake`, `Camera Follow Pos`, `Play Animation`, `Hey!`, `Change Scroll Speed`, `Change BPM` | Eventos nativos o scripts compat | Determinista |
| Scripts `.lua`/`.hx` (canciones, stages, eventos custom, note types, globales) | `scripts/<mod>/…/*.hxc` | **IA** (o stub comentado si no hay IA) |

## Qué hace la IA

1. **Análisis estático siempre** (sin IA): callbacks, llamadas a la API, shaders, vídeos, `runHaxeCode`, cambios de personaje…
2. **Análisis con LLM** (opcional): resumen del mod, riesgos, plan por script → `_fnfconv/report.md`.
3. **Traducción de scripts** con un prompt que incluye una cheat-sheet de la API de V-Slice y la regla
   *"no inventes APIs; si no hay equivalente, deja `// TODO(convert)`"*. Cada salida pasa por un chequeo de sintaxis básico
   (llaves/paréntesis, clase presente); si falla, se genera un **stub** con el script original comentado.
4. `--ai-review`: segunda pasada que corrige APIs inventadas.

Proveedores: **Anthropic** (`ANTHROPIC_API_KEY`), cualquier servidor **compatible con OpenAI** (`OPENAI_API_KEY` o `--base-url`,
p. ej. Ollama `http://localhost:11434/v1` con `--model`). Sin clave funciona en modo offline.
Las respuestas se cachean en `.fnfconv_cache/`.

## Interfaz gráfica (HTML)

```bash
python -m fnfconv gui          # abre http://127.0.0.1:8765 en tu navegador
python -m fnfconv gui --port 9000 --no-browser
```
Arrastra el `.zip` de tu mod (o escribe una ruta de carpeta), revisa el motor detectado, elige IA y opciones, pulsa **Convertir**
y descarga el ZIP resultante junto con el reporte. Es un servidor local (solo `127.0.0.1`, sin dependencias): la clave de API
no se guarda y las peticiones POST exigen una cabecera propia para evitar ataques CSRF.

## Uso (línea de comandos)

```bash
# Sin dependencias externas (Python 3.9+)
python -m fnfconv convert "ruta/al/mod" -o salida/mi-mod
python -m fnfconv convert "ruta/al/mod" -o salida/mi-mod --ai anthropic --ai-review
python -m fnfconv convert "ruta/al/mod" -o salida/mi-mod --ai openai --base-url http://localhost:11434/v1 --model qwen2.5-coder
python -m fnfconv analyze "ruta/al/mod"          # solo análisis
```
Opciones: `--engine psych|codename`, `--mod-id`, `--no-scripts`, `--mirror-shared` (copia `images/` también a `shared/images/`).

Copia la carpeta de salida a `mods/` de V-Slice. Revisa `_fnfconv/report.md` (puedes borrar esa carpeta al publicar).

## Limitaciones conocidas

- Shaders, vídeos/cutscenes MP4, estados/menús custom, y mecánicas de Lua muy dinámicas **no tienen equivalente directo**; se listan en el reporte.
- `healthbar_colors` de Psych no existe en V-Slice. `singTime` se estima (`sing_duration × 1.1`).
- Posición de personajes base del juego en stages: estimada (se avisa).
- Voces combinadas (`Voices.ogg`) se asignan al jugador.
- Si tus assets no cargan, prueba `--mirror-shared` (la resolución de la librería `shared` puede variar por versión).

## Tests

```bash
python -m unittest discover -s tests -t .
```
