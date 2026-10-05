from servicio.canal.filtro_sensible import MARCA_SECRETO, MARCA_TARJETA, borrar_secretos, borrar_tarjetas


def test_numero_con_espacios_guiones_y_pegado():
    for texto in ["mi tarjeta es 4539 1488 0343 6467, ¿está bien?",
                  "mi tarjeta es 4539-1488-0343-6467",
                  "tarjeta:4539148803436467ok"]:
        limpio, hubo = borrar_tarjetas(texto)
        assert hubo and MARCA_TARJETA in limpio and "6467" not in limpio


def test_monto_largo_sin_luhn_no_se_borra():
    limpio, hubo = borrar_tarjetas("me cobraron 1234567890123 pesos")
    assert not hubo and "1234567890123" in limpio


def test_montos_normales_intactos():
    limpio, hubo = borrar_tarjetas("un cobro de 180.000 el 17 de junio")
    assert not hubo and limpio == "un cobro de 180.000 el 17 de junio"


def test_secretos_marcados_por_el_interprete():
    limpio, n = borrar_secretos("mi clave es 4455, revísenla", ["4455"])
    assert n == 1 and "4455" not in limpio and MARCA_SECRETO in limpio
