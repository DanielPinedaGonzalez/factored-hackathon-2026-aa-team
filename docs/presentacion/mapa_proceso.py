"""El mapa del proceso en una sola imagen: de lo que escribe el cliente, a la política, a la persona y de vuelta.

Se dibuja a mano (SVG con carriles y coordenadas fijas) porque el trazado automático de Mermaid enreda un diagrama con tres carriles y
varios regresos. Lo usan las diapositivas (`generar.py`) y se guarda en `docs/presentacion/mapa_proceso_{en,es}.svg` para los planos.
Idioma: `en` (presentación) o `es` (planos). Uso: python docs/presentacion/mapa_proceso.py   → escribe los dos SVG.
"""
from __future__ import annotations

from html import escape
from pathlib import Path

ANCHO, ALTO = 1240, 514

TEXTOS = {
    "en": {
        "carriles": ["CUSTOMER", "ASSISTANT · model + code", "HUMAN TEAM"],
        "c1": ["“I don't", "recognize", "this charge”"], "c2": ["Confirms", "the action"],
        "c3": ["Gets a real", "answer in the", "same chat"], "c4": ["Comes back later:", "status · add ·", "withdraw"],
        "a1": ["Model", "understands.", "Code finds the", "real charge"],
        "p": ["Policy:", "4 checks +", "country rules:", "may we act alone?"],
        "a2": ["Proposes", "the allowed", "action"], "a3": ["Code executes", "and re-reads", "the real state"],
        "ap": ["Handoff package:", "facts · actions ·", "open questions"],
        "cn": ["Tells the customer:", "“Your case goes to the", "fraud team. You are #3.”"],
        "h1": ["Router: skill ·", "language ·", "priority"], "h2": ["Human agent sees", "the package, does", "not ask again"],
        "h3": ["Human", "agent", "decides"], "h5": ["Investigates the", "claim, decides ·", "customer is", "notified"],
        "si": "yes", "no": ["no: risk, high amount,", "doubt, or no model"],
        "verifica": "verified", "no_coincide": "does not match", "responde": "replies",
        "devuelve": ["returns it to the", "assistant, with a note"], "transfiere": "not mine: transfers with a note",
        "reclamo": "claim opened", "vuelve": "comes back later: the process starts again",
        "m1": ["M1 risk signal"],
        "leyenda": [("cliente", "Customer"), ("modelo", "Model"), ("codigo", "Code"), ("politica", "Policy"), ("m1", "M1 (learned)"), ("persona", "Person")],
    },
    "es": {
        "carriles": ["CLIENTE", "ASISTENTE · modelo + código", "EQUIPO HUMANO"],
        "c1": ["«No reconozco", "este cargo»"], "c2": ["Confirma", "la acción"],
        "c3": ["Recibe respuesta", "real en el chat"], "c4": ["Vuelve después:", "consulta · retira"],
        "a1": ["El modelo entiende.", "El código busca", "el cargo real"],
        "p": ["Política", "4 verificaciones + reglas", "del país: ¿se puede solo?"],
        "a2": ["Propone la", "acción permitida"], "a3": ["El código ejecuta y", "relee el estado real"],
        "ap": ["Traspaso:", "hechos · acciones ·", "preguntas abiertas"],
        "cn": ["Le dice al cliente:", "«Tu caso pasa al equipo", "de fraude. Eres el 3.º.»"],
        "h1": ["Enrutador:", "habilidad · idioma", "· prioridad"], "h2": ["El asesor ve el paquete,", "no vuelve a preguntar"],
        "h3": ["El asesor", "decide"], "h5": ["Investiga el reclamo,", "decide · se avisa", "al cliente"],
        "si": "sí", "no": ["no: riesgo, monto alto,", "duda o sin modelo"],
        "verifica": "verificado", "no_coincide": "no coincide", "responde": "responde",
        "devuelve": ["lo devuelve al", "asistente, con una nota"], "transfiere": "no es mío: transfiere con una nota",
        "reclamo": "reclamo abierto", "vuelve": "vuelve después: el proceso empieza de nuevo",
        "m1": ["Señal de riesgo M1"],
        "leyenda": [("cliente", "Cliente"), ("modelo", "Modelo"), ("codigo", "Código"), ("politica", "Política"), ("m1", "M1 (aprendido)"), ("persona", "Persona")],
    },
}

COLORES = {"cliente": ("#e8f1ff", "#2b6cb0", "#1a365d"), "modelo": ("#9b6bd1", "#4a1f73", "#ffffff"),
           "codigo": ("#4a1f73", "#4a1f73", "#ffffff"), "politica": ("#fff4d6", "#b7791f", "#5f370e"),
           "persona": ("#127a4b", "#0b5133", "#ffffff"), "m1": ("#fde7dc", "#d95926", "#7a2d0c")}
BANDAS = [(8, 126, "#f4f8ff"), (134, 334, "#faf7fd"), (342, 478, "#f1faf5")]

# Centros (x, y) de cada elemento.
C1, C2, C3, C4 = (110, 64), (600, 64), (985, 64), (1140, 64)
A1, P, A2, A3 = (215, 205), (395, 205), (600, 205), (840, 205)
AP, CN = (395, 304), (612, 300)
H1, H2, H3, H5 = (600, 415), (775, 415), (945, 415), (1140, 415)


def _texto(cx, cy, lineas, color, tam=14, peso=600):
    n = len(lineas)
    paso = tam * 1.18
    ts = "".join(f'<tspan x="{cx}" y="{cy - (n - 1) * paso / 2 + i * paso + 5}">{escape(t)}</tspan>' for i, t in enumerate(lineas))
    return f'<text text-anchor="middle" font-size="{tam}" font-weight="{peso}" fill="{color}">{ts}</text>'


def _caja(centro, w, h, lineas, clase, forma="caja"):
    cx, cy = centro
    w = w + 8
    tam = 14
    mas_larga = max(len(t) for t in lineas)
    if forma == "caja":
        tam = min(14, (w - 16) / (mas_larga * 0.56))                # que ninguna línea se salga de su caja
    h = max(h + 6, len(lineas) * tam * 1.18 + 16) if forma != "pildora" else h + 6
    fondo, borde, color = COLORES[clase]
    if forma == "rombo":
        f = f'<polygon points="{cx},{cy - h / 2} {cx + w / 2},{cy} {cx},{cy + h / 2} {cx - w / 2},{cy}" fill="{fondo}" stroke="{borde}" stroke-width="2"/>'
    else:
        rx = h / 2 if forma == "pildora" else 8
        f = f'<rect x="{cx - w / 2}" y="{cy - h / 2}" width="{w}" height="{h}" rx="{rx}" fill="{fondo}" stroke="{borde}" stroke-width="2"/>'
    return f + _texto(cx, cy, lineas, color, tam)


def _etiqueta(x, y, lineas, ancla="middle"):
    lineas = lineas if isinstance(lineas, list) else [lineas]
    s = ""
    for i, t in enumerate(lineas):
        ancho = 7.0 * len(t) + 8
        x0 = x - ancho / 2 if ancla == "middle" else (x - ancho + 4 if ancla == "end" else x - 4)
        yy = y + i * 14
        s += (f'<rect x="{x0}" y="{yy - 11}" width="{ancho}" height="14" rx="3" fill="#ffffff" fill-opacity="0.94"/>'
              f'<text x="{x}" y="{yy}" text-anchor="{ancla}" font-size="13" fill="#334155">{escape(t)}</text>')
    return s


def _flecha(puntos, discontinua=False):
    d = "M" + " L".join(f"{x},{y}" for x, y in puntos)
    estilo = ' stroke-dasharray="6 5"' if discontinua else ""
    return f'<path d="{d}" fill="none" stroke="#475569" stroke-width="2"{estilo} marker-end="url(#punta)"/>'


def svg(idioma: str = "en") -> str:
    T = TEXTOS[idioma]
    s = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {ANCHO} {ALTO}" font-family="system-ui, Segoe UI, Roboto, sans-serif">',
         '<defs><marker id="punta" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">'
         '<path d="M0,0 L10,5 L0,10 z" fill="#475569"/></marker></defs>']
    for (y0, y1, c), nombre in zip(BANDAS, T["carriles"]):
        s.append(f'<rect x="4" y="{y0}" width="{ANCHO - 8}" height="{y1 - y0}" rx="10" fill="{c}" stroke="#d9e2ef"/>')
        s.append(f'<text x="14" y="{y0 + 16}" font-size="12.5" font-weight="700" fill="#64748b" letter-spacing="0.6">{escape(nombre)}</text>')

    # --- flechas (van debajo de las cajas)
    s += [
        _flecha([(175, 64), (215, 64), (215, 177)]),                                   # el cliente escribe → el modelo entiende
        _flecha([(283, 205), (310, 205)]),                                             # → política
        _flecha([(480, 205), (540, 205)]),                                             # política: sí
        _flecha([(600, 182), (600, 86)]),                                              # propone → el cliente confirma
        _flecha([(655, 64), (840, 64), (840, 182)]),                                   # confirma → ejecuta
        _flecha([(928, 205), (985, 205), (985, 89)]),                                  # ejecuta y verifica → respuesta
        _flecha([(470, 159), (470, 170)]),                                             # M1 → política
        _flecha([(395, 246), (395, 270)]),                                             # política: no → paquete
        _flecha([(474, 304), (489, 300)]),                                             # paquete → aviso al cliente
        _flecha([(600, 327), (600, 388)]),                                             # aviso → enrutador
        _flecha([(790, 228), (790, 262), (440, 262), (440, 273)]),                     # no coincide → paquete
        _flecha([(665, 415), (695, 415)]),                                             # enrutador → asesor ve el paquete
        _flecha([(855, 415), (880, 415)]),                                             # → decide
        _flecha([(1012, 415), (1040, 415), (1040, 89)]),                                # responde en el mismo chat
        _flecha([(930, 375), (930, 252), (880, 252), (880, 228)]),                     # lo devuelve al asistente
        _flecha([(945, 455), (945, 468), (600, 468), (600, 442)]),                     # transfiere con una nota
        _flecha([(840, 228), (840, 345), (1100, 345), (1100, 386)], True),             # reclamo abierto → investigación
        _flecha([(1180, 386), (1180, 89)], True),                                      # decisión → se avisa al cliente
        _flecha([(1140, 39), (1140, 22), (110, 22), (110, 39)], True),                 # el cliente vuelve: empieza de nuevo
    ]
    # --- cajas
    s += [_caja(C1, 130, 50, T["c1"], "cliente", "pildora"), _caja(C2, 110, 44, T["c2"], "cliente", "pildora"),
          _caja(C3, 150, 50, T["c3"], "cliente", "pildora"), _caja(C4, 158, 50, T["c4"], "cliente", "pildora"),
          _caja(A1, 136, 56, T["a1"], "modelo"), _caja(P, 170, 70, T["p"], "politica"),
          _caja(A2, 120, 46, T["a2"], "codigo"), _caja(A3, 175, 46, T["a3"], "codigo"),
          _caja((530, 146), 130, 24, T["m1"], "m1", "pildora"), _caja(AP, 150, 54, T["ap"], "codigo"), _caja(CN, 230, 54, T["cn"], "codigo"),
          _caja(H1, 140, 56, T["h1"], "codigo"), _caja(H2, 160, 46, T["h2"], "persona"),
          _caja(H3, 118, 104, T["h3"], "persona", "rombo"), _caja(H5, 162, 58, T["h5"], "persona")]
    # --- etiquetas de las flechas
    s += [_etiqueta(510, 198, T["si"]), _etiqueta(388, 254, T["no"], "end"), _etiqueta(952, 198, T["verifica"]),
          _etiqueta(650, 257, T["no_coincide"]), _etiqueta(1043, 250, T["responde"]),
          _etiqueta(900, 322, T["devuelve"], "end") if False else _etiqueta(938, 292, T["devuelve"], "start"),
          _etiqueta(780, 482, T["transfiere"]), _etiqueta(1010, 340, T["reclamo"]), _etiqueta(620, 26, T["vuelve"])]
    # --- leyenda
    x = 260
    for clase, nombre in T["leyenda"]:
        fondo, borde, _ = COLORES[clase]
        s.append(f'<rect x="{x}" y="494" width="14" height="14" rx="3" fill="{fondo}" stroke="{borde}" stroke-width="1.5"/>'
                 f'<text x="{x + 20}" y="506" font-size="13" fill="#475569">{escape(nombre)}</text>')
        x += 120
    s.append("</svg>")
    return "".join(s)


if __name__ == "__main__":
    destino = Path(__file__).resolve().parent
    for idioma in ("en", "es"):
        (destino / f"mapa_proceso_{idioma}.svg").write_text(svg(idioma), encoding="utf-8")
        print("escrito", destino / f"mapa_proceso_{idioma}.svg")
