from datetime import date

from contratos.modelos import CargoReferido, Cuando, Monto
from servicio.resolutor.calendario import dias_habiles_entre, es_habil, feriados_co, rango_de_cuando, sumar_dias_habiles
from servicio.resolutor.resolutor import resolver

HOY = date(2026, 6, 18)   # jueves


def tx(d, monto, comercio="Rappi", moneda="COP"):
    return {"fecha": d, "monto": monto, "moneda": moneda, "amount_usd": monto / 4000, "comercio": comercio, "estado": "Approved"}


def test_feriados_colombia_conocidos():
    f = feriados_co(2026)
    assert date(2026, 1, 1) in f and date(2026, 7, 20) in f
    assert date(2026, 1, 12) in f          # Reyes trasladado al lunes
    assert date(2026, 4, 3) in f           # Viernes Santo (Pascua 5-abr-2026)


def test_dias_habiles_por_pais():
    assert not es_habil(date(2026, 7, 20), "CO") and es_habil(date(2026, 7, 20), "MX")
    assert sumar_dias_habiles(date(2026, 6, 18), 2, "MX") == date(2026, 6, 22)
    assert dias_habiles_entre(date(2026, 6, 18), date(2026, 6, 22), "MX") == 2


def test_fechas_relativas():
    assert rango_de_cuando("relativa", "ayer", HOY) == (date(2026, 6, 17),) * 2
    assert rango_de_cuando("relativa", "ontem", HOY) == (date(2026, 6, 17),) * 2
    assert rango_de_cuando("dia_semana", "martes", HOY) == (date(2026, 6, 16),) * 2
    assert rango_de_cuando("dia_semana", "jueves", HOY) == (date(2026, 6, 11), HOY)
    assert rango_de_cuando("relativa", "el dia del padre", HOY) is None


def test_monto_aproximado_solo_propone_y_nunca_elige():
    txs = [tx(date(2026, 6, 17), 179850), tx(date(2026, 6, 17), 500000)]
    r = resolver(CargoReferido(monto=Monto(valor=180000, aproximado=True), cuando=Cuando(tipo="relativa", valor="ayer")),
                 txs, HOY, HOY)
    assert r.clase == "1" and r.candidatos[0]["monto"] == 179850


def test_el_resolutor_filtra_por_lo_que_se_calcula_y_la_descripcion_queda_para_el_comparador():
    """La descripción del cliente (comercio o tipo de operación) no filtra por palabras aquí: la compara el
    Comparador (A3b) por el sentido. Una transferencia sin comercio sigue siendo candidata."""
    txs = [tx(date(2026, 6, d), 20000 + d) for d in (10, 12, 15)] + [{**tx(date(2026, 6, 14), 9000), "comercio": None}]
    r = resolver(CargoReferido(descripcion="transferencia"), txs, HOY, HOY)
    assert r.clase == "2-5" and [t["fecha"].day for t in r.candidatos] == [15, 14, 12, 10]


def test_estado_guardado_con_comercio_o_canal_se_lee_como_descripcion():
    assert CargoReferido(**{"comercio_texto": "rappi", "canal": None}).descripcion == "rappi"
    assert CargoReferido(**{"comercio_texto": None, "canal": "transferencia"}).descripcion == "transferencia"


def test_cargo_posterior_a_los_datos():
    r = resolver(CargoReferido(cuando=Cuando(tipo="relativa", valor="hoy")), [], date(2026, 6, 19), HOY)
    assert r.clase == "0" and r.posterior_a_datos


def test_la_fecha_absoluta_la_completa_el_calendario_y_no_el_modelo():
    """El modelo escribe las partes que dijo el cliente; el año y el mes que faltan salen del reloj (adaptado de un sistema propio del autor)."""
    from datetime import date
    from servicio.resolutor.calendario import fecha_absoluta
    hoy = date(2026, 6, 18)
    assert fecha_absoluta("2026-06-15", hoy) == date(2026, 6, 15)
    assert fecha_absoluta("06-15", hoy) == date(2026, 6, 15)
    assert fecha_absoluta("12-24", hoy) == date(2025, 12, 24)        # diciembre ya pasó el año anterior
    assert fecha_absoluta("15", hoy) == date(2026, 6, 15)
    assert fecha_absoluta("20", hoy) == date(2026, 5, 20)            # el 20 de este mes todavía no llega
    assert fecha_absoluta("31", date(2026, 6, 18)) == date(2026, 5, 31)
    assert fecha_absoluta("sin fecha", hoy) is None


def test_el_momento_del_dia_sale_del_reloj_en_la_zona_del_cliente():
    from datetime import datetime, timezone
    from servicio.resolutor.calendario import momento_del_dia
    t = datetime(2026, 6, 18, 17, 30, tzinfo=timezone.utc)                 # 12:30 en Bogotá, 14:30 en Buenos Aires
    assert momento_del_dia("America/Bogota", t) == "tarde"
    assert momento_del_dia("America/Mexico_City", datetime(2026, 6, 18, 16, 0, tzinfo=timezone.utc)) == "mañana"
    assert momento_del_dia("America/Argentina/Buenos_Aires", datetime(2026, 6, 18, 23, 0, tzinfo=timezone.utc)) == "noche"
