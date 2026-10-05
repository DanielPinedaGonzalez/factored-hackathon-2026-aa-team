"""A16: el borrador del asesor sale del estado comunicable del caso; quien lo envía ya es la persona del banco."""
from contratos.modelos import EstadoConversacion
from servicio.asistencia_asesor.asistencia import borrador
from servicio.llm.cliente import ModeloFalso

RESPUESTA = ("IDIOMA: es\nACCIONES_AFIRMADAS: abrir_reclamo\nCITA: ninguna\nSUFICIENCIA: no_aplica\n"
             "TEXTO: Tu reclamo {CASO_1} quedó abierto y lo sigo yo desde aquí. ¿Necesitas algo más?")


def test_el_borrador_lleva_lo_hecho_y_no_ofrece_una_persona():
    modelo = ModeloFalso([RESPUESTA])
    paquete = {"acciones_realizadas": [{"accion": "abrir_reclamo", "estado": "completada", "resultado": {"numero": "R-000101"}}]}
    r = borrador(modelo, EstadoConversacion(conversation_id="c"), paquete, "es")
    assert r["ok"] and "R-000101" in r["texto"]
    enviado = modelo.llamadas[0]["usuario"]
    assert "accion_completada" in enviado and "persona_disponible" not in enviado
