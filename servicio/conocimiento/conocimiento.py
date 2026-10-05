"""A15 — Servicio de conocimiento (ARQUITECTURA §8.8, CONTRATOS A15, GOBERNANZA §11).

Entrega el artículo vigente de un tema del catálogo, filtrado por audiencia (la RLS niega los internos al cliente) y
por país. Si el Intérprete no nombra un tema, busca por texto completo en los artículos públicos vigentes. Las cifras
no viven en el artículo: sus marcadores se resuelven desde la política o la configuración al servir. Sin artículo
suficiente, `None` (SIN_ARTICULO): el Redactor no responde de memoria.

Solo se sirven artículos `publicado`. En desarrollo local, `CONOCIMIENTO_INCLUIR_PENDIENTES=1` sirve también los
`pendiente_aprobacion` (declarado; nunca en el despliegue público).
"""
from __future__ import annotations

import functools
import json
import os
import re
from datetime import date
from pathlib import Path

import yaml
from contratos.idiomas import IDIOMA_BASE

RAIZ = Path(__file__).resolve().parents[2]
CARPETA = RAIZ / "conocimiento"
PAISES_NOMBRE = {"MX": "MX", "CO": "CO", "AR": "AR"}
RANGO_MINIMO_BUSQUEDA = 0.05
CORTACIRCUITOS_FALLAS = 3          # respuestas seguidas que no pasan la verificación al primer intento (GOBERNANZA §11.8)


def articulos_en_disco() -> list[dict]:
    salida = []
    for f in sorted(CARPETA.glob("*/*.md")):
        if f.name == "README.md":
            continue
        _, cab, cuerpo = f.read_text(encoding="utf-8").split("---\n", 2)
        cab = yaml.safe_load(cab)
        texto = cuerpo.split("\n## Respaldo")[0]          # el respaldo es para el asesor y el jurado
        partes = re.split(r"^## (es|pt)\s*$", texto, flags=re.M)
        cuerpos = {partes[i]: partes[i + 1].strip() for i in range(1, len(partes) - 1, 2)} if len(partes) > 1 else {"es": texto.strip()}
        salida.append({"cabecera": cab, "es": cuerpos.get("es", texto.strip()), "pt": cuerpos.get("pt")})
    return salida


def cargar_en_base(conexion_admin) -> int:
    """Carga (reemplaza) los artículos en la base. Lo corre el rol de migraciones al desplegar."""
    n = 0
    with conexion_admin.cursor() as cur:
        cur.execute("TRUNCATE atencion.conocimiento_articulos")
        for a in articulos_en_disco():
            c = a["cabecera"]
            cur.execute("""insert into atencion.conocimiento_articulos (id, version, estado, audiencia, paises, criticidad,
                             titulo, cabecera, cuerpo_es, cuerpo_pt, busqueda)
                           values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,
                             setweight(to_tsvector('spanish', %s), 'A') || to_tsvector('spanish', %s) ||
                             to_tsvector('portuguese', coalesce(%s, '')))""",
                        (c["id"], c["version"], c["estado"], c["audiencia"], c["paises"], c["criticidad"], c["titulo"],
                         json.dumps(c, default=str), a["es"], a["pt"], c["titulo"], a["es"], a["pt"]))
            n += 1
        # Un artículo que el cortacircuitos retiró sigue retirado al volver a cargar, hasta que se reactive o cambie de
        # versión: volver a desplegar no lo reactiva.
        cur.execute("""update atencion.conocimiento_articulos a set estado = 'inactivo'
                       where exists (select 1 from atencion.conocimiento_eventos e
                                     where e.articulo = a.id and e.version = a.version and e.evento = 'cortacircuitos'
                                       and not exists (select 1 from atencion.conocimiento_eventos r
                                                       where r.articulo = e.articulo and r.version = e.version
                                                         and r.evento = 'reactivado' and r.id > e.id))""")
    return n


def resultado(c, art: dict, ok: bool) -> str | None:
    """Cortacircuitos (GOBERNANZA §11.8): una respuesta con el artículo pasó o no la verificación al primer intento. Al
    llegar al tope de fallas seguidas, la base lo retira (inactivo) y deja el evento; devuelve el estado resultante."""
    return c.execute("select atencion.resultado_articulo(%s, %s, %s, %s) e",
                     (art["id"], art["version"], ok, CORTACIRCUITOS_FALLAS)).fetchone()["e"]


def _estados_servibles() -> tuple[str, ...]:
    return ("publicado", "pendiente_aprobacion") if os.environ.get("CONOCIMIENTO_INCLUIR_PENDIENTES") == "1" else ("publicado",)


FUENTES_CAMBIADAS = RAIZ / "artefactos" / "fuentes_cambiadas.json"


def fuentes_cambiadas() -> set[str]:
    """Claves de fuentes que cambiaron y nadie revisó todavía (scripts/vigilar_fuentes.py, GOBERNANZA §11.6)."""
    return set(json.loads(FUENTES_CAMBIADAS.read_text(encoding="utf-8"))) if FUENTES_CAMBIADAS.exists() else set()


def vigente(cab: dict, hoy: date) -> bool:
    if cab.get("estado") not in _estados_servibles():
        return False
    if cab.get("criticidad") == "alta" and set(cab.get("fuentes") or []) & fuentes_cambiadas():
        return False                                  # su fuente cambió: se trata como vencido hasta revisarla
    revisar = cab.get("revisar_antes_de")
    if cab.get("criticidad") == "alta" and revisar and date.fromisoformat(str(revisar)) < hoy:
        return False                                  # criticidad alta vencida: mejor callar que decir algo vencido
    return True


@functools.lru_cache(maxsize=1)
def _fuentes_de_datos() -> dict:
    politica = {p.stem: yaml.safe_load(p.read_text()) for p in (RAIZ / "politica").glob("*.yaml")}
    config = {p.stem: yaml.safe_load(p.read_text()) for p in (RAIZ / "config").glob("*.yaml")}
    return {"politica": politica, "config": config}


def resolver_datos(cab: dict) -> dict[str, str]:
    """{marcador: valor} desde la política o la configuración; la fuente determinística siempre gana."""
    fuentes = _fuentes_de_datos()
    salida = {}
    for marcador, ruta in (cab.get("datos") or {}).items():
        partes = ruta.split(".")
        valor = fuentes[partes[0]]
        for p in partes[1:]:
            valor = valor.get(p) if isinstance(valor, dict) else None
        if valor is None:
            raise KeyError(f"{cab['id']}: {ruta} no existe")
        salida[marcador] = str(valor)
    return salida


def temas(audiencia: str = "publico", hoy: date | None = None) -> dict[str, str]:
    """Catálogo de temas para el Intérprete: se genera de los artículos servibles (D-14)."""
    hoy = hoy or date.today()
    return {a["cabecera"]["id"]: a["cabecera"]["titulo"] for a in articulos_en_disco()
            if a["cabecera"]["audiencia"] == audiencia and vigente(a["cabecera"], hoy)}


def _fila_a_articulo(f: dict, idioma: str) -> dict:
    cab = f["cabecera"]
    # El cuerpo viene en el idioma pedido si el artículo lo tiene; si no, en el base y lo dice: un respaldo nunca es
    # invisible (el cliente recibiría contenido sin traducción revisada).
    cuerpos = {"es": f["cuerpo_es"], "pt": f["cuerpo_pt"]}
    idioma_cuerpo = idioma if cuerpos.get(idioma) else IDIOMA_BASE
    return {"id": f["id"], "version": f["version"], "titulo": f["titulo"], "cuerpo": cuerpos[idioma_cuerpo],
            "idioma_cuerpo": idioma_cuerpo, "datos": resolver_datos(cab), "criticidad": f["criticidad"]}


def servir(c, tema: str, pais: str | None, idioma: str, hoy: date) -> dict | None:
    f = c.execute("""select * from atencion.conocimiento_articulos where id = %s and estado = any(%s)
                     order by version desc limit 1""", (tema, list(_estados_servibles()))).fetchone()
    if f is None or not vigente(f["cabecera"], hoy) or (pais and pais not in f["paises"]):
        return None
    art = _fila_a_articulo(f, idioma)
    c.execute("insert into atencion.conocimiento_eventos (articulo, version, evento, detalle) values (%s,%s,'consultado',%s)",
              (f["id"], f["version"], json.dumps({"via": "tema"})))
    return art


def buscar(c, texto: str, pais: str | None, idioma: str, hoy: date, audiencia: str = "publico", limite: int = 1,
           todas: bool = False) -> list[dict]:
    """Texto completo en español y portugués; la RLS ya limita al cliente a los públicos.
    `todas`: el artículo debe contener todas las palabras de la consulta (por defecto basta una: sirve para el mensaje libre)."""
    union = "&" if todas else "|"
    consulta = f"""(replace(plainto_tsquery('spanish', %(t)s)::text, '&', '{union}')::tsquery ||
                   replace(plainto_tsquery('portuguese', %(t)s)::text, '&', '{union}')::tsquery)"""
    filas = c.execute(f"""select *, ts_rank(busqueda, {consulta}) as rango from atencion.conocimiento_articulos
                          where audiencia = %(a)s and estado = any(%(e)s) and busqueda @@ {consulta}
                          order by rango desc limit 5""",
                      {"t": texto, "a": audiencia, "e": list(_estados_servibles())}).fetchall()
    salida = []
    for f in filas:
        if f["rango"] < RANGO_MINIMO_BUSQUEDA or not vigente(f["cabecera"], hoy) or (pais and pais not in f["paises"]):
            continue
        salida.append({**_fila_a_articulo(f, idioma), "rango": float(f["rango"])})
        if len(salida) >= limite:
            break
    return salida
