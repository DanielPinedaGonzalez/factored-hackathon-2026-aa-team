"""A4 — Motor de política: cuatro verificaciones antes de cada acción (ARQUITECTURA §8.3, CONTRATOS A4).

Función pura de `HechosVerificados` y de la versión de la política: misma entrada, misma salida, byte a byte. No lee
el mensaje, no llama al modelo y no recibe el segmento del cliente. Las verificaciones son restricciones, no pesos:
una acción es admisible solo si pasa las cuatro.
"""
from __future__ import annotations

import functools
import hashlib
import json
from datetime import date, timedelta
from pathlib import Path

import yaml

from contratos.modelos import DecisionPolitica, HechosVerificados, Verificacion
from servicio.resolutor.calendario import sumar_dias_habiles

RAIZ = Path(__file__).resolve().parents[2] / "politica"
PAISES = ("MX", "CO", "AR")
_OBLIGATORIOS_REGLA = {"nombre", "condicion", "accion", "excepciones", "fuente", "version", "vigente_desde",
                       "verificada_el", "prueba"}


class PoliticaInvalida(Exception):
    pass


@functools.lru_cache(maxsize=1)
def cargar() -> dict:
    comun = yaml.safe_load((RAIZ / "comun.yaml").read_text(encoding="utf-8"))
    for regla in comun.get("reglas", []):
        faltan = _OBLIGATORIOS_REGLA - set(regla)
        if faltan:
            raise PoliticaInvalida(f"regla {regla.get('nombre')} sin {sorted(faltan)}")
    paises = {}
    for p in PAISES:
        datos = yaml.safe_load((RAIZ / f"{p.lower()}.yaml").read_text(encoding="utf-8"))
        sin_fuente = [k for k in ("umbral_monto_usd", "ventana_reclamo_dias", "ventana_investigacion_dias")
                      if k not in datos.get("fuentes", {})]
        if sin_fuente:
            raise PoliticaInvalida(f"{p}: cifras sin fuente {sin_fuente}")
        paises[p] = datos
    return {"comun": comun, "paises": paises}


def hash_politica() -> str:
    h = hashlib.sha256()
    for f in sorted(RAIZ.glob("*.yaml")):
        h.update(f.read_bytes())
    return h.hexdigest()[:12]


def version_politica() -> str:
    return cargar()["comun"]["version"]


def plazo_normativo(pais: str | None, desde: date) -> dict | None:
    """Plazo de investigación del país, con su fuente. None si la jurisdicción es desconocida."""
    if pais not in PAISES:
        return None
    p = cargar()["paises"][pais]
    dias = p["ventana_investigacion_dias"]
    vence = sumar_dias_habiles(desde, dias, pais) if p["plazo_tipo"] == "habiles" else desde + timedelta(days=dias)
    return {"dias": dias, "tipo": p["plazo_tipo"], "vence": vence.isoformat(),
            "fuente": p["fuentes"]["ventana_investigacion_dias"]}


def _certeza(h: HechosVerificados, accion: str) -> tuple[float, dict]:
    autenticacion = 1.0 if h.autenticado else 0.0
    identificacion = 1.0 if (h.candidatos == 1 and h.cargo_confirmado) else 0.0
    partes = {"autenticacion": autenticacion}
    if accion in ("abrir_reclamo",):
        partes["identificacion_cargo"] = identificacion
    if accion == "bloquear_producto" and h.recomendacion_del_sistema:
        partes["umbral_certificado"] = (1.0 - h.cota_fdr) if (h.supera_umbral_certificado and h.cota_fdr is not None) else 0.0
    return min(partes.values()), partes


def decidir(h: HechosVerificados, hoy: date) -> DecisionPolitica:
    pol = cargar()
    comun = pol["comun"]
    accion = h.accion
    pais = h.jurisdiccion if h.jurisdiccion in PAISES else None
    motivos: list[str] = []

    # V1 · irreversibilidad frente a certeza
    irr = comun["irreversibilidad"].get(accion, {"valor": 1.0})["valor"]
    certeza, partes = _certeza(h, accion)
    v1_ok = certeza > 0 and irr <= certeza       # sin ninguna certeza no se actúa, aunque la acción sea reversible
    v1 = Verificacion(id="V1", cumple=v1_ok,
                      numeros={"irreversibilidad": irr, "certeza": certeza, **partes},
                      razon="La acción se deshace a un costo menor que la certeza que tenemos." if v1_ok
                      else "No hay certeza suficiente para una acción de esta irreversibilidad.")

    # V2 · mismo caso, mismo trato: la decisión es función de estos hechos y de esta versión; se registra su huella
    huella = hashlib.sha256(h.model_dump_json().encode()).hexdigest()[:12]
    v2 = Verificacion(id="V2", cumple=True, numeros={"huella_hechos": huella, "version": comun["version"]},
                      razon="La decisión depende solo de los hechos verificados y de la versión de la política.")

    # V3 · corrección y persona disponibles: lo que debe ver una persona
    seguridad = sorted(set(h.senales_riesgo) & set(comun["senales_seguridad"]))
    humano: list[str] = []
    if accion in ("abrir_reclamo",):
        if pais is None:
            humano.append("jurisdiccion_desconocida")
        if h.monto_usd is None:
            humano.append("monto_desconocido")
        elif pais and h.monto_usd >= pol["paises"][pais]["umbral_monto_usd"]:
            humano.append("monto_sobre_umbral")
        if h.senal_riesgo_p is None:
            humano.append("sin_score")
        elif h.supera_umbral_certificado:
            humano.append("senal_sobre_umbral")
        elif h.senal_riesgo_p >= comun["zona_incertidumbre_p_min"]:
            humano.append("senal_en_zona_de_incertidumbre")
        if h.reclamos_previos_90d >= comun["tope_reclamos_90_dias"]:
            humano.append("reclamos_previos")
        if not h.moneda_pais_coherente:
            humano.append("moneda_incoherente")
        if h.tipo_disputa in comun["tipos_siempre_humanos"]:
            humano.append("tipo_siempre_humano")
        if pais and h.dias_desde_transaccion is not None and h.dias_desde_transaccion > pol["paises"][pais]["ventana_reclamo_dias"]:
            humano.append("fuera_de_ventana")
        if seguridad:
            humano.append("senal_de_seguridad")
    if accion == "desbloquear_producto" and (not h.bloqueo_pedido_por_cliente or h.senales_riesgo):
        humano.append("desbloqueo_tras_riesgo")
    if accion == "abono":
        humano.append("accion_de_dinero")
    v3 = Verificacion(id="V3", cumple=not humano, numeros={"motivos": ",".join(humano) or None},
                      razon="Nada exige que lo vea una persona." if not humano else "Una persona debe revisarlo.")

    # V4 · cuidar la relación: el sistema solo recomienda bloquear con el umbral certificado
    v4_ok = True
    if accion == "bloquear_producto" and h.recomendacion_del_sistema:
        v4_ok = bool(h.supera_umbral_certificado and h.cota_fdr is not None and h.cota_fdr <= comun["fdr_maximo_recomendacion"])
    v4 = Verificacion(id="V4", cumple=v4_ok, numeros={"cota_fdr": h.cota_fdr, "fdr_maximo": comun["fdr_maximo_recomendacion"]},
                      razon="La conversación deja las opciones del cliente intactas." if v4_ok
                      else "El sistema no recomienda un bloqueo sin el umbral certificado.")

    verifs = [v1, v2, v3, v4]
    sin_cobro = h.estado_transaccion in comun["estados_sin_cobro"]
    if accion == "abrir_reclamo" and sin_cobro and v1.cumple:
        motivos.append("sin_cobro")
        permitidas = ["bloquear_producto"]
        camino = "automatizable"
    elif all(v.cumple for v in verifs):
        camino, permitidas = "automatizable", [accion]
    elif not v1.cumple and accion == "abrir_reclamo" and h.autenticado:
        camino, permitidas = "abstencion", []        # falta identificar el cargo: se vuelve a aclarar
        motivos.append("cargo_no_identificado")
    else:
        camino, permitidas = "revision_humana", []
        motivos += humano or ["verificacion_no_cumplida"]
    if accion == "abrir_reclamo" and h.autenticado and "bloquear_producto" not in permitidas:
        permitidas.append("bloquear_producto")      # bloquear a pedido siempre está disponible (PROCESOS §P4)
    return DecisionPolitica(camino=camino, acciones_permitidas=permitidas, verificaciones=verifs, motivos=motivos,
                            plazo_normativo=plazo_normativo(pais, hoy) if accion == "abrir_reclamo" else None,
                            version_politica=comun["version"], hash_politica=hash_politica())


def resumen_para_json(d: DecisionPolitica) -> str:
    return json.dumps(d.model_dump(mode="json"), ensure_ascii=False, sort_keys=True)
