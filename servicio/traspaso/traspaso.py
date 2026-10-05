"""A10 — Traspaso (CONTRATOS A10 y `PaqueteTraspaso`) y A11 — enrutamiento sin modelo.

El paquete lleva lo verificado, lo hecho, la evidencia (solo para el asesor) y lo que queda abierto; nunca la
transcripción cruda (se enlaza). La habilidad sale de los motivos (PROCESOS §P2.2) y la prioridad de las señales y
del plazo (§P2.3). Sin modelo, A11 hace lo mismo con lo que el estado ya sabe: no lee ni interpreta el texto.
"""
from __future__ import annotations

import functools
import json
from datetime import date
from pathlib import Path

from contratos import catalogo
from contratos.modelos import EstadoConversacion, Nodo, PaqueteTraspaso
from servicio.resolutor.calendario import dias_habiles_entre
from contratos.idiomas import normalizar

SEGURIDAD = {"engano_por_tercero", "coaccion", "credencial_comprometida", "producto_en_manos_de_otro"}
ARTEFACTO_DINERO = Path(__file__).resolve().parents[2] / "artefactos" / "dinero_en_juego.json"


@functools.lru_cache(maxsize=1)
def _umbrales() -> dict:
    return json.loads(ARTEFACTO_DINERO.read_text(encoding="utf-8"))


def dinero_en_juego(tipo: str | None, monto_usd) -> dict | None:
    """El monto está en el tramo alto de su tipo (cuantil de la política, calculado de los datos): daño posible para
    el cliente. No es una señal de fraude. Devuelve la evidencia para el asesor, o None."""
    fila = _umbrales()["por_tipo"].get(tipo or "")
    if not fila or monto_usd is None or float(monto_usd) < fila["umbral_usd"]:
        return None
    return {"monto_usd": float(monto_usd), "umbral_usd": fila["umbral_usd"], "tipo": tipo, "cuantil": _umbrales()["cuantil"]}


def prioridad(senales: list[str], motivos: list[str], supera_umbral: bool, plazo_vence: str | None, pais: str | None,
              hoy: date, dinero_en_juego: bool = False) -> int:
    if SEGURIDAD & set(senales) or "codigos_fallidos" in motivos or supera_umbral:
        return 1
    if "vulnerabilidad_declarada" in senales:
        return 2
    if plazo_vence and pais and dias_habiles_entre(hoy, date.fromisoformat(plazo_vence), pais) <= 2:
        return 3
    if dinero_en_juego:
        return 3
    return 4


def motivos_de_senales(senales: list[str]) -> list[str]:
    return [s for s in senales if s in catalogo.cargar()["motivos_traspaso"]]


def armar_paquete(estado: EstadoConversacion, motivos: list[str], hechos: list[dict], acciones: list[dict],
                  evidencia: dict, preguntas: list[str], supera_umbral: bool, plazo: dict | None, pais: str | None,
                  hoy: date, solicitud: str | None, sin_resumen: bool, dinero_en_juego: bool = False) -> PaqueteTraspaso:
    motivos = list(dict.fromkeys(motivos + motivos_de_senales(estado.senales_riesgo)))
    if not estado.identidad_verificada and "identidad_no_verificada" not in motivos:
        motivos.append("identidad_no_verificada")
    servicio = estado.pila_temas[-1]["tema"] if estado.pila_temas else None
    return PaqueteTraspaso(
        motivo_traspaso=motivos, solicitud=None if sin_resumen else solicitud, sin_resumen_ia=sin_resumen,
        servicio_intencion=servicio, adjuntos=[a.adjunto_id for a in estado.adjuntos], hechos_verificados=hechos,
        acciones_realizadas=acciones,
        accion_pendiente=({"accion": estado.accion_pendiente.codigo, "sobre": estado.accion_pendiente.alias,
                           "estado": "propuesta, sin ejecutar"} if estado.accion_pendiente else None),
        evidencia=evidencia, preguntas_abiertas=preguntas, idioma=normalizar(estado.idioma),
        prioridad=prioridad(estado.senales_riesgo, motivos, supera_umbral, (plazo or {}).get("vence"), pais, hoy,
                            dinero_en_juego),
        habilidad_requerida=catalogo.habilidad_de(motivos), plazo_normativo=plazo,
        identidad_verificada=estado.identidad_verificada, conversation_id=estado.conversation_id)


def enrutar_sin_modelo(estado: EstadoConversacion) -> list[str]:
    """A11: motivos del traspaso solo con el estado (nodo, cargo en curso, tema apilado, señales)."""
    motivos = ["sin_modelo"] + motivos_de_senales(estado.senales_riesgo)
    tema = estado.pila_temas[-1]["tema"] if estado.pila_temas else None
    if tema == "disputas.reportar_cargo" or estado.nodo in (Nodo.N5, Nodo.N6, Nodo.N7):
        motivos.append("fraude_no_automatizable" if estado.tipo_disputa in ("no_autorizada", "estafa_autorizada")
                       else "revision_humana_politica")
    if tema in ("tarjetas.desbloquear",):
        motivos.append("desbloqueo_tras_riesgo")
    return motivos
