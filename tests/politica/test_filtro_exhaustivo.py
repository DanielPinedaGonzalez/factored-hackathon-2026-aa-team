"""El filtro de admisibilidad (las cuatro verificaciones) revisado sobre TODAS las combinaciones de una rejilla de hechos, no solo ejemplos.

La regla que se afirma (función indicadora): una acción se hace sin una persona si y solo si V1 ∧ V2 ∧ V3 ∧ V4. Lo que se comprueba:
1. Admisible ⇒ las cuatro cumplen (nada pasa con una verificación sin cumplir: no hay compensación).
2. Las cuatro cumplen ⇒ admisible (el filtro no bloquea de más), salvo la excepción declarada: abrir un reclamo sobre un cargo sin cobro.
3. Un abono nunca es automático, con cualquier combinación de hechos.
4. Quien recomienda bloquear es el sistema solo con el umbral certificado.
5. Una señal de seguridad nunca deja abrir el reclamo sin una persona.
6. Un hecho desconocido (monto, país, score) nunca equivale a «todo bien».
7. El camino sale de los hechos: dos veces la misma entrada, la misma decisión."""
import itertools
from datetime import date

import pytest

from contratos.modelos import HechosVerificados
from servicio.politica.motor import decidir

HOY = date(2026, 6, 18)
ACCIONES = ["consultar", "abrir_reclamo", "retirar_reclamo", "bloquear_producto", "desbloquear_producto", "abono"]
SENALES_RIESGO = [(None, False, None), (0.0003, False, 0.008), (0.06, False, 0.008), (1.0, True, 0.008)]   # (p, supera el umbral, cota)


def _rejilla():
    for (accion, auth, cand, conf, estado, monto, dias, jur, (p, supera, cota), previos, senales, moneda, pedido, recomienda) in itertools.product(
            ACCIONES, (True, False), (1, 2), (True, False), ("Approved", "Declined"), (10.0, None), (1, 400), ("MX", None),
            SENALES_RIESGO, (0, 2), ([], ["coaccion"]), (True, False), (True, False), (True, False)):
        yield HechosVerificados(autenticado=auth, accion=accion, candidatos=cand, cargo_confirmado=conf, estado_transaccion=estado, monto_usd=monto,
                                dias_desde_transaccion=dias, jurisdiccion=jur, tipo_disputa="no_autorizada", senal_riesgo_p=p,
                                supera_umbral_certificado=supera, cota_fdr=cota, reclamos_previos_90d=previos, senales_riesgo=senales,
                                moneda_pais_coherente=moneda, bloqueo_pedido_por_cliente=pedido, recomendacion_del_sistema=recomienda)


@pytest.fixture(scope="module")
def decisiones():
    return [(h, decidir(h, HOY)) for h in _rejilla()]


def test_la_rejilla_es_grande_de_verdad(decisiones):
    assert len(decisiones) > 90_000


def test_1_admisible_implica_las_cuatro_verificaciones(decisiones):
    malas = [(h, d) for h, d in decisiones if h.accion in d.acciones_permitidas and d.camino == "automatizable"
             and not all(v.cumple for v in d.verificaciones)]
    assert not malas, f"{len(malas)} acciones pasaron con una verificación sin cumplir; la primera: {malas[0][0]}"


def test_2_las_cuatro_cumplen_implica_admisible_salvo_el_cargo_sin_cobro(decisiones):
    malas = [(h, d) for h, d in decisiones if all(v.cumple for v in d.verificaciones)
             and not (h.accion in d.acciones_permitidas or (h.accion == "abrir_reclamo" and h.estado_transaccion == "Declined"))]
    assert not malas, f"{len(malas)} casos con las cuatro cumplidas quedaron fuera; el primero: {malas[0][0]}"


def test_3_un_abono_nunca_es_automatico(decisiones):
    assert not [h for h, d in decisiones if h.accion == "abono" and "abono" in d.acciones_permitidas]


def test_4_el_sistema_solo_recomienda_bloquear_con_el_umbral_certificado(decisiones):
    malas = [h for h, d in decisiones if h.accion == "bloquear_producto" and h.recomendacion_del_sistema
             and not h.supera_umbral_certificado and "bloquear_producto" in d.acciones_permitidas]
    assert not malas


def test_5_una_senal_de_seguridad_nunca_deja_abrir_el_reclamo_sin_una_persona(decisiones):
    assert not [h for h, d in decisiones if h.accion == "abrir_reclamo" and h.senales_riesgo and "abrir_reclamo" in d.acciones_permitidas]


def test_6_un_hecho_desconocido_nunca_equivale_a_todo_bien(decisiones):
    for campo, valor in (("monto_usd", None), ("jurisdiccion", None), ("senal_riesgo_p", None)):
        assert not [h for h, d in decisiones if h.accion == "abrir_reclamo" and getattr(h, campo) == valor and "abrir_reclamo" in d.acciones_permitidas]


def test_7_misma_entrada_misma_decision(decisiones):
    muestra = decisiones[::997]
    assert all(decidir(h, HOY).model_dump() == d.model_dump() for h, d in muestra)
