"""Reloj de la conversación: la fecha y la hora reales de la persona, en la zona horaria de su país.

Como en el sistema propio del autor, el tiempo lo calcula el código con la zona de quien escribe; nunca el servidor
ni el modelo. Los datos sintéticos del organizador terminan en una fecha de corte (`data_as_of`); en una conversación
en vivo se desplazan en bloque para que ese último día sea hoy en la zona del cliente. Todo lo interno (política,
señal de riesgo, plazos, búsqueda de cargos) trabaja en el marco de los datos, donde las diferencias entre fechas no
cambian; solo se convierte en los bordes: lo que dice el cliente se interpreta en su fecha real (`a_datos`) y toda
fecha que se le muestra sale en su fecha real (`a_local`). Un movimiento posterior a la hora actual del cliente
todavía no ocurrió. La evaluación fija su propio reloj y no se desplaza: es reproducible.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo


@dataclass(frozen=True)
class Reloj:
    hoy_datos: date              # "hoy" en el marco de los datos: con él decide todo lo interno
    desplazamiento: int          # días que separan el marco de los datos de la fecha real del cliente
    ahora_local: datetime        # fecha y hora reales en la zona del cliente
    zona: str

    @classmethod
    def vivo(cls, zona: str, data_as_of: date, ahora: datetime | None = None) -> "Reloj":
        local = (ahora or datetime.now(ZoneInfo(zona))).astimezone(ZoneInfo(zona))
        return cls(data_as_of, max(0, (local.date() - data_as_of).days), local, zona)

    @classmethod
    def fijo(cls, fecha: date, zona: str) -> "Reloj":
        """Reloj fijado (evaluación): sin desplazamiento, al final de ese día."""
        return cls(fecha, 0, datetime.combine(fecha, time(23, 59), ZoneInfo(zona)), zona)

    @property
    def hoy_local(self) -> date:
        return self.ahora_local.date()

    @property
    def ahora_datos(self) -> datetime:
        """El instante actual del cliente llevado al marco de los datos (sin zona, como los movimientos)."""
        return datetime.combine(self.hoy_datos, self.ahora_local.time().replace(tzinfo=None))

    def a_local(self, d):
        """Una fecha de los datos, en la fecha real del cliente (acepta fecha, fecha y hora o texto ISO releído)."""
        if isinstance(d, str):
            d = date.fromisoformat(d[:10])
        return d + timedelta(days=self.desplazamiento) if d is not None else None

    def a_datos(self, d):
        """Una fecha real del cliente, en el marco de los datos."""
        return d - timedelta(days=self.desplazamiento) if d is not None else None
