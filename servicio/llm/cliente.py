"""Clientes de modelos de lenguaje: proveedor real (API compatible con OpenAI), puente de archivos y falso.

Todo modelo usado debe estar en el inventario (GOBERNANZA §8.1). Cada llamada pasa por el guardián de cupo (A12) y
devuelve su consumo para `operacion.consumo_modelos`. El puente de archivos es la forma por defecto de desarrollar:
el asistente de desarrollo hace de modelo, sin gastar cupo (adaptado de un sistema propio del autor).
"""
from __future__ import annotations

import hashlib
import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Protocol

import httpx

from servicio.recursos.guardian import CircuitoAbierto, CupoAgotado, Guardian

TEMPERATURA_BASE = 0.2                              # la de toda tarea que no declare otra (el Redactor, entre ellas)

INVENTARIO = {
    "openai/gpt-oss-120b",        # sistema: Intérprete, Redactor, asistencia al asesor (Groq)
    "openai/gpt-oss-20b",         # alternativa medida del sistema (Groq)
    "llama-3.3-70b-versatile",    # alternativa medida del sistema (Groq)
    "qwen/qwen3.8-27b",           # simulador de clientes (Groq, familia distinta del sistema)
    "nvidia/nemotron-3-super-120b-a12b:free",   # respaldo de la demo en OpenRouter cuando Groq cae (config/llaves.yaml)
    "puente",                     # el asistente de desarrollo haciendo de modelo
    "falso",                      # pruebas deterministas
}


class ModeloNoDisponible(Exception):
    """Falla del proveedor, cupo agotado o circuito abierto: la conversación sigue sin modelo. El mensaje lleva la
    razón real (código, mensaje del proveedor, límite), que queda registrada; al cliente nunca le llega."""


class RespuestaCortada(ModeloNoDisponible):
    """El proveedor cortó la respuesta por el límite de tokens: el texto está incompleto y no se usa. La llave está
    sana (no es un problema de cupo): se prueba el siguiente proveedor sin enfriarla."""


def _razon_del_proveedor(r) -> str:
    """El mensaje de error que devuelve el proveedor, sin la llave: es la razón real del fallo."""
    try:
        cuerpo = r.json()
        err = cuerpo.get("error", cuerpo)
        msg = err.get("message") if isinstance(err, dict) else str(err)
    except Exception:
        msg = r.text
    return (msg or "").replace("\n", " ")[:400]


def _registrar(**fila) -> None:
    from servicio.registro.consumo import registrar_llamada
    registrar_llamada(**fila)


@dataclass
class RespuestaModelo:
    texto: str
    proveedor: str
    modelo: str
    tokens_entrada: int = 0
    tokens_salida: int = 0
    latencia_ms: float = 0.0
    request_id: str | None = None
    cupo: dict = field(default_factory=dict)
    espera_s: float = 0.0
    proposito: str = ""          # interpretar | redactar | sugerir | ...: qué componente hizo la llamada (A13)
    llave: int | None = None     # índice de la llave del pool que respondió (nunca la llave)


class Modelo(Protocol):
    nombre: str

    def completar(self, sistema: str, usuario: str, proposito: str, max_tokens: int = 900) -> RespuestaModelo: ...


def _estimar_tokens(*textos: str) -> int:
    return sum(len(t) for t in textos) // 3 + 50


def hash_texto(t: str) -> str:
    return hashlib.sha256(t.encode()).hexdigest()[:12]


class ProveedorOpenAI:
    """Groq u OpenRouter por su API compatible. Un guardián por llave."""

    URLS = {"groq": "https://api.groq.com/openai/v1/chat/completions",
            "openrouter": "https://openrouter.ai/api/v1/chat/completions"}

    def __init__(self, proveedor: str, modelo: str, llave: str, guardian: Guardian | None = None,
                 temperatura: float = TEMPERATURA_BASE, timeout_s: float = 30.0, cero_retencion: bool = True):
        if modelo not in INVENTARIO:
            raise ValueError(f"modelo fuera del inventario: {modelo}")
        self.proveedor, self.nombre, self._llave = proveedor, modelo, llave
        self.familia = proveedor.split("_")[0]      # «openrouter_pago» es OpenRouter con otra ficha de llaves: el registro los distingue, la API es la misma
        self.guardian = guardian or Guardian()
        self.temperatura, self.timeout_s, self.cero_retencion = temperatura, timeout_s, cero_retencion

    def completar(self, sistema: str, usuario: str, proposito: str, max_tokens: int = 900) -> RespuestaModelo:
        base = {"proveedor": self.proveedor, "modelo": self.nombre, "proposito": proposito, "sistema": sistema,
                "llave": getattr(self, "indice_llave", None), "tamano_mensaje": len(usuario)}
        try:
            espera = self.guardian.antes_de_llamar(_estimar_tokens(sistema, usuario) + max_tokens)
        except (CupoAgotado, CircuitoAbierto) as e:
            razon = f"{type(e).__name__}: {e} (guardián local, sin llamar al proveedor)"
            _registrar(**base, exito=False, error=razon)
            raise ModeloNoDisponible(razon) from e
        cuerpo = {"model": self.nombre, "temperature": self.temperatura, "max_tokens": max_tokens,
                  "messages": [{"role": "system", "content": sistema}, {"role": "user", "content": usuario}]}
        if self.familia == "openrouter" and self.cero_retencion:
            cuerpo["provider"] = {"data_collection": "deny", "zdr": True}
        if self.familia == "groq" and self.nombre.startswith("qwen/"):
            cuerpo["reasoning_effort"] = "none"
        if (self.familia == "groq" and self.nombre.startswith("openai/gpt-oss")) or self.familia == "openrouter":
            # Modelos que razonan antes de responder: el razonamiento gasta del mismo presupuesto de salida.
            # Interpretar pide más razonamiento (medido: con "low" a veces omite una señal de riesgo); redactar, poco.
            defecto = "medium" if proposito == "interpretar" else "low"
            esfuerzo = os.environ.get("RAZONAMIENTO_" + proposito.upper(), defecto)
            if self.familia == "groq":
                cuerpo["reasoning_effort"] = esfuerzo
            else:
                cuerpo["reasoning"] = {"effort": esfuerzo, "exclude": True}
            # El respaldo de OpenRouter razona más largo (medido el 27-sep: con 1.200 se cortó al redactar).
            piso = 4000 if self.familia == "openrouter" else 2000 if proposito == "interpretar" else 1200
            cuerpo["max_tokens"] = max(max_tokens, piso)
        t0 = time.monotonic()
        try:
            r = httpx.post(self.URLS[self.familia], json=cuerpo, timeout=self.timeout_s,
                           headers={"Authorization": f"Bearer {self._llave}"})
        except httpx.HTTPError as e:
            self.guardian.registrar_resultado(False)
            razon = f"red: {type(e).__name__}: {e}"[:400]
            _registrar(**base, exito=False, error=razon, latencia_ms=(time.monotonic() - t0) * 1000, espera_s=espera)
            raise ModeloNoDisponible(razon) from e
        latencia = (time.monotonic() - t0) * 1000
        self.guardian.registrar_cabeceras(dict(r.headers))
        cupo = {"peticiones_restantes": self.guardian.estado.peticiones_restantes,
                "tokens_restantes": self.guardian.estado.tokens_restantes}
        if r.status_code >= 400:
            reintentar = float(r.headers.get("retry-after", 30)) if r.status_code == 429 else None
            self.guardian.registrar_resultado(False, reintentar)
            razon = f"{r.status_code} {_razon_del_proveedor(r)}" + (f" (reintentar en {reintentar:.0f}s)" if reintentar else "")
            _registrar(**base, exito=False, error=razon, http_estado=r.status_code, latencia_ms=latencia, espera_s=espera,
                       request_id=r.headers.get("x-request-id"), cupo=cupo)
            raise ModeloNoDisponible(razon)
        try:
            datos = r.json()
            uso = datos.get("usage") or {}
            texto = (datos["choices"][0]["message"].get("content") or "").strip()
            cortada = datos["choices"][0].get("finish_reason") == "length"
        except Exception as e:                        # respuesta 200 sin el formato esperado: también es una falla
            self.guardian.registrar_resultado(False)
            razon = f"respuesta sin formato: {type(e).__name__}: {r.text[:300]}"
            _registrar(**base, exito=False, error=razon, http_estado=r.status_code, latencia_ms=latencia, espera_s=espera,
                       request_id=r.headers.get("x-request-id"), cupo=cupo)
            raise ModeloNoDisponible(razon) from e
        if cortada:
            razon = (f"respuesta cortada por el límite de {cuerpo['max_tokens']} tokens de salida "
                     f"({uso.get('completion_tokens', 0)} usados): el texto está incompleto")
            _registrar(**base, exito=False, error=razon, http_estado=r.status_code, latencia_ms=latencia, espera_s=espera,
                       tokens_entrada=uso.get("prompt_tokens", 0), tokens_salida=uso.get("completion_tokens", 0),
                       request_id=r.headers.get("x-request-id"), cupo=cupo)
            raise RespuestaCortada(razon)
        self.guardian.registrar_resultado(True)
        _registrar(**base, exito=True, latencia_ms=latencia, espera_s=espera, tokens_entrada=uso.get("prompt_tokens", 0),
                   tokens_salida=uso.get("completion_tokens", 0), request_id=r.headers.get("x-request-id"), cupo=cupo)
        return RespuestaModelo(texto, self.proveedor, self.nombre, uso.get("prompt_tokens", 0),
                               uso.get("completion_tokens", 0), latencia, r.headers.get("x-request-id"), cupo,
                               espera, proposito)


class PuenteArchivos:
    """Escribe el prompt en `prompt_NN.txt` y espera `respuesta_NN.txt`. Solo para desarrollo."""

    nombre = "puente"

    def __init__(self, carpeta: str | Path, timeout_s: int = 1800):
        self.carpeta = Path(carpeta)
        self.carpeta.mkdir(parents=True, exist_ok=True)
        self.timeout_s = timeout_s
        existentes = sorted(self.carpeta.glob("prompt_*.txt"))
        self._n = int(existentes[-1].stem.split("_")[1]) if existentes else 0

    def completar(self, sistema: str, usuario: str, proposito: str, max_tokens: int = 900) -> RespuestaModelo:
        self._n += 1
        pedido = self.carpeta / f"prompt_{self._n:03d}.txt"
        respuesta = self.carpeta / f"respuesta_{self._n:03d}.txt"
        pedido.write_text(f"=== PROPÓSITO: {proposito} ===\n\n=== SISTEMA ===\n{sistema}\n\n=== USUARIO ===\n{usuario}\n",
                          encoding="utf-8")
        t0 = time.monotonic()
        while not respuesta.exists():
            if time.monotonic() - t0 > self.timeout_s:
                _registrar(proveedor="puente", modelo="puente", proposito=proposito, sistema=sistema, exito=False,
                           error=f"puente sin respuesta en {respuesta}")
                raise ModeloNoDisponible(f"puente sin respuesta en {respuesta}")
            time.sleep(0.5)
        time.sleep(0.2)
        texto = respuesta.read_text(encoding="utf-8").strip()
        if texto == "FALLA":
            _registrar(proveedor="puente", modelo="puente", proposito=proposito, sistema=sistema, exito=False,
                       error="falla inyectada por el puente")
            raise ModeloNoDisponible("falla inyectada por el puente")
        r = RespuestaModelo(texto, "puente", "puente", _estimar_tokens(sistema, usuario), len(texto) // 3,
                            (time.monotonic() - t0) * 1000, proposito=proposito)
        _registrar(proveedor="puente", modelo="puente", proposito=proposito, sistema=sistema, exito=True,
                   latencia_ms=r.latencia_ms, tokens_entrada=r.tokens_entrada, tokens_salida=r.tokens_salida)
        return r


class ModeloFalso:
    """Respuestas programadas para pruebas. `guion(sistema, usuario, proposito) -> texto` o una lista en orden."""

    nombre = "falso"

    def __init__(self, guion: list[str] | Callable[[str, str, str], str]):
        self._guion = guion
        self.llamadas: list[dict] = []

    def completar(self, sistema: str, usuario: str, proposito: str, max_tokens: int = 900) -> RespuestaModelo:
        self.llamadas.append({"proposito": proposito, "sistema": sistema, "usuario": usuario})
        if callable(self._guion):
            texto = self._guion(sistema, usuario, proposito)
        else:
            if not self._guion:
                _registrar(proveedor="falso", modelo="falso", proposito=proposito, sistema=sistema, exito=False, error="guion agotado")
                raise ModeloNoDisponible("guion agotado")
            texto = self._guion.pop(0)
        if texto is None or texto == "FALLA":
            _registrar(proveedor="falso", modelo="falso", proposito=proposito, sistema=sistema, exito=False, error="falla programada")
            raise ModeloNoDisponible("falla programada")
        r = RespuestaModelo(texto, "falso", "falso", _estimar_tokens(sistema, usuario), len(texto) // 3, 1.0, proposito=proposito)
        _registrar(proveedor="falso", modelo="falso", proposito=proposito, sistema=sistema, exito=True, latencia_ms=1.0,
                   tokens_entrada=r.tokens_entrada, tokens_salida=r.tokens_salida)
        return r


def _llaves(prefijo: str) -> list[str]:
    return [v for k, v in sorted(os.environ.items()) if k.startswith(prefijo) and v]


TEMPERATURAS_SISTEMA = {"interpretar": 0.0}       # el Intérprete describe: sin azar


def modelos_del_sistema() -> dict[str, str]:
    """Qué modelo hace cada tarea del sistema; una sola fuente para el cliente y para la huella de cada corrida."""
    return {"interpretar": os.environ.get("MODELO_INTERPRETE", "openai/gpt-oss-120b"),
            "redactar": os.environ.get("MODELO_REDACTOR", "openai/gpt-oss-120b")}


def modelo_desde_entorno(rol: str = "sistema") -> Modelo:
    """MODELO_MODO = puente | groq | openrouter. Por defecto, el puente (desarrollo sin gastar cupo)."""
    modo = os.environ.get("MODELO_MODO", "puente")
    if modo == "puente":
        return PuenteArchivos(os.environ.get("PUENTE_DIR", "/tmp/puente_aa"))
    if modo == "groq":            # pool de llaves con un guardián por llave (servicio/llm/pool.py)
        from servicio.llm.pool import PoolLlaves, llaves_del_papel, registrar_pool
        llaves = llaves_del_papel(rol)                # config/llaves.yaml: cada papel con su cupo; (nombre de la variable, llave)
        modelos = modelos_del_sistema()
        from servicio.llm.pool import CadenaProveedores, reparto
        from servicio.registro.consumo import enfriamientos_vigentes
        orden = reparto().get("orden_sistema", ["groq"]) if rol == "sistema" else ["groq"]
        pools = []
        for proveedor in orden:
            if proveedor == "groq":
                if not llaves:
                    continue
                lotes = rol in ("evaluacion", "linea_base")      # sin cliente esperando: puede esperar el cupo
                p = PoolLlaves("groq", [v for _, v in llaves], modelos, modelos["interpretar"], nombres=[n for n, _ in llaves],
                               espacio_s=float(os.environ.get("ESPACIO_LLAMADAS_S", "2")), temperaturas=TEMPERATURAS_SISTEMA,
                               espera_guardian_s=60.0 if lotes else 0.0,
                               espera_saturado_s=65.0 if lotes else float(os.environ.get("ESPERA_SATURADO_S", "15")))     # un cliente espera unos segundos a que se libere una llave antes de pasar a una persona
            else:                    # respaldo: su propio pool, con el modelo y la privacidad declarados en la ficha
                ficha = reparto()[proveedor]
                propias = [(n, os.environ[n].strip()) for n in ficha["llaves"] if len((os.environ.get(n) or "").strip()) >= 20]     # un relleno («.») no es una llave
                if not propias:
                    continue
                p = PoolLlaves(proveedor, [v for _, v in propias], {}, ficha["modelo"], nombres=[n for n, _ in propias], espacio_s=3.0,
                               cero_retencion=ficha.get("cero_retencion", True))
            p.cargar_enfriamientos(enfriamientos_vigentes(proveedor))   # el estado sobrevive a un reinicio
            pools.append(p)
        if not pools:                # sin ninguna llave: la conversación pasa a una persona; la cabina lo dice
            from servicio.llm.pool import SinLlaves
            nombres = reparto().get(rol, []) + [n for pr in orden if pr != "groq" for n in reparto()[pr]["llaves"]]
            return registrar_pool(SinLlaves(nombres))
        return registrar_pool(pools[0] if len(pools) == 1 else CadenaProveedores(pools))
    if modo == "simulador":       # E1: otra familia, otra llave (simulación, separada del sistema)
        from servicio.llm.pool import llaves_del_papel
        return ProveedorOpenAI("groq", os.environ.get("MODELO_SIMULADOR", "qwen/qwen3.8-27b"), llaves_del_papel("simulador")[0][1],
                               Guardian(espacio_min_s=3.0, espera_max_s=60), temperatura=0.8)
    raise ValueError(f"MODELO_MODO desconocido: {modo}")


def a_json(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, default=str)


class ModeloPorProposito:
    """Un modelo por rol (p. ej. interpretar con uno y redactar con otro): cada modelo tiene su propio cupo."""

    def __init__(self, por_proposito: dict, defecto: Modelo):
        self.por_proposito, self.defecto = por_proposito, defecto
        self.nombre = "+".join(sorted({m.nombre for m in [*por_proposito.values(), defecto]}))

    def completar(self, sistema: str, usuario: str, proposito: str, max_tokens: int = 900) -> RespuestaModelo:
        return self.por_proposito.get(proposito, self.defecto).completar(sistema, usuario, proposito, max_tokens)


class ModeloQueFalla:
    """Inyección de fallas para la evaluación: las próximas `n` llamadas fallan como un proveedor caído."""

    def __init__(self, base: Modelo, n: int = 99):
        self.base, self.n, self.nombre = base, n, base.nombre

    def completar(self, sistema: str, usuario: str, proposito: str, max_tokens: int = 900) -> RespuestaModelo:
        if self.n > 0:
            self.n -= 1
            _registrar(proveedor="evaluacion", modelo=self.nombre, proposito=proposito, sistema=sistema, exito=False,
                       error="falla inyectada por la evaluación")
            raise ModeloNoDisponible("falla inyectada por la evaluación")
        return self.base.completar(sistema, usuario, proposito, max_tokens)
