"""Calendario: fechas relativas contra el reloj del sandbox y días hábiles por país.

Adaptado de un sistema propio del autor (feriados de Colombia, Ley 51 de 1983: fijos, trasladables al lunes y
móviles según la Pascua). México y Argentina: lunes a viernes, sin feriados (simplificación declarada en
PROCESOS §P2.3).
"""
from __future__ import annotations

import functools
import math
from datetime import date, datetime, timedelta

_FIJOS_CO = [(1, 1), (5, 1), (7, 20), (8, 7), (12, 8), (12, 25)]
_TRASLADABLES_CO = [(1, 6), (3, 19), (6, 29), (8, 15), (10, 12), (11, 1), (11, 11)]
DIAS_SEMANA = ["lunes", "martes", "miercoles", "jueves", "viernes", "sabado", "domingo"]
_DIAS_PT = {"segunda": 0, "terca": 1, "quarta": 2, "quinta": 3, "sexta": 4, "sabado": 5, "domingo": 6}


def _pascua(anio: int) -> date:
    a = anio % 19
    b, c = divmod(anio, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    l_ = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l_) // 451
    mes = (h + l_ - 7 * m + 114) // 31
    dia = ((h + l_ - 7 * m + 114) % 31) + 1
    return date(anio, mes, dia)


def _al_lunes(f: date) -> date:
    return f + timedelta(days=(7 - f.weekday()) % 7)


@functools.lru_cache(maxsize=32)
def feriados_co(anio: int) -> frozenset[date]:
    dias = {date(anio, m, d) for m, d in _FIJOS_CO}
    dias |= {_al_lunes(date(anio, m, d)) for m, d in _TRASLADABLES_CO}
    p = _pascua(anio)
    dias |= {p - timedelta(days=3), p - timedelta(days=2)}
    dias |= {_al_lunes(p + timedelta(days=n)) for n in (39, 60, 68)}
    return frozenset(dias)


def es_habil(d: date, pais: str) -> bool:
    if d.weekday() >= 5:
        return False
    return not (pais == "CO" and d in feriados_co(d.year))


def sumar_dias_habiles(inicio: date, n: int, pais: str) -> date:
    actual, contados = inicio, 0
    while contados < n:
        actual += timedelta(days=1)
        if es_habil(actual, pais):
            contados += 1
    return actual


def dias_habiles_entre(desde: date, hasta: date, pais: str) -> int:
    """Días hábiles en (desde, hasta]."""
    n, actual = 0, desde
    while actual < hasta:
        actual += timedelta(days=1)
        if es_habil(actual, pais):
            n += 1
    return n


def momento_del_dia(zona: str, ahora: datetime | None = None) -> str:
    """Hecho del reloj en la zona del cliente (mañana | tarde | noche), como en el sistema propio del autor: lo
    calcula el código y el Redactor lo usa para saludar; el modelo nunca mira el reloj. Cortes: 12:00 y 19:00."""
    from zoneinfo import ZoneInfo
    hora = (ahora or datetime.now(ZoneInfo(zona))).astimezone(ZoneInfo(zona)).hour
    return "mañana" if hora < 12 else "tarde" if hora < 19 else "noche"


def fecha_absoluta(valor: str, hoy: date) -> date | None:
    """AAAA-MM-DD, MM-DD o DD: lo que el cliente dijo, sin que el modelo complete nada. Lo que falta (año, mes) lo
    completa el calendario con la ocurrencia más reciente que no pasa de hoy (un cargo ya ocurrió)."""
    partes = [p for p in valor.strip().split("-") if p]
    try:
        numeros = [int(p) for p in partes]
    except ValueError:
        return None
    try:
        if len(numeros) == 3:
            return date(*numeros)
        if len(numeros) == 2:
            mes, dia = numeros
            d = date(hoy.year, mes, dia)
            return d if d <= hoy else date(hoy.year - 1, mes, dia)
        if len(numeros) == 1:
            dia, anio, mes = numeros[0], hoy.year, hoy.month
            for _ in range(12):
                try:
                    d = date(anio, mes, dia)
                    if d <= hoy:
                        return d
                except ValueError:
                    pass
                mes, anio = (mes - 1, anio) if mes > 1 else (12, anio - 1)
    except ValueError:
        return None
    return None


# Quien dice «hace como ocho días» no recuerda el día exacto, y el error de memoria crece con la distancia: el margen de «hace N días» es una fracción de N
# (mínimo un día, que es lo que había). Un margen mayor no trae ruido: el monto y la descripción siguen filtrando dentro de la ventana.
FRACCION_INCERTIDUMBRE = 0.25

TIPOS_CUANDO = ("absoluta", "relativa", "dia_semana")


def expresion_de_cuando(texto: str) -> tuple[str, str] | None:
    """La fecha dicha como campo suelto (`dar_dato(cuando, ayer)`), sin el tipo que lleva dentro de un bloque CARGO (`relativa ayer`).

    Devuelve (tipo, valor) si la expresión está en el vocabulario cerrado de este módulo (hoy, ayer, anteayer, hace_N_dias, semana_pasada, un día de la semana,
    una fecha); None si no. Es validar lo que emitió el modelo contra un catálogo, no interpretar el mensaje del cliente."""
    partes = (texto or "").strip().split(maxsplit=1)
    if len(partes) == 2 and partes[0] in TIPOS_CUANDO:                  # ya trae su tipo: se respeta (si el valor no se entiende, el resolutor lo dice)
        return partes[0], partes[1]
    referencia = date.today()
    for tipo in TIPOS_CUANDO:
        if (texto or "").strip() and rango_de_cuando(tipo, texto, referencia):
            return tipo, texto.strip()
    return None


def rango_de_cuando(tipo: str, valor: str, hoy: date, ahora: datetime | None = None) -> tuple[date, date] | None:
    """Convierte la expresión del Intérprete en un rango de fechas [desde, hasta]. None si no se entiende.

    El Intérprete no calcula fechas: emite la expresión; aquí se resuelve contra el reloj de la persona (`hoy` y
    `ahora` en la zona de su país, `servicio/resolutor/reloj.py`).
    """
    v = (valor or "").strip().lower().replace("é", "e").replace("á", "a").replace("ç", "c")
    if tipo == "absoluta":
        d = fecha_absoluta(v, hoy)
        return (d, d) if d else None
    if tipo == "relativa":
        if v in ("hoy", "hoje"):
            return (hoy, hoy)
        if v in ("ayer", "ontem"):
            return (hoy - timedelta(days=1),) * 2
        if v in ("anteayer", "anteontem"):
            return (hoy - timedelta(days=2),) * 2
        if v.startswith("hace_") and v.endswith("_dias"):
            try:
                n = int(v.split("_")[1])
            except ValueError:
                return None
            d = hoy - timedelta(days=n)
            margen = timedelta(days=max(1, math.ceil(n * FRACCION_INCERTIDUMBRE)))
            return (d - margen, d + margen)
        if v.startswith("hace_") and v.endswith("_horas"):
            try:
                n = int(v.split("_")[1])
            except ValueError:
                return None
            momento = (ahora or datetime.combine(hoy, datetime.max.time())) - timedelta(hours=n)
            return (min(momento.date(), hoy), hoy)            # si cruza la medianoche, incluye el día anterior
        if v in ("semana_pasada", "semana_passada"):
            lunes = hoy - timedelta(days=hoy.weekday() + 7)
            return (lunes, lunes + timedelta(days=6))
        if v in ("esta_semana",):
            return (hoy - timedelta(days=hoy.weekday()), hoy)
        if v in ("este_mes", "este_mês"):
            return (hoy.replace(day=1), hoy)
        if v in ("mes_pasado", "mes_passado", "mês_passado"):
            ultimo = hoy.replace(day=1) - timedelta(days=1)
            return (ultimo.replace(day=1), ultimo)
        return None
    if tipo == "dia_semana":
        clave = v.split()[0].replace("-feira", "")
        idx = DIAS_SEMANA.index(clave) if clave in DIAS_SEMANA else _DIAS_PT.get(clave)
        if idx is None:
            return None
        atras = (hoy.weekday() - idx) % 7
        d = hoy - timedelta(days=atras)
        if atras == 0:   # "el martes" dicho un martes: hoy o hace una semana
            return (d - timedelta(days=7), d)
        return (d, d)
    return None
