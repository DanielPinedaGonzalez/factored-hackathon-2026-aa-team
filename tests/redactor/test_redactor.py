import pytest

from contratos.modelos import EstadoConversacion, Redaccion
from servicio.llm.cliente import ModeloFalso
from servicio.redactor.estado_comunicable import Constructor, para_modelo
from servicio.redactor.redactor import RedaccionFallida, redactar
from servicio.verificacion.redaccion import reemplazar, verificar


def ec_reclamo():
    b = Constructor("es")
    b.resultado("accion_completada", "abrir_reclamo")
    b.exacto("numero_caso", {"CASO": "R-000101"})
    b.afirmar("abrir_no_asegura_devolucion")
    return b.construir()


BUENA = ("IDIOMA: es\nACCIONES_AFIRMADAS: abrir_reclamo\nCITA: ninguna\nSUFICIENCIA: no_aplica\n"
         "TEXTO: Listo, abrí tu reclamo con el número {CASO_1}. Una persona del banco lo revisa; abrirlo no asegura la devolución.")


def test_al_modelo_no_van_valores():
    assert "R-000101" not in para_modelo(ec_reclamo()) and "CASO_1" in para_modelo(ec_reclamo())


def test_verificador_atrapa_digitos_marcadores_acciones_e_idioma():
    ec = ec_reclamo()
    assert verificar(Redaccion(texto="Tu reclamo {CASO_1} quedó abierto hace 2 minutos", idioma="es",
                               acciones_afirmadas=["abrir_reclamo"]), ec, "es", {"abrir_reclamo"})
    assert verificar(Redaccion(texto="Abrí tu reclamo y el abono llega pronto.", idioma="es",
                               acciones_afirmadas=["abrir_reclamo"]), ec, "es", {"abrir_reclamo"})   # falta {CASO_1}
    assert verificar(Redaccion(texto="Reclamo {CASO_1} aberto, uma pessoa vai revisar o seu caso.", idioma="es",
                               acciones_afirmadas=["abrir_reclamo"]), ec, "es", {"abrir_reclamo"})
    assert verificar(Redaccion(texto="Reclamo {CASO_1} abierto y tarjeta bloqueada, ya está todo.", idioma="es",
                               acciones_afirmadas=["abrir_reclamo", "bloquear_producto"]), ec, "es", {"abrir_reclamo"})


def test_verificador_atrapa_un_marcador_incompleto():
    """Una respuesta cortada a mitad de un marcador nunca llega al cliente."""
    ec = ec_reclamo()
    completo = Redaccion(texto="Listo, abrí tu reclamo con el número {CASO_1} y una persona lo revisa.", idioma="es",
                         acciones_afirmadas=["abrir_reclamo"])
    cortado = Redaccion(texto="Listo, abrí tu reclamo con el número {CASO_1} y una persona lo revisa desde las {HORA",
                        idioma="es", acciones_afirmadas=["abrir_reclamo"])
    assert not verificar(completo, ec, "es", {"abrir_reclamo"})
    assert any("marcador completo" in e for e in verificar(cortado, ec, "es", {"abrir_reclamo"}))


def test_redaccion_buena_y_reemplazo():
    r = redactar(ModeloFalso([BUENA]), EstadoConversacion(conversation_id="c"), ec_reclamo(), "es", {"abrir_reclamo"}, None)
    assert r.origen == "redactor" and "R-000101" in reemplazar(r.redaccion.texto, ec_reclamo())


def test_re_redacta_una_vez_y_luego_persona_nunca_frase():
    mala = BUENA.replace("{CASO_1}", "101")
    r = redactar(ModeloFalso([mala, BUENA]), EstadoConversacion(conversation_id="c"), ec_reclamo(), "es", {"abrir_reclamo"}, None)
    assert r.origen == "re_redaccion"
    with pytest.raises(RedaccionFallida):
        redactar(ModeloFalso([mala, mala]), EstadoConversacion(conversation_id="c"), ec_reclamo(), "es", {"abrir_reclamo"},
                 "Hola, te ayudo.")     # el borrador no sirve: el turno tenía hechos que decir
