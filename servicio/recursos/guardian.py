"""A12 — Guardián de cupo (CONTRATOS A12).

Antes de cada llamada a un modelo compara lo que queda del cupo (peticiones y tokens, leídos de las cabeceras de
límite del proveedor en la respuesta anterior) con lo que pide la llamada, y espacia las llamadas para no llegar al
error 429. Si el cupo no alcanza y la ventana es corta, espera; si no, no se llama y la conversación sigue sin modelo.
El modelo nunca decide sobre su propio consumo. El mensaje del cliente no se recorta.
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field


class CupoAgotado(Exception):
    """No hay cupo para esta llamada: la conversación sigue sin modelo (ARQUITECTURA §8.4)."""


class CircuitoAbierto(Exception):
    """El proveedor falló varias veces seguidas: sin modelo hasta la próxima prueba."""


def _segundos(valor: str | None) -> float:
    """Convierte '1m2.5s', '7.66s', '120ms' o '30' a segundos."""
    if not valor:
        return 0.0
    v, total, num = valor.strip(), 0.0, ""
    i = 0
    while i < len(v):
        c = v[i]
        if c.isdigit() or c == ".":
            num += c
        elif v[i:i + 2] == "ms":
            total += float(num or 0) / 1000
            num, i = "", i + 1
        elif c in "hms":
            total += float(num or 0) * {"h": 3600, "m": 60, "s": 1}[c]
            num = ""
        i += 1
    return total + (float(num) if num else 0.0)


@dataclass
class EstadoCupo:
    peticiones_restantes: int | None = None
    tokens_restantes: int | None = None
    reinicio_peticiones_s: float = 0.0
    reinicio_tokens_s: float = 0.0
    leido_en: float = 0.0


@dataclass
class Guardian:
    """Uno por llave. `espacio_min_s` sale del límite por minuto medido (60 / RPM, con margen)."""
    espacio_min_s: float = 2.5
    espera_max_s: float = 20.0
    fallos_para_abrir: int = 3
    enfriamiento_s: float = 60.0
    estado: EstadoCupo = field(default_factory=EstadoCupo)
    _ultima: float = 0.0
    _fallos: int = 0
    _abierto_hasta: float = 0.0
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def antes_de_llamar(self, tokens_estimados: int) -> float:
        """Bloquea lo necesario para respetar el cupo; devuelve los segundos esperados. Lanza si no alcanza."""
        with self._lock:
            ahora = time.monotonic()
            if ahora < self._abierto_hasta:
                raise CircuitoAbierto(f"circuito abierto {self._abierto_hasta - ahora:.0f}s más")
            espera = max(0.0, self._ultima + self.espacio_min_s - ahora)
            e = self.estado
            transcurrido = ahora - e.leido_en
            if e.peticiones_restantes is not None and e.peticiones_restantes <= 1:
                espera = max(espera, e.reinicio_peticiones_s - transcurrido)
            if e.tokens_restantes is not None and e.tokens_restantes < tokens_estimados:
                espera = max(espera, e.reinicio_tokens_s - transcurrido)
            if espera > self.espera_max_s:
                raise CupoAgotado(f"el cupo se libera en {espera:.0f}s")
            if espera > 0:
                time.sleep(espera)
            self._ultima = time.monotonic()
            return espera

    def registrar_cabeceras(self, cabeceras: dict[str, str]) -> None:
        h = {k.lower(): v for k, v in cabeceras.items()}
        e = self.estado
        if "x-ratelimit-remaining-requests" in h:
            e.peticiones_restantes = int(float(h["x-ratelimit-remaining-requests"]))
            e.reinicio_peticiones_s = _segundos(h.get("x-ratelimit-reset-requests"))
        if "x-ratelimit-remaining-tokens" in h:
            e.tokens_restantes = int(float(h["x-ratelimit-remaining-tokens"]))
            e.reinicio_tokens_s = _segundos(h.get("x-ratelimit-reset-tokens"))
        e.leido_en = time.monotonic()

    def registrar_resultado(self, ok: bool, reintentar_en_s: float | None = None) -> None:
        with self._lock:
            if ok:
                self._fallos = 0
                return
            self._fallos += 1
            if reintentar_en_s:
                self._abierto_hasta = max(self._abierto_hasta, time.monotonic() + reintentar_en_s)
            if self._fallos >= self.fallos_para_abrir:
                self._abierto_hasta = max(self._abierto_hasta, time.monotonic() + self.enfriamiento_s)

    @property
    def abierto(self) -> bool:
        return time.monotonic() < self._abierto_hasta
