"""Las métricas complementarias de M1 (ml/metricas_m1.py): probabilidad calibrada y tramos de calibración."""
import numpy as np

from ml.metricas_m1 import _probabilidad, _tramos

ART = {"isotonica_x": [0.0, 29.99, 30.0, 30.01, 99.99], "isotonica_y": [0.0, 0.0003, 0.0003, 1.0, 1.0]}


def test_la_probabilidad_es_el_escalon_guardado():
    p = _probabilidad(ART, np.array([5.0, 30.0, 31.0, 100.0]))
    assert p[0] < 0.001 and p[1] == 0.0003 and p[2] == 1.0 and p[3] == 1.0


def test_los_tramos_cuentan_cada_fila_una_vez_y_traen_su_n():
    p = np.array([0.0, 0.0002, 0.0002, 1.0, 1.0])
    y = np.array([0, 0, 1, 1, 1])
    tramos = _tramos(p, y)
    assert sum(t["n"] for t in tramos) == len(p)
    assert sum(t["fraudes"] for t in tramos) == y.sum()
    assert all(t["ic95_frecuencia"][0] <= t["frecuencia_observada"] <= t["ic95_frecuencia"][1] for t in tramos)
