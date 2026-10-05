from datetime import date

import pytest

from servicio.conocimiento import conocimiento as k
from servicio.datos.db import transaccion

HOY = date(2026, 6, 18)


def test_datos_salen_de_la_politica_y_la_configuracion():
    art = next(a for a in k.articulos_en_disco() if a["cabecera"]["id"] == "publico.plazos-por-pais")
    datos = k.resolver_datos(art["cabecera"])
    assert datos["mx_dias_dictamen"] == "45" and datos["ar_dias_habiles_reclamo"] == "10"


def test_todos_los_articulos_resuelven_sus_datos():
    for a in k.articulos_en_disco():
        k.resolver_datos(a["cabecera"])


def test_solo_publicado_se_sirve_salvo_desarrollo(monkeypatch):
    monkeypatch.delenv("CONOCIMIENTO_INCLUIR_PENDIENTES", raising=False)
    assert k.temas() == {}          # hoy todos están pendientes de aprobación
    monkeypatch.setenv("CONOCIMIENTO_INCLUIR_PENDIENTES", "1")
    assert "publico.plazos-por-pais" in k.temas() and not any(t.startswith("interno.") for t in k.temas())


@pytest.mark.db
def test_cliente_nunca_recibe_un_interno_y_busqueda_por_texto(monkeypatch):
    monkeypatch.setenv("CONOCIMIENTO_INCLUIR_PENDIENTES", "1")
    with transaccion("app_ejecucion", conversation_id="c-test") as c:
        assert k.servir(c, "interno.desbloqueo-tras-riesgo", "CO", "es", HOY) is None
        assert k.servir(c, "publico.plazos-por-pais", "MX", "pt", HOY)["cuerpo"].startswith("Os prazos")
        r = k.buscar(c, "cuánto tiempo tarda en resolverse mi reclamo", "CO", "es", HOY)
        assert r and r[0]["id"].startswith("publico.")


@pytest.mark.db
def test_cortacircuitos_retira_el_articulo_tras_fallas_seguidas_y_sobrevive_a_recargar(monkeypatch):
    """GOBERNANZA §11.8: un acierto vuelve el contador a cero; al llegar al tope, el artículo sale de servicio con su
    evento, y volver a cargar los artículos no lo reactiva. Solo un evento 'reactivado' lo devuelve."""
    import psycopg
    from tests.apoyo import admin
    monkeypatch.setenv("CONOCIMIENTO_INCLUIR_PENDIENTES", "1")
    tema = "publico.hablar-con-una-persona"
    with transaccion("app_ejecucion", conversation_id="c-test") as c:
        art = k.servir(c, tema, "CO", "es", HOY)
        assert k.resultado(c, art, ok=False) != "inactivo"
        assert k.resultado(c, art, ok=True) != "inactivo"          # un acierto reinicia la cuenta
        estados = [k.resultado(c, art, ok=False) for _ in range(k.CORTACIRCUITOS_FALLAS)]
        assert estados[-1] == "inactivo" and "inactivo" not in estados[:-1]
        assert k.servir(c, tema, "CO", "es", HOY) is None
    try:
        with admin() as a:
            assert a.execute("select count(*) from atencion.conocimiento_eventos where articulo = %s and evento = 'cortacircuitos'",
                             (tema,)).fetchone()[0] >= 1
            k.cargar_en_base(a)
            assert a.execute("select estado from atencion.conocimiento_articulos where id = %s", (tema,)).fetchone()[0] == "inactivo"
    finally:
        with admin() as a:
            a.execute("insert into atencion.conocimiento_eventos (articulo, version, evento) values (%s, %s, 'reactivado')",
                      (tema, art["version"]))
            k.cargar_en_base(a)
            assert a.execute("select estado from atencion.conocimiento_articulos where id = %s", (tema,)).fetchone()[0] != "inactivo"
