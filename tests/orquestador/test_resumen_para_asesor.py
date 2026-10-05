"""El resumen que el Redactor escribe para el asesor llega con marcadores: se guarda con los valores verificados."""
from servicio.orquestador.orquestador import _completar_solicitud
from servicio.redactor.estado_comunicable import Constructor


class _Conexion:
    def __init__(self):
        self.escrito = []

    def execute(self, sql, params):
        self.escrito.append(params[0])


def _ec():
    b = Constructor("es")
    b.exacto("numero_caso", {"CASO": "R-000101"})
    return b.construir()


def test_el_resumen_se_guarda_con_los_valores_verificados():
    c = _Conexion()
    _completar_solicitud(c, "tr_x", "Cliente con el reclamo {CASO_1} pide revisión.", _ec())
    assert c.escrito == ["Cliente con el reclamo R-000101 pide revisión."]


def test_un_resumen_con_un_marcador_sin_valor_no_se_guarda():
    c = _Conexion()
    _completar_solicitud(c, "tr_x", "Cliente reporta un cargo de {MONTO_9}.", _ec())
    assert c.escrito == []
