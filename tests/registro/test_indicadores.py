"""Indicadores de operación (A13): mismas definiciones que el reporte, calculadas del registro de turnos."""
from datetime import datetime, timedelta, timezone

from servicio.registro.indicadores import calcular

AHORA = datetime(2026, 9, 26, 12, tzinfo=timezone.utc)


def _turno(cid, minutos, acciones=(), traspaso=None, sin_modelo=False, latencia=1000.0):
    pasos = [{"componente": "traspaso", "estado": "ok", "detalle": {"habilidad": traspaso}}] if traspaso else []
    return {"conversation_id": cid, "creado": AHORA - timedelta(minutes=minutos),
            "registro": {"pasos": pasos, "acciones": [{"accion": a} for a in acciones], "sin_modelo": sin_modelo,
                         "latencia_ms": latencia, "espera_cupo_ms": 0, "tokens": {"entrada": 100, "salida": 20},
                         "senales": []}}


def test_resuelta_solo_con_accion_verificada_y_sin_persona():
    regs = [_turno("a", 60, acciones=["abrir_reclamo"]),          # resuelta por el asistente
            _turno("b", 60, acciones=["bloquear_producto"]), _turno("b", 59, traspaso="fraude"),   # acción + persona
            _turno("c", 60),                                        # solo conversó: ni resuelta ni escalada
            _turno("d", 5, sin_modelo=True, traspaso="general")]
    o = calcular(regs, AHORA)
    assert o["conversaciones"] == 4
    assert o["resueltas_por_el_asistente"]["numerador"] == 1
    assert o["pasaron_a_una_persona"]["numerador"] == 2
    assert o["traspasos_por_habilidad"] == {"fraude": 1, "general": 1}
    assert o["acciones_verificadas"] == {"abrir_reclamo": 1, "bloquear_producto": 1}
    assert o["alarma_sin_modelo"]["activa"] is True


def test_alarma_se_apaga_fuera_de_la_ventana_y_sin_datos_no_inventa():
    assert calcular([_turno("d", 60, sin_modelo=True)], AHORA)["alarma_sin_modelo"]["activa"] is False
    vacio = calcular([], AHORA)
    assert vacio["conversaciones"] == 0 and vacio["resueltas_por_el_asistente"]["tasa"] is None
    assert vacio["equivalente_usd_por_resolucion"] == "no definido"
