"""A12 — Pool de llaves del proveedor (diseño adaptado de un sistema propio del autor).

- Llaves de `GROQ_API_KEY` y `GROQ_API_KEY_2` … `GROQ_API_KEY_5` (misma convención de sufijos).
- Un guardián de cupo por llave, compartido por todos los componentes: el Intérprete y el Redactor ven el mismo
  límite por minuto de esa llave.
- Selección LRU: la llave disponible que lleva más tiempo sin usarse.
- Nadie espera: una llave que recibe 429, abre su circuito o necesitaría una pausa queda en enfriamiento y la llamada
  pasa a la siguiente en milisegundos (el guardián de cada llave no duerme dentro del pool). Con todas en
  enfriamiento el estado es SATURADO y falla de inmediato: responde el siguiente proveedor de la cadena y, si ninguno,
  la conversación pasa a una persona (ARQUITECTURA §8.4). Esperar solo tiene sentido en un proceso por lotes sin
  cliente (la evaluación), y lo decide ese proceso.
- Estados formales: NOMINAL (todas disponibles), DEGRADADO (alguna en enfriamiento), SATURADO (ninguna disponible).
- `estado()` alimenta el tablero del sistema. Las llaves se muestran solo por el nombre de su variable de entorno: ni un fragmento del valor.
"""
from __future__ import annotations

import os
import threading
import time
from dataclasses import dataclass, field

from servicio.llm.cliente import TEMPERATURA_BASE, ModeloNoDisponible, ProveedorOpenAI, RespuestaCortada, RespuestaModelo
from servicio.recursos.guardian import Guardian

SUFIJOS = ("", "_1", "_2", "_3", "_4", "_5")


def _parece_llave(v: str) -> bool:
    """Un valor de relleno («.», «x») que se puso para dejar una variable sin llave no es una llave: no cuenta como una que falla."""
    return len(v) >= 20


def llaves_del_entorno(prefijo: str = "GROQ_API_KEY") -> list[tuple[str, str]]:
    """(nombre de la variable, llave) de las llaves del entorno, sin repetir valores."""
    vistas: list[tuple[str, str]] = []
    for s in SUFIJOS:
        v = (os.environ.get(prefijo + s) or "").strip()
        if _parece_llave(v) and v not in [x for _, x in vistas]:
            vistas.append((prefijo + s, v))
    return vistas


def reparto() -> dict:
    import yaml
    from pathlib import Path
    return yaml.safe_load((Path(__file__).resolve().parents[2] / "config" / "llaves.yaml").read_text(encoding="utf-8"))


def llaves_del_papel(papel: str) -> list[tuple[str, str]]:
    """(nombre de la variable, llave) de las llaves de Groq de un papel según `config/llaves.yaml`; si ese papel no tiene ninguna en el entorno
    (p. ej. en el despliegue, que trae solo las suyas), todas las del entorno. El nombre es lo único que se muestra o se registra de una llave."""
    propias = [(n, os.environ[n].strip()) for n in reparto().get(papel, []) if _parece_llave((os.environ.get(n) or "").strip())]
    vistas: list[tuple[str, str]] = []
    for n, v in propias:
        if v not in [x for _, x in vistas]:
            vistas.append((n, v))
    return vistas or llaves_del_entorno()


@dataclass
class _Llave:
    llave: str
    indice: int
    guardian: Guardian
    nombre: str = ""            # nombre de la variable de entorno: lo único de la llave que sale del proceso
    ultimo_uso: float = 0.0
    llamadas: int = 0
    fallos: int = 0
    ultimo_error: str | None = None
    enfriada_hasta: float = 0.0
    proveedores: dict = field(default_factory=dict)

    @property
    def disponible(self) -> bool:
        return time.monotonic() >= self.enfriada_hasta and not self.guardian.abierto

    def publica(self) -> dict:
        e = self.guardian.estado
        return {"llave": self.nombre or f"llave {self.indice}", "indice": self.indice, "disponible": self.disponible,
                "enfriada_s": max(0, round(self.enfriada_hasta - time.monotonic())),
                "peticiones_restantes_dia": e.peticiones_restantes, "tokens_restantes_minuto": e.tokens_restantes,
                "llamadas": self.llamadas, "fallos": self.fallos, "ultimo_error": self.ultimo_error,
                "ultimo_uso_hace_s": round(time.monotonic() - self.ultimo_uso) if self.ultimo_uso else None}


class PoolLlaves:
    """Cumple el protocolo `Modelo`: `completar(sistema, usuario, proposito, max_tokens)`."""

    def __init__(self, proveedor: str, llaves: list[str], modelos: dict[str, str], defecto: str,
                 espacio_s: float = 4.0, enfriamiento_s: float = 60.0, temperaturas: dict[str, float] | None = None,
                 espera_saturado_s: float = 0.0, reintentos_saturado: int = 2, cero_retencion: bool = True,
                 espera_guardian_s: float = 0.0, nombres: list[str] | None = None):
        if not llaves:
            raise ValueError("pool sin llaves")
        self.proveedor, self.modelos, self.defecto = proveedor, modelos, defecto
        self.enfriamiento_s, self.temperaturas = enfriamiento_s, temperaturas or {}
        self.espera_saturado_s, self.reintentos_saturado = espera_saturado_s, reintentos_saturado
        self.cero_retencion = cero_retencion
        self._lock = threading.Lock()
        # El guardián de cada llave no duerme: si la llave necesita una pausa, se pasa a la siguiente
        nombres = nombres or []
        self._llaves = [_Llave(l, i, Guardian(espacio_min_s=espacio_s, espera_max_s=espera_guardian_s), nombre=nombres[i - 1] if i <= len(nombres) else "")
                        for i, l in enumerate(llaves, 1)]
        self.nombre = "+".join(sorted({*modelos.values(), defecto}))

    def cargar_enfriamientos(self, por_llave: dict[int, float]) -> None:
        """Enfriamientos vigentes leídos del registro (al arrancar): no se golpea una llave que el proveedor sacó."""
        with self._lock:
            for k in self._llaves:
                if k.indice in por_llave:
                    k.enfriada_hasta = max(k.enfriada_hasta, time.monotonic() + por_llave[k.indice])
                    k.ultimo_error = "según el registro: el proveedor pidió esperar"

    def estado_formal(self) -> str:
        disponibles = sum(k.disponible for k in self._llaves)
        return "NOMINAL" if disponibles == len(self._llaves) else "SATURADO" if disponibles == 0 else "DEGRADADO"

    def estado(self) -> dict:
        return {"estado": self.estado_formal(), "proveedor": self.proveedor, "modelos": {**self.modelos, "otros": self.defecto},
                "llaves": [k.publica() for k in self._llaves]}

    def _elegir(self, excluidas: set[int]) -> _Llave | None:
        with self._lock:
            candidatas = [k for k in self._llaves if k.disponible and k.indice not in excluidas]
            if not candidatas:
                return None
            k = min(candidatas, key=lambda x: x.ultimo_uso)
            k.ultimo_uso = time.monotonic()
            return k

    def _proveedor(self, k: _Llave, modelo: str, proposito: str) -> ProveedorOpenAI:
        clave = (modelo, proposito)
        if clave not in k.proveedores:
            k.proveedores[clave] = ProveedorOpenAI(self.proveedor, modelo, k.llave, k.guardian,
                                                   temperatura=self.temperaturas.get(proposito, TEMPERATURA_BASE),
                                                   cero_retencion=self.cero_retencion)
            k.proveedores[clave].indice_llave = k.indice          # cada llamada registrada dice qué llave respondió
        return k.proveedores[clave]

    def _proxima_liberacion_s(self) -> float:
        with self._lock:
            return max(0.0, min(max(k.enfriada_hasta, k.guardian._abierto_hasta) for k in self._llaves) - time.monotonic())

    def completar(self, sistema: str, usuario: str, proposito: str, max_tokens: int = 900) -> RespuestaModelo:
        """Con todas las llaves enfriándose: SATURADO de inmediato (`espera_saturado_s` = 0, el valor de la demo). Un
        valor mayor solo lo usa un proceso por lotes sin cliente."""
        errores: list[str] = []
        for _ in range(self.reintentos_saturado + 1):
            try:
                return self._intentar(sistema, usuario, proposito, max_tokens, errores)
            except _TodasEnfriadas:
                espera = self._proxima_liberacion_s()
                if espera > self.espera_saturado_s:
                    break
                time.sleep(espera + 0.5)
        razon = "SATURADO: " + ("; ".join(errores) or "todas las llaves en enfriamiento") + \
                f" (la primera se libera en {self._proxima_liberacion_s():.0f}s, tope de espera {self.espera_saturado_s:.0f}s)"
        from servicio.registro.consumo import registrar_llamada
        registrar_llamada(proveedor=self.proveedor, modelo=self.modelos.get(proposito, self.defecto), proposito=proposito,
                          sistema=sistema, exito=False, error=razon)
        raise ModeloNoDisponible(razon)

    def _intentar(self, sistema: str, usuario: str, proposito: str, max_tokens: int, errores: list[str]) -> RespuestaModelo:
        modelo = self.modelos.get(proposito, self.defecto)
        excluidas: set[int] = set()
        while (k := self._elegir(excluidas)) is not None:
            excluidas.add(k.indice)
            try:
                r = self._proveedor(k, modelo, proposito).completar(sistema, usuario, proposito, max_tokens)
            except RespuestaCortada:
                raise                       # la llave está sana y otra llave del mismo modelo cortaría igual
            except ModeloNoDisponible as e:
                with self._lock:
                    k.fallos += 1
                    k.ultimo_error = str(e)[:300]
                    k.enfriada_hasta = time.monotonic() + _enfriamiento(str(e), self.enfriamiento_s)
                errores.append(f"llave {k.indice}: {e}")
                continue
            with self._lock:
                k.llamadas += 1
                k.ultimo_error = None
            r.llave = k.indice
            return r
        raise _TodasEnfriadas()


class _TodasEnfriadas(Exception):
    pass


def _enfriamiento(error: str, defecto: float) -> float:
    """El guardián dice cuándo se libera el cupo ("el cupo se libera en 42s"); si no lo dice, el enfriamiento fijo."""
    import re
    m = re.search(r"(?:se libera en|reintentar en) (\d+)s", error)
    return float(m.group(1)) if m else defecto


class CadenaProveedores:
    """Orden de proveedores: cada uno con su pool de llaves; si uno queda SATURADO, responde el siguiente. Cada
    intento, en cualquier proveedor, queda registrado con su razón."""

    def __init__(self, pools: list[PoolLlaves]):
        self.pools = pools
        self.nombre = "+".join(p.nombre for p in pools)

    def completar(self, sistema: str, usuario: str, proposito: str, max_tokens: int = 900) -> RespuestaModelo:
        errores = []
        for p in self.pools:
            try:
                return p.completar(sistema, usuario, proposito, max_tokens)
            except ModeloNoDisponible as e:
                errores.append(f"{p.proveedor}: {e}")
        raise ModeloNoDisponible("TODOS LOS PROVEEDORES: " + " | ".join(errores))

    def estado_formal(self) -> str:
        estados = [p.estado_formal() for p in self.pools]
        if estados[0] == "NOMINAL":
            return "NOMINAL"
        return "SATURADO" if all(e == "SATURADO" for e in estados) else "DEGRADADO"

    def estado(self) -> dict:
        llaves = [{**k, "proveedor": p.proveedor} for p in self.pools for k in p.estado()["llaves"]]
        return {"estado": self.estado_formal(), "proveedor": " → ".join(p.proveedor for p in self.pools),
                "modelos": {p.proveedor: p.estado()["modelos"] for p in self.pools}, "llaves": llaves}


class SinLlaves:
    """El entorno no trae ninguna llave del proveedor. Cumple el protocolo `Modelo`: cada llamada falla con esa razón
    real y queda registrada; la conversación sigue el camino sin modelo (pasa a una persona con aviso de espera) y la
    cabina lo muestra como alerta crítica. Nunca un error 500."""

    nombre = "sin_llaves"

    def __init__(self, variables: list[str]):
        self.razon = "SIN LLAVES: el entorno de la API no trae ninguna llave (" + ", ".join(variables) + ")"

    def completar(self, sistema: str, usuario: str, proposito: str, max_tokens: int = 900) -> RespuestaModelo:
        from servicio.registro.consumo import registrar_llamada
        registrar_llamada(proveedor="ninguno", modelo="ninguno", proposito=proposito, sistema=sistema, exito=False,
                          error=self.razon)
        raise ModeloNoDisponible(self.razon)

    def estado_formal(self) -> str:
        return "SIN_LLAVES"

    def estado(self) -> dict:
        return {"estado": "SIN_LLAVES", "proveedor": "ninguno", "modelos": {}, "llaves": [], "razon": self.razon}


_POOL = None


def pool_del_sistema() -> PoolLlaves | None:
    """El pool vivo del proceso (lo crea `modelo_desde_entorno` en modo groq); None en puente o pruebas."""
    return _POOL


def registrar_pool(p: PoolLlaves) -> PoolLlaves:
    global _POOL
    _POOL = p
    return p
