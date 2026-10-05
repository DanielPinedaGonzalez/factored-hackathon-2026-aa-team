"""Estudio del trato (tú frente a vos o usted) del Redactor con el modelo real, antes de cambiar nada en producción.

Genera N redacciones por estado comunicable típico con el prompt de una versión dada (archivo o commit), y un juez de
otra familia de modelos (el del simulador, E1) clasifica el trato de cada una. Sin listas de palabras: el trato es una
propiedad del texto que juzga un modelo, igual que en el resto del sistema.

Uso: python scripts/dev/medir_trato.py N [commit_del_prompt_anterior]
"""
import os
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ))
for l in (RAIZ / ".env").read_text().splitlines():
    if "=" in l and not l.startswith("#"):
        k, v = l.strip().split("=", 1)
        os.environ.setdefault(k, v)
from contratos.modelos import EstadoConversacion  # noqa: E402
from servicio.llm.cliente import ProveedorOpenAI  # noqa: E402
from servicio.llm.pool import llaves_del_papel  # noqa: E402
from servicio.recursos.guardian import Guardian  # noqa: E402
from servicio.redactor import redactor  # noqa: E402
from servicio.redactor.estado_comunicable import Constructor  # noqa: E402

JUEZ = ("Clasifica el trato gramatical con que el texto se dirige al lector, según la conjugación y los pronombres de "
        "segunda persona. Responde con una sola palabra: tu, vos, usted, mixto o ninguno.")


def estados() -> list:
    salida = []
    a = Constructor("es", True)
    a.afirmar("identidad_requerida"); a.afirmar("proteccion_tras_identidad"); a.afirmar("persona_disponible")
    salida.append(a)
    b = Constructor("es")
    b.resultado("accion_completada", "abrir_reclamo", {"CASO": "R-000123"}); b.afirmar("abrir_no_asegura_devolucion")
    b.preguntar("otra_ayuda")
    salida.append(b)
    c = Constructor("es")
    c.afirmar("traspaso"); c.afirmar("persona_disponible")
    salida.append(c)
    return salida


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 5
    versiones = {"actual": (RAIZ / "prompts" / "redactor.md").read_text(encoding="utf-8")}
    if len(sys.argv) > 2:
        versiones[sys.argv[2]] = subprocess.run(["git", "show", f"{sys.argv[2]}:prompts/redactor.md"], capture_output=True,
                                                text=True, cwd=RAIZ).stdout
    m = ProveedorOpenAI("groq", "openai/gpt-oss-120b", llaves_del_papel("linea_base")[0][1], Guardian(espacio_min_s=20, espera_max_s=120))
    juez = ProveedorOpenAI("groq", os.environ.get("MODELO_SIMULADOR", "qwen/qwen3.8-27b"),
                           llaves_del_papel("simulador")[0][1], Guardian(espacio_min_s=5), temperatura=0.0)
    original = redactor.RUTA_PROMPT
    for nombre, texto in versiones.items():
        tmp = RAIZ / "scripts/dev" / f".redactor_{nombre}.md"
        tmp.write_text(texto, encoding="utf-8")
        redactor.RUTA_PROMPT = tmp
        conteo: dict[str, int] = {}
        for ec in estados():
            for _ in range(n):
                try:
                    r = redactor.redactar(m, EstadoConversacion(conversation_id="estudio"), ec.construir(), "es", {"abrir_reclamo"}, None)
                except redactor.RedaccionFallida as e:
                    print("  falla:", e)
                    continue
                trato = juez.completar(JUEZ, r.redaccion.texto, "juzgar_trato", 20).texto.strip().lower().split()[0]
                conteo[trato] = conteo.get(trato, 0) + 1
        print(f"{nombre}: {sum(conteo.values())} redacciones · trato {conteo}", flush=True)
        tmp.unlink()
    redactor.RUTA_PROMPT = original


if __name__ == "__main__":
    main()
