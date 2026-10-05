"""GOBERNANZA §8: la deriva del fraud_score se mide con PSI contra la ventana de calibración; > 0,2 es alerta."""
import json

from ml.deriva import SALIDA, UMBRAL_ALERTA, psi


def test_psi_es_cero_sin_cambio_y_alto_con_un_cambio_grande():
    ref = [0.5, 0.3, 0.2]
    assert psi(ref, ref) == 0
    assert psi(ref, [0.1, 0.2, 0.7]) > UMBRAL_ALERTA


def test_la_medicion_guardada_cubre_los_meses_posteriores_a_la_calibracion():
    r = json.loads(SALIDA.read_text())
    assert r["referencia"]["ventana"] == ["2023-06-01", "2025-07-01"] and r["por_mes"]
    assert all(m["mes"] >= "2025-07" for m in r["por_mes"]) and r["alerta"] == any(m["alerta"] for m in r["por_mes"])
