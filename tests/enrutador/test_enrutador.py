"""T18/T21: reglas del enrutador (PROCESOS §P2) sobre la plantilla real, sin base."""
from datetime import datetime, timedelta, timezone

from servicio.enrutador.enrutador import _orden, elegibles, espera_excedida, habilidades_por_nivel, nivel_desborde

from servicio.enrutador.enrutador import config as _config
CONFIG_REAL = _config()
AHORA = datetime(2026, 6, 18, 15, 0, tzinfo=timezone.utc)      # 10:00 en Bogotá, 09:00 en Ciudad de México


def asesor(code, hab, idiomas, turno="Morning", pais="Colombia", demo=True, presencia="disponible", carga=0, capacidad=2):
    return {"employee_code": code, "habilidad": hab, "idiomas": idiomas, "canal": "Digital", "turno": turno, "pais": pais,
            "demo": demo, "presencia": presencia, "carga": carga, "capacidad": capacidad, "ultima_asignacion": None}


def test_elegible_exige_habilidad_idioma_turno_capacidad(monkeypatch):
    from servicio.enrutador import enrutador
    monkeypatch.setattr(enrutador, "config", lambda: {**CONFIG_REAL, "asesores_demo_cualquier_habilidad": False})      # la regla de producción
    a = [asesor("A", "fraude", ["es", "pt"]), asesor("B", "fraude", ["es"]), asesor("C", "general", ["es", "pt"]),
         asesor("D", "fraude", ["es", "pt"], turno="Night", demo=False), asesor("E", "fraude", ["es", "pt"], carga=2)]
    assert [x["employee_code"] for x in elegibles(a, "fraude", "pt", 0, AHORA, False)] == ["A", "E"]   # E: presencia, no carga
    assert [x["employee_code"] for x in elegibles(a, "fraude", "pt", 0, AHORA, True)] == ["A"]         # recibe casos: con cupo


def test_identidades_de_demo_siempre_en_turno():
    a = [asesor("N", "fraude", ["es"], turno="Night", demo=True), asesor("M", "fraude", ["es"], turno="Night", demo=False)]
    assert [x["employee_code"] for x in elegibles(a, "fraude", "es", 0, AHORA, False)] == ["N"]


def test_desborde_amplia_habilidades():
    assert habilidades_por_nivel("fraude", 0) == {"fraude"}
    assert habilidades_por_nivel("fraude", 1) == {"fraude", "reclamos"}
    assert habilidades_por_nivel("fraude", 2) == {"fraude", "reclamos", "general"}


def test_sin_nadie_con_el_idioma_en_turno_es_nivel_3():
    a = [asesor("A", "fraude", ["es"], turno="Morning")]
    assert nivel_desborde("fraude", "pt", 1, AHORA, AHORA, a) == 3


def test_nivel_por_fraccion_del_hito():
    a = [asesor("A", "fraude", ["es", "pt"])]
    assert nivel_desborde("fraude", "pt", 4, AHORA - timedelta(minutes=11), AHORA, a) == 1     # 55 % de 20 min
    assert nivel_desborde("fraude", "pt", 4, AHORA - timedelta(minutes=17), AHORA, a) == 2     # 85 %


def test_premium_nunca_adelanta_a_uno_en_alarma_ni_a_mayor_prioridad():
    base = {"numero": "x", "segmento": None}
    fraude = {**base, "numero": "1", "prioridad": 1, "llegada": AHORA}
    premium = {**base, "numero": "2", "prioridad": 4, "segmento": "Premium", "llegada": AHORA - timedelta(minutes=1)}
    alarma = {**base, "numero": "3", "prioridad": 4, "llegada": AHORA - timedelta(minutes=17)}
    normal = {**base, "numero": "4", "prioridad": 4, "llegada": AHORA - timedelta(minutes=2)}
    orden = sorted([normal, premium, alarma, fraude], key=lambda t: _orden(t, AHORA))
    assert [t["numero"] for t in orden] == ["1", "3", "2", "4"]


def test_misma_cola_misma_asignacion():
    a = [asesor("B", "fraude", ["es"]), asesor("A", "fraude", ["es"])]
    uno = [x["employee_code"] for x in elegibles(a, "fraude", "es", 0, AHORA, True)]
    dos = [x["employee_code"] for x in elegibles(list(reversed(a)), "fraude", "es", 0, AHORA, True)]
    assert sorted(uno) == sorted(dos)


def test_espera_excedida_contra_la_primera_estimacion():
    """§P2.6: el aviso aparece cuando la espera real supera en 50 % la primera estimación, y solo en la cola."""
    t = {"estado": "en_cola", "espera_estimada_min": 10, "llegada": AHORA - timedelta(minutes=14)}
    assert not espera_excedida(t, AHORA)
    assert espera_excedida({**t, "llegada": AHORA - timedelta(minutes=16)}, AHORA)
    assert not espera_excedida({**t, "llegada": AHORA - timedelta(minutes=16), "estado": "en_atencion"}, AHORA)
    assert not espera_excedida({**t, "espera_estimada_min": None}, AHORA)      # sin estimación no se promete nada


def test_en_la_demo_las_identidades_de_demo_reciben_casos_de_cualquier_habilidad_pero_no_de_otro_idioma(monkeypatch):
    """Quien entra a la demo no debe adivinar con qué asesor entrar (declarado en `config/atencion_humana.yaml`). El idioma sí se respeta; las identidades que no son de la demo siguen la regla de habilidad."""
    from servicio.enrutador import enrutador
    monkeypatch.setattr(enrutador, "config", lambda: {**CONFIG_REAL, "asesores_demo_cualquier_habilidad": True})
    a = [asesor("G", "general", ["es"]), asesor("F", "fraude", ["pt"]), asesor("X", "general", ["es"], demo=False)]
    assert [x["employee_code"] for x in elegibles(a, "reclamos", "es", 0, AHORA, False)] == ["G"]

