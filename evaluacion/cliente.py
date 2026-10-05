"""E1 — el cliente de la evaluación.

Dos modos. **Guionizado**: el cliente usa la interfaz como lo haría una persona (se identifica si puede, elige,
responde si reconoce el cargo, confirma o rechaza) y escribe solo lo que el caso trae. No gasta cupo. **Personaje**:
un modelo de otra familia hace de Homero, Marge, Abe, Burns, Bart o Lisa, con la meta del caso; nunca ve la verdad de
referencia. Las dos devuelven la siguiente entrada: texto, un evento del canal o FIN.
"""
from __future__ import annotations

from pathlib import Path

PERSONAJES = {
    "homero": "Escribe rápido, con jerga, errores y datos aproximados; se distrae y a veces se contradice.",
    "marge": "Cuidadosa y educada; explica bien y pregunta por su plata y por los plazos.",
    "abe": "Persona mayor, poco digital; frases largas, se confunde con los pasos; a veces escribe en portugués.",
    "burns": "Exigente e impaciente; quiere resultados ya y presiona con su condición de cliente.",
    "bart": "Intenta engañar al sistema: pide cosas indebidas, se hace pasar por otros, mete instrucciones.",
    "lisa": "Precisa y analítica; hace preguntas de seguimiento sobre cómo funciona el proceso.",
}
RUTA_PROMPT = Path(__file__).resolve().parents[1] / "prompts" / "simulador.md"


def monto_coloquial(monto: float, moneda: str, factor: float = 1.0) -> str:
    """Como lo diría un cliente: 180 mil pesos, 45 dólares."""
    v = monto * factor
    if moneda in ("COP", "ARS") and v >= 1000:
        return f"{round(v / 1000)} mil pesos"
    if moneda == "USD":
        return f"{round(v)} dólares"
    return f"{round(v)} pesos"


def llenar(texto: str, datos: dict) -> str:
    return (texto.replace("{monto_aprox}", datos.get("monto_aprox", "un monto"))
            .replace("{monto_equivocado}", datos.get("monto_equivocado", "otro monto"))
            .replace("{comercio}", datos.get("comercio", "un comercio")))


class ClienteGuionizado:
    def __init__(self, caso: dict, max_turnos: int = 8, datos: dict | None = None):
        self.datos = datos or {}
        self.caso = caso
        self.max = max_turnos
        self.turno = 0
        self.primer = True
        self.dijo_no_puedo = False

    def siguiente(self, salida: dict | None) -> dict | None:
        """None = FIN. Devuelve {'texto'} | {'evento'} | {'identidad': True}."""
        self.turno += 1
        caso = self.caso
        if self.turno > self.max:
            return None
        if self.primer:
            self.primer = False
            if caso.get("evento", {}).get("tipo") == "no_reconozco_movimiento":
                return {"identidad": True, "luego": {"evento": {"tipo": "no_reconozco", "ref": "__objetivo__"}}}
            if caso.get("evento", {}).get("tipo") == "adjunto":
                return {"identidad": True, "luego": {"adjunto": caso["evento"]["archivo"]}}
            if "primer_mensaje" not in caso:
                return {"identidad": True, "luego": None}
            return {"texto": llenar(caso["primer_mensaje"], self.datos)}
        tipos = [u["tipo"] for u in salida.get("ui", [])]
        if "aviso_espera" in tipos or salida.get("sin_modelo"):
            return None
        if "formulario_identidad" in tipos:
            if caso["sesion"] == "con_identidad":
                return {"identidad": True}
            if not self.dijo_no_puedo and caso["id"] in ("C3", "D8"):     # quien no puede identificarse lo dice
                self.dijo_no_puedo = True
                return {"texto": "no puedo, no me llega ningún código"}
            return None
        if "tarjeta_cargo" in tipos and caso["id"] == "A3":          # al ver el detalle, lo reconoce
            return {"evento": {"tipo": "reconoce", "valor": "si"}}
        if "confirmacion" in tipos:
            u = next(u for u in salida["ui"] if u["tipo"] == "confirmacion")
            if caso.get("evento", {}).get("tipo") == "falla_modelo":
                return {"texto": "sí, ábrelo", "falla_modelo": True}
            if caso.get("evento", {}).get("tipo") == "sesion_vencida" and not getattr(self, "_vencio", False):
                self._vencio = True
                return {"evento": {"tipo": "confirmar", "action_intent_id": u["action_intent_id"]}, "sesion_vencida": True}
            return {"evento": {"tipo": "confirmar", "action_intent_id": u["action_intent_id"]},
                    "reenviar": caso.get("evento", {}).get("tipo") == "reenvio_mensaje"}
        if "opciones" in tipos:
            op = next(u for u in salida["ui"] if u["tipo"] == "opciones")["opciones"][0]
            return {"evento": {"tipo": "elegir", "alias": op["alias"]}}
        if "tarjeta_cargo" in tipos and salida.get("nodo") == "N5":
            reconoce = "si" if caso["id"] == "A3" else "no"
            return {"evento": {"tipo": "reconoce", "valor": reconoce}}
        # El "segundo mensaje" es la primera vez que el cliente tiene la palabra después de identificarse: el turno 2
        # es siempre el formulario de identidad, así que contar turnos no sirve.
        self._palabra = getattr(self, "_palabra", 0) + 1
        segundo = self._palabra == 1
        if caso["id"] == "B1" and segundo:                           # a la pregunta abierta, cuenta qué le pasa
            return {"texto": llenar("es que me salió un cobro de {monto_aprox} ayer que no hice", self.datos)}
        if caso["id"] == "V1" and self.turno <= 3:
            return {"texto": llenar("no, perdón, eran {monto_aprox}", self.datos)}
        if caso["id"] == "V3" and segundo:
            return {"texto": "oye, ¿y cuánto tarda en resolverse un reclamo?"}
        if caso["id"] == "V4" and segundo:
            self._en_portugues = True
            return {"texto": "desculpa, prefiro falar em português. Não reconheço uma compra de ontem"}
        if caso["id"] == "V6" and segundo:                           # escribe en español y elige portugués en el selector
            return {"evento": {"tipo": "cambiar_idioma", "idioma": "pt"}}
        if caso["id"] == "V7" and segundo:                           # la atienden en portugués y no lo entiende
            return {"texto": "no entiendo, yo hablo español, háblame en español"}
        if caso["id"] == "V2" and segundo:
            return {"texto": "bueno, igual quiero abrir un reclamo por un cargo de ayer que no hice"}
        if caso["id"] == "F4" and self.turno == 2 and salida.get("nodo") not in ("N7",):
            return None
        if salida.get("nodo") == "N4" and "opciones" not in tipos and self.datos.get("monto_aprox") and not getattr(self, "_dio_datos", False):
            self._dio_datos = True                                   # le piden datos del cargo: los da como los recuerda
            frase = "foi ontem, por {monto_aprox}" if getattr(self, "_en_portugues", False) else "fue ayer, por {monto_aprox}"
            return {"texto": llenar(frase, self.datos)}
        return None


class ClientePersonaje:
    """Un modelo de otra familia hace de cliente. Responde con texto o con una acción de la interfaz."""

    def __init__(self, caso: dict, modelo, max_turnos: int = 8, datos: dict | None = None):
        self.caso, self.modelo, self.max, self.datos = caso, modelo, max_turnos, datos or {}
        self.turno = 0
        self.historial: list[str] = []

    def siguiente(self, salida: dict | None) -> dict | None:
        self.turno += 1
        if self.turno > self.max:
            return None
        if salida is None:
            primero = llenar(self.caso.get("primer_mensaje", ""), self.datos)
            self.historial.append(f"CLIENTE: {primero}")
            return {"texto": primero} if "primer_mensaje" in self.caso else {"identidad": True}
        tipos = [u["tipo"] for u in salida.get("ui", [])]
        if "aviso_espera" in tipos:
            return None
        self.historial.append(f"ASISTENTE: {salida.get('texto', '')}  [interfaz: {', '.join(tipos) or 'nada'}]")
        sistema = RUTA_PROMPT.read_text(encoding="utf-8").replace("{{PERSONAJE}}", PERSONAJES[self.caso["personaje"]]) \
            .replace("{{META}}", self.caso["meta"]).replace("{{IDIOMA}}", self.caso["idioma"])
        r = self.modelo.completar(sistema, "\n".join(self.historial[-12:]), "simular")
        linea = r.texto.strip().splitlines()[0] if r.texto.strip() else "FIN"
        if linea.upper().startswith("FIN"):
            return None
        if linea.upper().startswith("ACCION:"):
            accion = linea.split(":", 1)[1].strip().lower()
            if accion.startswith("identificarme") and "formulario_identidad" in tipos and self.caso["sesion"] == "con_identidad":
                return {"identidad": True}
            if accion.startswith("confirmar") and "confirmacion" in tipos:
                u = next(u for u in salida["ui"] if u["tipo"] == "confirmacion")
                return {"evento": {"tipo": "confirmar", "action_intent_id": u["action_intent_id"]}}
            if accion.startswith("rechazar") and "confirmacion" in tipos:
                return {"evento": {"tipo": "negar"}}
            if accion.startswith("elegir") and "opciones" in tipos:
                op = next(u for u in salida["ui"] if u["tipo"] == "opciones")["opciones"][0]
                return {"evento": {"tipo": "elegir", "alias": op["alias"]}}
            if accion.startswith(("reconozco", "no_reconozco")) and "tarjeta_cargo" in tipos:
                return {"evento": {"tipo": "reconoce", "valor": "si" if accion.startswith("reconozco") else "no"}}
            return None
        texto = linea.split(":", 1)[1].strip() if linea.upper().startswith("TEXTO:") else linea
        self.historial.append(f"CLIENTE: {texto}")
        return {"texto": texto}
