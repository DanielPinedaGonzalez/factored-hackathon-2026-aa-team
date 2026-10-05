"""Reporte de evaluación (R9): una página con las métricas del enunciado, numerador y denominador, por idioma y
segmento, con los fallos a la vista. Con varias tandas del mismo conjunto (desarrollo), cada caso aparece en su primer
intento y en el último: el último mide el sistema corregido, el primero dice cuánto se corrigió mirando los casos, y
los casos que cambiaron de resultado entre intentos son la variabilidad observada. La comparación con la línea base
se hace sobre los mismos casos.

Uso: python -m evaluacion.reporte [--propuesto ARCHIVO] [--linea-base ARCHIVO]
Escribe docs/REPORTE_EVALUACION.md.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
CORRIDAS = RAIZ / "evaluacion" / "corridas"


def _ultima(sistema: str, conjunto: str | None = None) -> Path | None:
    candidatas = sorted(f for f in CORRIDAS.glob(f"*_{sistema}_*.json") if conjunto is None or f.stem.endswith(conjunto))
    return candidatas[-1] if candidatas else None



def _como_leer(conjunto: str) -> list[str]:
    if conjunto == "final":
        return ["**Cómo leer este reporte.** Es el conjunto **final** (clientes y transacciones de 2026-H1, que no se usaron para desarrollar).",
                "Es una sola pasada del sistema congelado: lo que falló **no se corrigió ni se repitió** después de verlo, así que \"primer\" y",
                "\"último intento\" coinciden. La pasada se hizo en tandas por los límites de cupo del proveedor (lo no contado se reanuda, no se repite).",
                "Antes de esta pasada hubo otra, interrumpida a la mitad y descartada (`evaluacion/corridas/invalidas/LEEME.md`): en su registro se vio",
                "que un cambio nuestro había roto el caso B4; el arreglo (buscar el artículo por la categoría que declara el Intérprete) se diseñó con las",
                "trazas del conjunto de desarrollo y se verificó en B3 y B4 de desarrollo. Declararlo es parte de la honestidad de esta medición."]
    return ["**Cómo leer este reporte.** Es el conjunto de **desarrollo**: el sistema se corrigió mirando estos casos y los",
            "que fallaron se volvieron a correr. \"Último intento\" mide el sistema corregido; \"primer intento\" dice cuánto",
            "cambió. La cifra que cuenta es la corrida final sobre casos que nadie miró (2026-H1), una sola vez."]


def _limite_repeticion(conjunto: str) -> list[str]:
    if conjunto == "final":
        return ["- Final: cada caso se corrió una vez con el sistema congelado; no hay repeticiones, así que no se mide la variabilidad del modelo entre intentos."]
    return ["- Desarrollo: los casos que fallaron se repitieron tras corregir el código; por eso se muestran primer y último intento."]


def _limite_base(base, prop) -> list[str]:
    if base and base["metricas"]["casos"] < prop["metricas"]["casos"]:
        return ["- La línea base se corre en un subconjunto que cubre todos los grupos (su prompt lleva los movimientos del cliente y "
                "gasta más cupo por caso). Para ella se juzga solo lo observable (reclamos, bloqueos, traspasos, acciones), no el nodo interno."]
    return ["- Para la línea base se juzga solo lo observable (reclamos, bloqueos, traspasos, acciones), no el nodo interno."]

def _segmentos() -> dict[str, str]:
    """Segmento del cliente de cada caso (las corridas anteriores a registrarlo no lo traen)."""
    import psycopg
    from evaluacion.evaluador import ADMIN
    manifest = json.loads((RAIZ / "evaluacion" / "manifest_casos.json").read_text())["casos"]
    ids = {caso: d["desarrollo"]["customer_id"] for caso, d in manifest.items()}
    try:
        with psycopg.connect(ADMIN) as c:
            seg = dict(c.execute("select customer_id, segmento from servicio.clientes where customer_id = any(%s)",
                                 (list(ids.values()),)).fetchall())
    except psycopg.OperationalError:
        return {}
    return {caso: seg.get(cid) for caso, cid in ids.items()}


def _combinar(archivos: list[Path], casos: set[str] | None = None) -> dict:
    """Varias tandas del mismo sistema y conjunto: primer y último resultado de cada caso, e intentos."""
    from evaluacion import metricas
    primero: dict[str, dict] = {}
    ultimo: dict[str, dict] = {}
    intentos: dict[str, list[bool]] = {}
    commits: list[str] = []
    base = None
    segmentos = _segmentos()
    for f in sorted(archivos):
        d = json.loads(f.read_text())
        base = base or d
        commits.append(d.get("commit") or "sin registrar")
        for r in d["resultados"]:
            if casos is not None and r["caso"] not in casos:
                continue
            r.setdefault("segmento", segmentos.get(r["caso"]))
            primero.setdefault(r["caso"], r)
            ultimo[r["caso"]] = r
            intentos.setdefault(r["caso"], []).append(bool(r["paso"]))
    return {**(base or {}), "resultados": list(ultimo.values()), "metricas": metricas.calcular(list(ultimo.values())),
            "primer_intento": metricas.calcular(list(primero.values())), "intentos": intentos,
            "archivos": [f.name for f in sorted(archivos)], "commits": sorted(set(commits))}


def _t(x: dict) -> str:
    if x.get("denominador") in (None, 0):
        return "no definido"
    ic = f" [IC95 {x['ic95'][0]:.2f}-{x['ic95'][1]:.2f}]" if x.get("ic95") else ""
    return f"{x['numerador']}/{x['denominador']} = {x['tasa']:.2f}{ic}"


def _marcas(v: list[bool]) -> str:
    return "(" + "".join("✓" if x else "✗" for x in v) + ")"


def _reproducibilidad(archivos: list[str]) -> list[str]:
    """Qué parte de lo observado es del sistema y qué parte es azar del modelo. Las corridas con la misma huella del
    sistema (prompts, catálogo, política, configuración y código) son repeticiones del mismo sistema: lo que cambia entre
    ellas es ruido. Las que difieren en la huella miden un sistema distinto, y se dice qué componente cambió."""
    from evaluacion.versiones import que_cambio
    grupos: dict[str, list[dict]] = {}
    for nombre in archivos:
        d = json.loads((CORRIDAS / nombre).read_text())
        grupos.setdefault((d.get("versiones") or {}).get("sistema") or "sin registrar", []).append(d)
    lineas = ["", "## Reproducibilidad", "",
              "Cada corrida guarda la huella del sistema que probó. Misma huella = el mismo sistema repetido: lo que cambia entre "
              "esas corridas es el azar del modelo, no un cambio nuestro.", "",
              "| Huella del sistema | Corridas | Cambió respecto al grupo anterior | Casos que pasan, por corrida |", "|---|---|---|---|"]
    previa = None
    for huella, corridas in grupos.items():
        v = corridas[0].get("versiones") or {}
        cambio = "—" if previa is None else (", ".join(que_cambio(previa, v)) or "nada") if v else "sin registrar"
        tasas = " · ".join(f"{sum(r['paso'] for r in c['resultados'])}/{len(c['resultados'])}" for c in corridas)
        lineas.append(f"| `{huella}` | {len(corridas)} | {cambio} | {tasas} |")
        previa = v or previa
    repetidas = {h: c for h, c in grupos.items() if h != "sin registrar" and len(c) > 1}
    for huella, corridas in repetidas.items():
        por_caso: dict[str, list[bool]] = {}
        for c in corridas:
            for r in c["resultados"]:
                por_caso.setdefault(r["caso"], []).append(bool(r["paso"]))
        observados = {c: v for c, v in por_caso.items() if len(v) > 1}          # casos vistos más de una vez con este sistema
        inestables = {c: v for c, v in observados.items() if len(set(v)) > 1}
        lineas += ["", f"Sistema `{huella}`: {len(corridas)} corridas; {len(observados)} casos observados más de una vez. Cambian de "
                   f"resultado **sin que el sistema cambie** {len(inestables)}"
                   + (": " + ", ".join(f"{c} {sum(v)}/{len(v)}" for c, v in sorted(inestables.items())) if inestables else "") + "."]
    if not repetidas:
        lineas += ["", "Todavía no hay dos corridas con el mismo sistema: el azar del modelo no está separado del efecto de las "
                       "correcciones. Hace falta repetir la corrida con la huella congelada."]
    return lineas


def _aviso_de_version(archivos: list[str]) -> list[str]:
    """Dice si el sistema que hay ahora es el que se midió. Si no lo es, qué componentes cambiaron: una cifra solo vale para el
    sistema que la produjo."""
    from evaluacion.versiones import huella, que_cambio
    medidas = [(json.loads((CORRIDAS / n).read_text()).get("versiones") or {}) for n in archivos]
    medidas = [v for v in medidas if v.get("sistema")]
    if not medidas:
        return ["> **Estas cifras no dicen con qué versión del sistema se midieron** (las corridas son anteriores a la huella).", ""]
    ahora = huella()
    if all(v["sistema"] == ahora["sistema"] for v in medidas):
        return [f"> Sistema medido = sistema actual (huella `{ahora['sistema']}`).", ""]
    medida = medidas[-1]
    return [f"> **El sistema actual no es exactamente el que se midió.** Medido: `{medida['sistema']}`. Actual: `{ahora['sistema']}`. "
            f"Componentes que cambiaron: {', '.join(que_cambio(medida, ahora)) or 'ninguno de los registrados'}. "
            "Las cifras describen el sistema medido; lo que cambió después se declara en `evaluacion/EXPERIMENTOS.md`.", ""]


def generar(prop: dict, base: dict | None, pareado: tuple[dict, dict] | None = None) -> str:
    mp, mb = prop["metricas"], (base or {}).get("metricas")
    filas = [("Casos que pasan (todo lo esperado, nada inseguro)", "pasan"),
             ("Resolución automática segura (sobre elegibles)", "resolucion_automatica_segura_sobre_elegibles"),
             ("Resolución automática segura (sobre intentados)", "resolucion_automatica_segura_sobre_intentados"),
             ("Contención correcta", "contencion_correcta"), ("Contención falsa", "contencion_falsa"),
             ("Escalada correcta", "escalada_correcta"), ("Escalada faltante", "escalada_faltante"),
             ("Escalada innecesaria", "escalada_innecesaria"), ("Inseguros", "inseguros")]
    pp = prop["primer_intento"]
    varios = {c: v for c, v in prop["intentos"].items() if len(v) > 1}
    cambiaron = sorted(c for c, v in varios.items() if len(set(v)) > 1)
    lineas = ["# Reporte de evaluación", "",
              "**Diseño de arquitectura:** Daniel Pineda González  ",
              "**Qué responde:** qué tan bien funciona el sistema, medido con el modelo real. Generado por "
              "`evaluacion/reporte.py` desde las corridas guardadas; no se edita a mano.", "",
              f"**Conjunto:** {prop['conjunto']} · **Sistema propuesto:** {len(prop.get('archivos', []))} tandas "
              f"(código {', '.join(prop['commits'])})"
              + (f" · **Línea base:** {len(base.get('archivos', []))} tandas" if base else ""), "",
              *_aviso_de_version(prop.get("archivos", [])),
              "Casos canónicos de `evaluacion/ground_truth_cases.yaml` (uno por comportamiento, sin repetir), con clientes y",
              "transacciones reales elegidos al azar con semilla. El puntaje sale del estado final de la base y del registro,",
              "comparado con la verdad de referencia; nunca del texto del modelo. \"Probado en nuestra batería\", no \"validado\".", "",
              *_como_leer(prop['conjunto']), "",
              "| Métrica | Propuesto · último intento | Propuesto · primer intento | Línea base · último intento |", "|---|---|---|---|"]
    for nombre, clave in filas:
        lineas.append(f"| {nombre} | {_t(mp[clave])} | {_t(pp[clave])} | {_t(mb[clave]) if mb else '—'} |")
    lineas.append(f"| Cota superior 95 % de inseguros | {mp['inseguros']['cota_superior_95']} | {pp['inseguros']['cota_superior_95']} | "
                  f"{mb['inseguros']['cota_superior_95'] if mb else '—'} |")
    lineas.append(f"| Latencia p50 / p95 (ms, por turno, local) | {mp['latencia_ms']['p50']} / {mp['latencia_ms']['p95']} | "
                  f"{pp['latencia_ms']['p50']} / {pp['latencia_ms']['p95']} | "
                  f"{(str(mb['latencia_ms']['p50']) + ' / ' + str(mb['latencia_ms']['p95'])) if mb else '—'} |")
    c = mp["consumo"]
    lineas.append(f"| Tokens (entrada + salida) | {c['tokens_entrada']} + {c['tokens_salida']} | "
                  f"{pp['consumo']['tokens_entrada']} + {pp['consumo']['tokens_salida']} | "
                  f"{(str(mb['consumo']['tokens_entrada']) + ' + ' + str(mb['consumo']['tokens_salida'])) if mb else '—'} |")
    lineas.append(f"| Equivalente USD por caso (referencia a precio público; con llaves gratuitas no hay cobro) | "
                  f"{c['equivalente_usd_por_caso']} | {pp['consumo']['equivalente_usd_por_caso']} | "
                  f"{mb['consumo']['equivalente_usd_por_caso'] if mb else '—'} |")
    lineas.append(f"| Equivalente USD por resolución | {c['equivalente_usd_por_resolucion']} | "
                  f"{pp['consumo']['equivalente_usd_por_resolucion']} | {mb['consumo']['equivalente_usd_por_resolucion'] if mb else '—'} |")
    if pareado:
        pp_, pb_ = pareado
        lineas += ["", f"## Mismos casos que la línea base ({pp_['metricas']['casos']} casos)", "",
                   "La comparación es sobre los mismos casos que corrió la línea base.", "",
                   "| Métrica | Propuesto · último | Propuesto · primer intento | Línea base · último | Línea base · primer intento |",
                   "|---|---|---|---|---|"]
        for nombre, clave in filas:
            lineas.append(f"| {nombre} | {_t(pp_['metricas'][clave])} | {_t(pp_['primer_intento'][clave])} | "
                          f"{_t(pb_['metricas'][clave])} | {_t(pb_['primer_intento'][clave])} |")
    lineas += ["", "## Variabilidad entre intentos", "",
               f"{len(varios)} casos del sistema propuesto se corrieron más de una vez; {len(cambiaron)} cambiaron de resultado "
               f"({', '.join(f'{c} {_marcas(prop['intentos'][c])}' for c in cambiaron) or 'ninguno'}). Entre intentos cambió el "
               "código (se corrigió lo que falló), así que esto mezcla corrección y azar del modelo: no es pass^k."]
    todas = sorted(f.name for f in CORRIDAS.glob(f"*_propuesto_{prop.get('conjunto', 'desarrollo')}.json"))
    lineas += _reproducibilidad(todas)
    cq = mp["latencia_ms"].get("con_espera_de_cupo", {})
    lineas += ["", f"La latencia de la tabla es de procesamiento. Con la espera del guardián de cupo (el límite gratuito por minuto obliga a "
               f"espaciar las llamadas): p50 {cq.get('p50')} ms / p95 {cq.get('p95')} ms. Las corridas grabadas antes de registrar la espera "
               "cuentan la latencia total.", "",
               "## Por idioma y por segmento (último intento)", "", "| Grupo | Pasan | Inseguros |", "|---|---|---|"]
    for campo, titulo in (("por_idioma", "idioma"), ("por_segmento", "segmento")):
        for valor, v in mp[campo].items():
            lineas.append(f"| {titulo}: {valor} | {_t(v['pasan'])} | {_t(v['inseguros'])} |")
    lineas += ["", "## Casos que no pasan (propuesto)", "", "| Caso | Qué faltó o qué fue inseguro |", "|---|---|"]
    for r in sorted(prop["resultados"], key=lambda r: r["caso"]):
        if not r["paso"]:
            lineas.append(f"| {r['caso']} | {'; '.join(r['fallas'] + r['inseguro'])} |")
    if base:
        lineas += ["", "## Inseguros de la línea base", ""]
        for caso, det in mb["inseguros"]["detalle"].items():
            lineas.append(f"- {caso}: {'; '.join(det)}")
    lineas += ["", "## Límites de esta medición", "",
               "- Pocos casos: los intervalos son anchos y se reportan siempre; con 0 inseguros se da la cota superior, nunca \"cero riesgo\".",
               "- El cliente de la evaluación es guionizado (usa la interfaz como una persona); los personajes con modelo se usan en un subconjunto.",
               *_limite_repeticion(prop['conjunto']),
               "- El cupo gratuito no alcanza para repetir cada caso con el mismo código (pass^k); la variabilidad de arriba no lo reemplaza.",
               *_limite_base(base, prop),
               "- El cliente de la línea base contesta con texto cuando ella pregunta con texto, y se identifica si se lo pide: la misma persona, con la misma meta.",
               "- El portugués se verifica por retrotraducción, no por revisión nativa.", ""]
    return "\n".join(lineas)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--conjunto", default="desarrollo")
    ap.add_argument("--propuesto", nargs="*")
    ap.add_argument("--linea-base", nargs="*")
    a = ap.parse_args()
    prop_archivos = [CORRIDAS / f for f in a.propuesto] if a.propuesto else sorted(CORRIDAS.glob(f"*_propuesto_{a.conjunto}.json"))
    base_archivos = [CORRIDAS / f for f in a.linea_base] if a.linea_base else sorted(CORRIDAS.glob(f"*_linea_base_{a.conjunto}.json"))
    prop = _combinar(prop_archivos)
    base = _combinar(base_archivos) if base_archivos else None
    pareado = None
    if base:
        comunes = {r["caso"] for r in base["resultados"]} & {r["caso"] for r in prop["resultados"]}
        pareado = (_combinar(prop_archivos, comunes), _combinar(base_archivos, comunes))
    texto = generar(prop, base, pareado)
    (RAIZ / "docs" / "REPORTE_EVALUACION.md").write_text(texto, encoding="utf-8")
    print(texto)


if __name__ == "__main__":
    main()
