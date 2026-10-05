import pytest

from servicio.recursos.guardian import CircuitoAbierto, CupoAgotado, Guardian, _segundos


def test_lee_duraciones_del_proveedor():
    assert _segundos("7.66s") == pytest.approx(7.66)
    assert _segundos("1m2.5s") == pytest.approx(62.5)
    assert _segundos("120ms") == pytest.approx(0.12)


def test_sin_cupo_de_tokens_y_ventana_larga_no_llama():
    g = Guardian(espacio_min_s=0)
    g.registrar_cabeceras({"x-ratelimit-remaining-tokens": "100", "x-ratelimit-reset-tokens": "5m"})
    with pytest.raises(CupoAgotado):
        g.antes_de_llamar(3000)


def test_circuito_se_abre_tras_fallos_seguidos():
    g = Guardian(espacio_min_s=0, fallos_para_abrir=2)
    g.registrar_resultado(False)
    g.registrar_resultado(False)
    with pytest.raises(CircuitoAbierto):
        g.antes_de_llamar(10)


def test_espacia_las_llamadas():
    g = Guardian(espacio_min_s=0.2)
    g.antes_de_llamar(10)
    assert g.antes_de_llamar(10) > 0.1
