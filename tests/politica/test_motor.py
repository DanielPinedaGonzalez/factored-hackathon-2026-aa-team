from datetime import date

from contratos.modelos import HechosVerificados
from servicio.politica.motor import decidir, plazo_normativo, resumen_para_json

HOY = date(2026, 6, 18)


def base(**kw):
    d = dict(autenticado=True, accion="abrir_reclamo", candidatos=1, cargo_confirmado=True, estado_transaccion="Approved",
             monto_usd=45.0, dias_desde_transaccion=1, jurisdiccion="CO", tipo_disputa="no_autorizada",
             senal_riesgo_p=0.0, supera_umbral_certificado=False, cota_fdr=0.008)
    d.update(kw)
    return HechosVerificados(**d)


def test_caso_normal_automatizable_con_plazo():
    d = decidir(base(), HOY)
    assert d.camino == "automatizable" and "abrir_reclamo" in d.acciones_permitidas
    assert all(v.cumple for v in d.verificaciones) and d.plazo_normativo["tipo"] == "habiles"


def test_misma_entrada_misma_salida_byte_a_byte():
    assert resumen_para_json(decidir(base(), HOY)) == resumen_para_json(decidir(base(), HOY))


def test_desconocidos_nunca_son_cero():
    for campo in ("monto_usd", "jurisdiccion", "senal_riesgo_p"):
        assert decidir(base(**{campo: None}), HOY).camino == "revision_humana"


def test_monto_sobre_umbral_y_reclamos_previos():
    assert "monto_sobre_umbral" in decidir(base(monto_usd=2500), HOY).motivos
    assert "reclamos_previos" in decidir(base(reclamos_previos_90d=2), HOY).motivos


def test_senal_de_seguridad_va_a_persona_pero_deja_bloquear():
    d = decidir(base(senales_riesgo=["producto_en_manos_de_otro"]), HOY)
    assert d.camino == "revision_humana" and "bloquear_producto" in d.acciones_permitidas


def test_sin_cobro_no_abre_reclamo_por_defecto():
    d = decidir(base(estado_transaccion="Declined"), HOY)
    assert "abrir_reclamo" not in d.acciones_permitidas and "sin_cobro" in d.motivos


def test_sin_confirmar_el_cargo_se_vuelve_a_aclarar():
    assert decidir(base(cargo_confirmado=False), HOY).camino == "abstencion"


def test_abono_nunca_automatico():
    assert decidir(base(accion="abono"), HOY).camino == "revision_humana"


def test_desbloqueo_tras_riesgo_solo_persona():
    ok = decidir(base(accion="desbloquear_producto", bloqueo_pedido_por_cliente=True), HOY)
    no = decidir(base(accion="desbloquear_producto", bloqueo_pedido_por_cliente=True, senales_riesgo=["coaccion"]), HOY)
    assert ok.camino == "automatizable" and no.camino == "revision_humana"


def test_recomendacion_de_bloqueo_exige_umbral_certificado():
    si = decidir(base(accion="bloquear_producto", recomendacion_del_sistema=True, supera_umbral_certificado=True), HOY)
    no = decidir(base(accion="bloquear_producto", recomendacion_del_sistema=True, supera_umbral_certificado=False), HOY)
    assert si.camino == "automatizable" and no.camino != "automatizable"


def test_pares_metamorficos_el_idioma_y_la_redaccion_no_existen_para_la_politica():
    # HechosVerificados no tiene idioma, texto ni segmento: la decisión no puede depender de ellos.
    assert not {"idioma", "texto", "segmento", "mensaje"} & set(HechosVerificados.model_fields)


def test_plazos_por_pais():
    assert plazo_normativo("MX", HOY)["vence"] == "2026-08-02"
    assert plazo_normativo("AR", HOY)["dias"] == 10 and plazo_normativo(None, HOY) is None
