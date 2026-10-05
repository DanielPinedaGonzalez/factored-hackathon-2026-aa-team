"""Candados (INV-TEXTO, INV-EVAL, INV-SECRETOS): pruebas que fallan si alguien mete lo que el diseño prohíbe."""
import ast
import re
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
PY = [p for p in (RAIZ / "servicio").rglob("*.py")]
AL_CLIENTE = re.compile(r"[¿¡]|\b(tu|tus|te|usted|puedes|tienes|quieres|necesitas|podemos|lamentamos|você|seu|sua|olá|hola|gracias|listo)\b", re.I)
PALABRAS_DE_FRAUDE = re.compile(r"robaron|(?<![_\w])estafa(?![_\w])|hackea|me llamaron|mi clave|no me llega", re.I)


def _literales(ruta: Path):
    arbol = ast.parse(ruta.read_text(encoding="utf-8"))
    docstrings = set()
    for n in ast.walk(arbol):
        if isinstance(n, (ast.Module, ast.FunctionDef, ast.ClassDef, ast.AsyncFunctionDef)) and n.body and \
                isinstance(n.body[0], ast.Expr) and isinstance(getattr(n.body[0], "value", None), ast.Constant):
            docstrings.add(id(n.body[0].value))
    for n in ast.walk(arbol):
        if isinstance(n, ast.Constant) and isinstance(n.value, str) and id(n) not in docstrings:
            yield n.lineno, n.value


def test_ningun_texto_al_cliente_en_python():
    hallados = [f"{p.relative_to(RAIZ)}:{l}: {v[:50]!r}" for p in PY for l, v in _literales(p) if AL_CLIENTE.search(v)]
    assert not hallados, "texto dirigido al cliente en código:\n" + "\n".join(hallados)


def test_ninguna_lista_de_palabras_sobre_el_mensaje():
    hallados = [f"{p.relative_to(RAIZ)}:{l}: {v[:50]!r}" for p in PY for l, v in _literales(p) if PALABRAS_DE_FRAUDE.search(v)]
    assert not hallados, "listas de palabras que interpretan al cliente:\n" + "\n".join(hallados)


def test_no_existe_catalogo_de_frases_para_el_cliente():
    permitidos = {"textos_legales.yaml"}       # la única excepción cerrada: textos legales LITERAL
    for y in (RAIZ / "config").glob("*.yaml"):
        texto = y.read_text(encoding="utf-8")
        if y.name not in permitidos:
            assert not re.search(r"^(mensajes|frases|respuestas|plantillas)\s*:", texto, re.M), y.name
    assert not list(RAIZ.rglob("mensajes_minimos*"))


def test_la_verdad_de_referencia_no_importa_la_politica():
    for p in (RAIZ / "evaluacion").rglob("*.py"):
        assert "politica" not in {a.split(".")[-1] for a in re.findall(r"(?:from|import)\s+([\w.]+)", p.read_text())}, p.name
    casos = (RAIZ / "evaluacion" / "ground_truth_cases.yaml").read_text()
    assert not re.search(r"politica\.[a-z]", casos)          # ninguna referencia a reglas de la política


def test_sin_llaves_en_el_repositorio():
    patron = re.compile(r"(gsk_[A-Za-z0-9]{20,}|sk-or-v1-[a-f0-9]{20,}|sk-ant-[A-Za-z0-9-]{20,})")
    for p in RAIZ.rglob("*"):
        if p.is_file() and ".git" not in p.parts and ".venv" not in p.parts and p.name != ".env" and p.suffix in (".py", ".md", ".yaml", ".yml", ".json", ".js", ".html", ".toml", ".txt"):
            assert not patron.search(p.read_text(errors="ignore")), p


# ---------- Reglas de escritura de lo que lee un modelo (ARQUITECTURA §8.6; reglas G de prompts) ----------
# Revisa nuestros propios textos, no el mensaje del cliente: los prompts ya armados con el catálogo inyectado, las
# descripciones del catálogo y los mensajes con que el código le pide una corrección al modelo.
EJEMPLO = re.compile(r"por ejemplo|p\. ?ej\.?|\bej\.|\be\.g\.|\bcomo por\b", re.I)
ABSOLUTO = re.compile(r"\b(nunca|jamás)\b", re.I)
IMPERATIVO_NEGADO = re.compile(r"\bno\s+(?!reconoc)\w+(?:as|es)\b", re.I)          # "no escribas", "no repitas"...
FRASE_CITADA = re.compile(r"[\"“«]([^\"”»\n]*\s[^\"”»\n]*)[\"”»]")               # una frase entre comillas = un ejemplo


def _textos_para_modelos() -> dict[str, str]:
    import yaml
    from servicio.interprete.interprete import prompt_sistema as p_interprete
    from servicio.redactor.redactor import prompt_sistema as p_redactor
    textos = {"prompt del Intérprete": p_interprete({"publico.tema": "Un tema"}), "prompt del Redactor": p_redactor(None)}
    for nombre in ("simulador", "linea_base", "comparador"):
        textos[f"prompts/{nombre}.md"] = (RAIZ / "prompts" / f"{nombre}.md").read_text(encoding="utf-8")
    cat = yaml.safe_load((RAIZ / "contratos" / "catalogo.yaml").read_text(encoding="utf-8"))

    def recorrer(nodo, ruta):
        if isinstance(nodo, dict):
            for k, v in nodo.items():
                recorrer(v, f"{ruta}.{k}")
        elif isinstance(nodo, str) and " " in nodo:
            textos[f"catálogo{ruta}"] = nodo
    recorrer(cat, "")
    for ruta in (RAIZ / "servicio" / "verificacion" / "redaccion.py", RAIZ / "servicio" / "interprete" / "lector.py",
                 RAIZ / "servicio" / "resolutor" / "comparador.py"):
        for l, v in _literales(ruta):
            if " " in v:
                textos[f"{ruta.relative_to(RAIZ)}:{l}"] = v
    return textos


def test_lo_que_lee_un_modelo_va_en_positivo_y_sin_ejemplos():
    hallados = []
    for donde, texto in _textos_para_modelos().items():
        for patron, regla in ((EJEMPLO, "ejemplo"), (ABSOLUTO, "absoluto negado"), (IMPERATIVO_NEGADO, "negación suelta"),
                              (FRASE_CITADA, "frase citada como ejemplo")):
            for m in patron.finditer(texto):
                hallados.append(f"{donde}: {regla}: {m.group(0)[:60]!r}")
    assert not hallados, "reglas de escritura para modelos:\n" + "\n".join(hallados)


def test_catalogo_define_sin_ejemplos_entre_parentesis():
    """Una descripción del catálogo dice qué es la cosa; una lista entre paréntesis la ancla a esos casos."""
    import yaml
    cat = yaml.safe_load((RAIZ / "contratos" / "catalogo.yaml").read_text(encoding="utf-8"))
    hallados = []
    for seccion in ("comandos", "campos", "tipos_disputa", "senales_riesgo", "hechos", "preguntas"):
        for k, v in cat[seccion].items():
            if re.search(r"\([^)]*,[^)]*\)", v):
                hallados.append(f"{seccion}.{k}: {v}")
    for s, d in cat["servicios"].items():
        for k, v in d["intenciones"].items():
            if re.search(r"\([^)]*,[^)]*\)", v):
                hallados.append(f"servicios.{s}.{k}: {v}")
    assert not hallados, "ejemplos entre paréntesis en el catálogo:\n" + "\n".join(hallados)


# ---------- Movimientos sin comercio (27-sep: "Transfer" se mostraba como si fuera una tienda) ----------

def test_ningun_dato_ausente_se_reemplaza_por_otro():
    """Un movimiento sin comercio se nombra por su tipo (marcador MOVIMIENTO); nunca se rellena el comercio con el tipo
    ni con un guion."""
    patron = re.compile(r"""\[["']comercio["']\]\s+or\b|get\(["']comercio["']\)\s+or\b|\bcomercio\s+or\s+t""")
    rutas = list((RAIZ / "servicio").rglob("*.py")) + list((RAIZ / "evaluacion").rglob("*.py")) + [RAIZ / "apps" / "web" / "app.js"]
    hallados = [f"{p.relative_to(RAIZ)}:{i}" for p in rutas for i, l in enumerate(p.read_text(encoding="utf-8").splitlines(), 1)
                if patron.search(l)]
    assert not hallados, "comercio rellenado con otro dato:\n" + "\n".join(hallados)


def test_todo_tipo_de_movimiento_de_los_datos_tiene_nombre_en_los_dos_idiomas():
    import yaml
    from servicio.herramientas.banco import TIPOS_CARGO
    nombres = yaml.safe_load((RAIZ / "config" / "formatos.yaml").read_text(encoding="utf-8"))["tipos_movimiento"]
    for idioma in ("es", "pt"):
        assert set(TIPOS_CARGO) | {"Deposit"} <= set(nombres[idioma]), idioma


def test_la_descripcion_del_cliente_se_compara_por_el_sentido_y_no_por_palabras():
    assert not (RAIZ / "servicio" / "resolutor" / "matching.py").exists()
    for p in PY:
        assert "matching" not in p.read_text(encoding="utf-8"), p
