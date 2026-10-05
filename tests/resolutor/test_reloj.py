"""Reloj de la persona: fecha y hora reales en la zona de su país; los datos se desplazan en bloque (como en el
sistema propio del autor, el servidor y el modelo no ponen la hora)."""
from datetime import date, datetime, timezone

from contratos.modelos import CargoReferido, Cuando
from servicio.resolutor.reloj import Reloj
from servicio.resolutor.resolutor import resolver

CORTE = date(2026, 6, 18)                                       # último día de los datos sintéticos
AHORA = datetime(2026, 9, 27, 0, 30, tzinfo=timezone.utc)       # 19:30 del 26-sep en Bogotá; 18:30 en Ciudad de México


def test_la_fecha_es_la_de_la_persona_y_no_la_del_servidor():
    bogota, cdmx = Reloj.vivo("America/Bogota", CORTE, AHORA), Reloj.vivo("America/Mexico_City", CORTE, AHORA)
    assert bogota.hoy_local == date(2026, 9, 26) and cdmx.hoy_local == date(2026, 9, 26)     # en UTC ya es el 27
    assert bogota.desplazamiento == 100 and bogota.a_local(date(2026, 6, 17)) == date(2026, 9, 25)
    assert cdmx.ahora_datos == datetime(2026, 6, 18, 18, 30)


def _tx(fecha, hora="10:00"):
    return {"fecha": fecha, "hora": hora, "monto": 100.0, "moneda": "MXN", "amount_usd": 5.0, "comercio": "X"}


def test_el_15_es_de_septiembre_y_hace_dos_horas_es_hoy():
    r = Reloj.vivo("America/Mexico_City", CORTE, AHORA)
    quince = CargoReferido(refiere_a="nuevo", cuando=Cuando(tipo="absoluta", valor="15"))
    # el 15 de septiembre real es el 7 de junio en el marco de los datos
    res = resolver(quince, [_tx(date(2026, 6, 7)), _tx(date(2026, 6, 15))], r.hoy_datos, CORTE, r)
    assert res.clase == "1" and res.candidatos[0]["fecha"] == date(2026, 6, 7)
    horas = CargoReferido(refiere_a="nuevo", cuando=Cuando(tipo="relativa", valor="hace_2_horas"))
    res = resolver(horas, [_tx(date(2026, 6, 18)), _tx(date(2026, 6, 17))], r.hoy_datos, CORTE, r)
    assert [t["fecha"] for t in res.candidatos] == [date(2026, 6, 18)]


def test_la_evaluacion_conserva_su_reloj_fijo():
    r = Reloj.fijo(date(2025, 7, 26), "America/Bogota")
    assert r.desplazamiento == 0 and r.hoy_local == date(2025, 7, 26) and r.a_local(date(2025, 7, 25)) == date(2025, 7, 25)
