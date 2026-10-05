"""Graba la película con su voz, una escena por vez, y las une.

Uso (desde la raíz del repositorio):  python docs/lanzamiento/grabar.py [SALIDA.mp4] [id_de_escena ...] [--unir]   (con escenas sueltas solo se regraban esas; --unir vuelve a juntar todas)      (por defecto privado/video/lanzamiento.mp4)
Antes: `python docs/lanzamiento/voz.py` (genera `audio/*.wav` y las duraciones) y `python docs/lanzamiento/generar.py`.

Por qué por escenas: grabar las 12 de corrido, en tiempo real, en una máquina justa de memoria dejó la página congelada a mitad de la película. Cada escena se graba aparte
(`lanzamiento.html?manual&grabar&solo=N`, con el mapa en el estado que le deja el recorrido anterior), dura lo que su voz más una pausa y, si el navegador se cae, se repite.
La voz empieza 0,7 s después de entrar la escena (el mismo retraso que en la película). Necesita `ffmpeg` (el del sistema o el paquete `imageio-ffmpeg`)."""
import shutil
import subprocess
import sys
import time
import wave
from pathlib import Path

from playwright.sync_api import sync_playwright

AQUI = Path(__file__).resolve().parent
RAIZ = AQUI.parents[1]
sys.path.insert(0, str(AQUI))
from escenas import ESCENAS  # noqa: E402

ENTRADA_VOZ_S, COLA_S = 0.7, 0.7
MARCO = 24000


def ffmpeg() -> str:
    if shutil.which("ffmpeg"):
        return "ffmpeg"
    import imageio_ffmpeg
    return imageio_ffmpeg.get_ffmpeg_exe()


def largo(e: dict) -> float:
    return round(e["seg"] + COLA_S, 2)


def pcm_de_escena(e: dict) -> bytes:
    """La voz de la escena con su silencio de entrada y de salida, a la medida exacta de la escena (muestras de 16 bits, mono)."""
    with wave.open(str(AQUI / "audio" / f"{e['id']}.wav")) as w:
        assert w.getframerate() == MARCO and w.getnchannels() == 1 and w.getsampwidth() == 2, f"{e['id']}.wav no es PCM mono de 16 bits a {MARCO} Hz"
        pcm = w.readframes(w.getnframes())
    ini = b"\0\0" * round(ENTRADA_VOZ_S * MARCO)
    fin = b"\0\0" * max(0, round(largo(e) * MARCO) - len(ini) // 2 - len(pcm) // 2)
    return ini + pcm + fin


def grabar_escena(i: int, e: dict, trabajo: Path) -> Path:
    carpeta = trabajo / f"v{i:02d}"
    shutil.rmtree(carpeta, ignore_errors=True); carpeta.mkdir(parents=True)
    caida = []
    with sync_playwright() as p:
        b = p.chromium.launch()
        t_contexto = time.time()
        ctx = b.new_context(viewport={"width": 1920, "height": 1080}, record_video_dir=str(carpeta), record_video_size={"width": 1920, "height": 1080})
        pg = ctx.new_page()
        pg.on("crash", lambda _: caida.append(True))
        pg.goto(f"file://{AQUI}/lanzamiento.html?manual&grabar&solo={i}")
        pg.wait_for_timeout(1200)
        t_inicio = time.time()
        pg.evaluate("iniciar()")
        pg.wait_for_timeout(int((largo(e) + 0.8) * 1000))
        ctx.close(); b.close()
    if caida:
        raise RuntimeError("el navegador se cayó")
    webm = next(carpeta.glob("*.webm"))
    salida = trabajo / f"escena_{i:02d}.mp4"
    subprocess.run([ffmpeg(), "-y", "-loglevel", "error", "-ss", f"{t_inicio - t_contexto:.2f}", "-i", str(webm), "-t", f"{largo(e):.2f}", "-an",
                    "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p", "-r", "30", str(salida)], check=True)
    return salida


def unir(trabajo: Path, salida: Path) -> None:
    """Une las escenas (solo imagen, cada una recortada a su largo actual) y pone la voz como UNA pista continua, codificada una sola vez:
    codificar y pegar el audio escena por escena dejaba microcortes en cada unión."""
    clips = []
    for i, e in enumerate(ESCENAS):
        fuente = trabajo / f"escena_{i:02d}.mp4"
        mudo = trabajo / f"mudo_{i:02d}.mp4"
        subprocess.run([ffmpeg(), "-y", "-loglevel", "error", "-i", str(fuente), "-t", f"{largo(e):.2f}", "-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
                        "-pix_fmt", "yuv420p", "-r", "30", str(mudo)], check=True)
        clips.append(mudo)
    lista = trabajo / "lista.txt"
    lista.write_text("".join(f"file '{c.name}'\n" for c in clips))
    imagen = trabajo / "imagen.mp4"
    subprocess.run([ffmpeg(), "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(lista), "-c", "copy", str(imagen)], check=True)
    voz = trabajo / "voz_total.wav"
    with wave.open(str(voz), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(MARCO)
        for e in ESCENAS:
            w.writeframes(pcm_de_escena(e))
    subprocess.run([ffmpeg(), "-y", "-loglevel", "error", "-i", str(imagen), "-i", str(voz), "-map", "0:v", "-map", "1:a", "-c:v", "copy",
                    "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "1", "-movflags", "+faststart", str(salida)], check=True)


def main() -> None:
    args = sys.argv[1:]
    salida = Path(args[0]) if args and args[0].endswith(".mp4") else RAIZ / "privado" / "video" / "lanzamiento.mp4"
    juntar = "--unir" in args
    solo = [a for a in args if not a.endswith(".mp4") and a != "--unir"]
    salida.parent.mkdir(parents=True, exist_ok=True)
    trabajo = salida.parent / "_escenas"
    trabajo.mkdir(exist_ok=True)
    for i, e in enumerate(ESCENAS):
        if solo and e["id"] not in solo:
            continue
        for intento in (1, 2, 3):
            try:
                t0 = time.time()
                grabar_escena(i, e, trabajo)
                print(f"{e['id']:9s} grabada en {time.time() - t0:.0f} s (dura {largo(e):.1f} s)", flush=True)
                break
            except Exception as ex:                       # una caída del navegador solo repite esa escena
                print(f"{e['id']:9s} intento {intento} falló: {ex}", flush=True)
        else:
            sys.exit(f"no se pudo grabar la escena {e['id']}")
    if solo and not juntar:
        return
    unir(trabajo, salida)
    print(f"video: {salida} · {sum(largo(e) for e in ESCENAS):.0f} s")


if __name__ == "__main__":
    main()
