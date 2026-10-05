"""A1 — Intérprete (CONTRATOS A1).

Arma el prompt desde el catálogo único (las partes del dominio no se escriben a mano, ARQUITECTURA §8.6), le pasa al
modelo el estado sin campos internos, la conversación con marcadores y el mensaje delimitado como dato no confiable,
y valida la salida. Si no parsea: un reintento con el error; si vuelve a fallar, la conversación pasa a una persona.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from contratos import catalogo
from contratos.modelos import EstadoConversacion, Interpretacion
from servicio.interprete.lector import SalidaInvalida, _del_catalogo, leer
from servicio.llm.cliente import Modelo, ModeloNoDisponible, RespuestaModelo, hash_texto

RUTA_PROMPT = Path(__file__).resolve().parents[2] / "prompts" / "interprete.md"
PRESUPUESTO_HISTORIAL_CARACTERES = 6000    # se fija con la medición del cupo (F-8); ARQUITECTURA §8.1 regla 1


class InterpretacionFallida(Exception):
    """Dos salidas inválidas seguidas o modelo no disponible: la conversación sigue sin modelo."""

    def __init__(self, motivo: str, llamadas: list[RespuestaModelo], entendible: bool = False):
        super().__init__(motivo)
        self.llamadas = llamadas
        self.entendible = entendible      # el modelo SÍ respondió, pero su salida no se pudo leer: se puede repreguntar al cliente


def _lista(d: dict) -> str:
    return "\n".join(f"- {k}: {v}" for k, v in d.items())


def prompt_sistema(temas: dict[str, str]) -> str:
    cat = catalogo.cargar()
    servicios = "\n".join(f"- {s}.{i}: {desc}" for s, d in cat["servicios"].items() for i, desc in d["intenciones"].items())
    return (RUTA_PROMPT.read_text(encoding="utf-8")
            .replace("{{COMANDOS}}", _lista(cat["comandos"]))
            .replace("{{SERVICIOS}}", servicios)
            .replace("{{CAMPOS}}", _lista(cat["campos"]))
            .replace("{{TIPOS_DISPUTA}}", _lista(cat["tipos_disputa"]))
            .replace("{{SENALES}}", _lista(cat["senales_riesgo"]))
            .replace("{{RECONOCE}}", "\n".join(f"  - {k}: {v}" for k, v in cat["reconoce"].items()))
            .replace("{{TEMAS}}", _lista(temas) if temas else "- (sin temas publicados)"))


def estado_para_modelo(estado: EstadoConversacion) -> dict:
    """El estado sin campos internos: nunca referencias internas ni valores reales de la cuenta (ARQUITECTURA §8.1)."""
    return {
        "nodo": estado.nodo.name,
        "ultima_pregunta": (estado.ultima_pregunta or {}).get("codigo"),
        "cargos": [{"alias": c.alias, "estado": c.estado} for c in estado.cargos],
        "opciones_mostradas": estado.opciones_mostradas,
        "accion_propuesta": ({"accion": estado.accion_pendiente.codigo, "sobre": estado.accion_pendiente.alias}
                             if estado.accion_pendiente else None),
        "datos_dados": {c: v[:200] for c, v in estado.datos_dados.items() if c in catalogo.cargar()["campos"]},   # lo que el cliente dijo, con su valor; las banderas internas no pasan
        "temas_pendientes": [t.get("tema") for t in estado.pila_temas],
        "identidad_verificada": estado.identidad_verificada,
    }


def conversacion_para_modelo(estado: EstadoConversacion, limite: int = PRESUPUESTO_HISTORIAL_CARACTERES) -> str:
    """Transcripción completa si cabe; si no, se compacta sin resumen: primer mensaje del cliente y turnos recientes."""
    turnos = [f"{t.rol.upper()}: {t.texto_con_marcadores}" for t in estado.historial]
    texto = "\n".join(turnos)
    if len(texto) <= limite:
        return texto or "(primer mensaje)"
    primero = next((t for t in turnos if t.startswith("CLIENTE")), "")
    recientes: list[str] = []
    total = len(primero)
    for t in reversed(turnos):
        if total + len(t) > limite:
            break
        recientes.insert(0, t)
        total += len(t)
    return "\n".join([primero, "(…turnos intermedios guardados en la base…)"] + recientes)


def mensaje_usuario(estado: EstadoConversacion, mensaje: str) -> str:
    return (f"ESTADO:\n{json.dumps(estado_para_modelo(estado), ensure_ascii=False)}\n\n"
            f"CONVERSACIÓN:\n{conversacion_para_modelo(estado)}\n\n"
            f"<<<MENSAJE\n{mensaje}\nMENSAJE>>>")


def _validar_temas(interp: Interpretacion, temas: dict[str, str]) -> None:
    """El tema de una consulta es un valor del catálogo de temas, como todo lo demás (lector estricto con el contenido):
    un tema inventado se corrige con un reintento; el argumento es opcional."""
    for k in interp.comandos:
        if k.nombre == "consulta_informativa" and k.args:
            if k.args[0] in temas:
                continue
            if not temas:                 # sin temas publicados no hay catálogo contra qué validar: se busca por texto
                k.args.clear()
                continue
            try:
                k.args[0] = _del_catalogo(k.args[0], sorted(temas), "tema de consulta_informativa")
            except SalidaInvalida as e:
                raise SalidaInvalida(f"{e} (o sin argumento)")


@dataclass
class ResultadoInterpretacion:
    interpretacion: Interpretacion
    llamadas: list[RespuestaModelo]
    hash_prompt: str
    reintentos: int


def interpretar(modelo: Modelo, estado: EstadoConversacion, mensaje: str, temas: dict[str, str]) -> ResultadoInterpretacion:
    sistema = prompt_sistema(temas)
    usuario = mensaje_usuario(estado, mensaje)
    llamadas: list[RespuestaModelo] = []
    error = None
    for intento in range(2):
        pedido = usuario if error is None else f"{usuario}\n\nCorrige la salida anterior: {error}."
        try:
            r = modelo.completar(sistema, pedido, "interpretar")
        except ModeloNoDisponible as e:
            raise InterpretacionFallida(f"modelo no disponible: {e}", llamadas)
        llamadas.append(r)
        try:
            interp = leer(r.texto)
            _validar_temas(interp, temas)
            return ResultadoInterpretacion(interp, llamadas, hash_texto(sistema), intento)
        except SalidaInvalida as e:
            error = str(e)
    raise InterpretacionFallida(f"salida inválida dos veces: {error}", llamadas, entendible=True)
