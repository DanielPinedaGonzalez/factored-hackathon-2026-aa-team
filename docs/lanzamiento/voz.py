"""Genera la voz de la película, una escena por archivo, con la voz elegida (Gemini «Leda» por OpenRouter).

Uso (desde la raíz del repositorio):  python docs/lanzamiento/voz.py [id_de_escena ...]
Lee el texto en inglés de `escenas.py`, guarda `audio/<id>.wav` y `audio/duraciones.json` (que `escenas.py` usa para fijar la duración de cada escena).
La llave se lee del entorno (`OPENROUTER_API_KEY_PAGO`); nunca se imprime. La indicación de tono va en el campo `instructions`: dentro del texto, la voz la leería."""
import json
import os
import sys
import wave
from pathlib import Path

import httpx

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI))
from escenas import ESCENAS  # noqa: E402

MODELO, VOZ = "google/gemini-3.8-flash-tts", "Leda"
TONO = "Speak as a warm, cheerful, friendly woman: clear, fluid and smiling, at a calm medium pace."
SALIDA = AQUI / "audio"


def sintetizar(texto: str, llave: str) -> bytes:
    r = httpx.post("https://openrouter.ai/api/v1/audio/speech", timeout=240, headers={"Authorization": f"Bearer {llave}"},
                   json={"model": MODELO, "input": texto, "voice": VOZ, "response_format": "pcm", "instructions": TONO})
    if r.status_code != 200:
        sys.exit(f"HTTP {r.status_code}: {r.text[:200]}")
    return r.content


def main() -> None:
    for linea in (AQUI.parents[1] / ".env").read_text().splitlines():
        if "=" in linea and not linea.startswith("#"):
            k, v = linea.strip().split("=", 1)
            os.environ.setdefault(k, v)
    llave = os.environ["OPENROUTER_API_KEY_PAGO"]
    SALIDA.mkdir(exist_ok=True)
    ruta = SALIDA / "duraciones.json"
    duraciones = json.loads(ruta.read_text()) if ruta.exists() else {}
    for e in ESCENAS:
        if len(sys.argv) > 1 and e["id"] not in sys.argv[1:]:
            continue
        pcm = sintetizar(e["en"], llave)
        with wave.open(str(SALIDA / f"{e['id']}.wav"), "wb") as w:
            w.setnchannels(1); w.setsampwidth(2); w.setframerate(24000); w.writeframes(pcm)
        duraciones[e["id"]] = round(len(pcm) / 48000, 2)
        print(f"{e['id']:9s} {duraciones[e['id']]:6.2f} s · {len(e['en'].split())} palabras")
    ruta.write_text(json.dumps(duraciones, indent=1))
    print(f"total de voz: {sum(duraciones.values()):.1f} s")


if __name__ == "__main__":
    main()
