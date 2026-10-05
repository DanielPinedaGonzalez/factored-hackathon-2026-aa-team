"""Genera la película de lanzamiento y su guion a partir de `escenas.py` (una sola fuente).

Uso (desde la raíz del repositorio):  python docs/lanzamiento/generar.py
Salida: docs/lanzamiento/lanzamiento.html (se abre en el navegador; sin servidor ni dependencias) y privado/GUION_VIDEO.md si existe `privado/`.
Teclas: espacio o → siguiente · ← atrás · A modo automático · V voz · P ventana con la frase que dices · F pantalla completa · R reiniciar."""
import json
import re
import sys
from pathlib import Path

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI))
from escenas import CHAT_REAL, ESCENAS  # noqa: E402

BLOQUES = {"WHY": "Por qué", "WHAT": "Qué", "HOW": "Cómo", "CLOSE": "Cierre"}


def guion_md() -> str:
    total = round(sum(e["seg"] for e in ESCENAS))
    filas = []
    for i, e in enumerate(ESCENAS, 1):
        filas.append(f"### {i:02d} · {BLOQUES[e['bloque']]} · {e['id']}  ({e['seg']} s en automático)\n\n"
                     f"**Lo que ves:** {e['visual']}\n\n> {e['en']}\n> *({e['es']})*\n")
    return f"""# Guion del video: película de lanzamiento (Por qué → Qué → Cómo)

Generado por `docs/lanzamiento/generar.py` desde `docs/lanzamiento/escenas.py`: **no se edita a mano** (cambia `escenas.py` y vuelve a generar).

El organizador pidió (3-oct): vender un producto como ante un inversionista de un banco, **90 % producto y creatividad, 10 % técnico**, con animaciones y
maquetas en lugar de grabar la pantalla, como el lanzamiento de un producto. Esta película es eso; lo técnico son las escenas `how`, `gates`, `m1`, `secure` y `proof`, y el organizador pide que el video demuestre la solución funcionando y explique las decisiones de arquitectura.

## Cómo grabarlo (10 minutos)

1. Abre `docs/lanzamiento/lanzamiento.html` en el navegador (doble clic). Pulsa **F** (pantalla completa).
2. Pulsa **P**: se abre una ventana con **la frase que debes decir** (inglés grande, español debajo) y la siguiente. Ponla en tu segunda pantalla o en el teléfono.
3. Empieza la grabación (OBS, o `Ctrl+Alt+Shift+R` en Ubuntu) y avanza con la **barra espaciadora** cuando termines cada frase. Tú marcas el ritmo; nada se desfasa.
4. Si te trabas, repite la frase; se corta al editar. `R` reinicia, `←` retrocede.
5. Alternativa sin voz en vivo: `lanzamiento.html?auto` (o la tecla **A**) la corre sola con los tiempos de abajo (≈ {total // 60}:{total % 60:02d}); graba la pantalla y pon tu voz encima al editar.

**Idioma:** inglés sencillo, una idea por frase; el español entre paréntesis es lo que significa. Habla despacio.

## Escenas

{chr(10).join(filas)}
## Si te preguntan algo que no está en la película

Las frases para preguntas difíciles están en `docs/ENGLISH_PREPARATION.md` (§0 tres frases para cualquier pregunta y §12 lo nuevo). Los límites honestos
están en la pestaña **About** de la demo: 131 clientes cargados, 62 casos con una sola pasada, portugués verificado por retrotraducción, artículos en borrador.
"""


def ordenar(html: str) -> str:
    """Las <section> de la plantilla se colocan en el orden de `escenas.py`: el orden del guion manda, no el de la plantilla."""
    patron = re.compile(r'<section class="escena[^"]*" data-id="(\w+)">.*?</section>', re.S)
    bloques = {m.group(1): m.group(0) for m in patron.finditer(html)}
    ids = [e["id"] for e in ESCENAS]
    if set(bloques) != set(ids):
        sys.exit(f"escenas sin sección o secciones sin escena: {sorted(set(bloques) ^ set(ids))}")
    primero, ultimo = patron.search(html), list(patron.finditer(html))[-1]
    return html[: primero.start()] + "\n\n".join(bloques[i] for i in ids) + html[ultimo.end():]


def main() -> None:
    html = ordenar((AQUI / "plantilla.html").read_text(encoding="utf-8"))
    html = html.replace("__ESCENAS__", json.dumps(ESCENAS, ensure_ascii=False)).replace("__CHAT__", json.dumps(CHAT_REAL, ensure_ascii=False))
    (AQUI / "lanzamiento.html").write_text(html, encoding="utf-8")
    privado = AQUI.parents[1] / "privado"
    if privado.is_dir():
        (privado / "GUION_VIDEO.md").write_text(guion_md(), encoding="utf-8")
    print(f"película: {AQUI / 'lanzamiento.html'} · {len(ESCENAS)} escenas · {sum(e['seg'] for e in ESCENAS)} s en automático")


if __name__ == "__main__":
    main()
