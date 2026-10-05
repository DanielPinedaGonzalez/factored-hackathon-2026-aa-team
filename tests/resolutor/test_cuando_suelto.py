"""Hallado en la demo: el cliente dijo «ayer» dos veces y el sistema le volvió a pedir fecha, monto y descripción.

Causa: el Intérprete escribió la fecha suelta (`dar_dato(cuando, ayer)`) y no con su tipo (`relativa ayer`, como en un bloque CARGO); `_referido_de_datos` la
descartaba sin avisar, de modo que la búsqueda no tuvo fecha. Ahora el calendario reconoce la expresión suelta y, si no la reconoce, queda un incidente."""
from contratos.modelos import EstadoConversacion
from servicio.orquestador import grafo
from servicio.resolutor.calendario import expresion_de_cuando


def test_una_fecha_suelta_del_vocabulario_se_reconoce_con_su_tipo():
    assert expresion_de_cuando("ayer") == ("relativa", "ayer")
    assert expresion_de_cuando(" Ayer ") == ("relativa", "Ayer")
    assert expresion_de_cuando("anteayer") == ("relativa", "anteayer")
    assert expresion_de_cuando("hace_3_dias") == ("relativa", "hace_3_dias")
    assert expresion_de_cuando("semana_pasada") == ("relativa", "semana_pasada")
    assert expresion_de_cuando("lunes") == ("dia_semana", "lunes")
    assert expresion_de_cuando("2026-06-17") == ("absoluta", "2026-06-17")


def test_una_fecha_que_ya_trae_su_tipo_se_respeta_y_lo_que_no_se_reconoce_es_none():
    assert expresion_de_cuando("relativa ayer") == ("relativa", "ayer")
    assert expresion_de_cuando("dia_semana lunes") == ("dia_semana", "lunes")
    assert expresion_de_cuando("cuando me dio la gana") is None and expresion_de_cuando("") is None and expresion_de_cuando(None) is None


def _estado(cuando):
    return EstadoConversacion(conversation_id="x", datos_dados={"cuando": cuando})


def test_el_referido_toma_la_fecha_suelta_y_no_la_descarta():
    assert grafo._referido_de_datos(_estado("ayer"))["cuando"] == {"tipo": "relativa", "valor": "ayer"}
    assert grafo._referido_de_datos(_estado("relativa ayer"))["cuando"] == {"tipo": "relativa", "valor": "ayer"}


def test_una_fecha_que_el_calendario_no_reconoce_deja_incidente_y_no_se_descarta_en_silencio(monkeypatch):
    avisos = []
    import servicio.registro.consumo as consumo
    monkeypatch.setattr(consumo, "registrar_incidente", lambda *a, **k: avisos.append((a, k)))
    assert "cuando" not in grafo._referido_de_datos(_estado("cuando me dio la gana"))
    assert avisos and avisos[0][1]["tipo"] == "dato_no_entendido"
