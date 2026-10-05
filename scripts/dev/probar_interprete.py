"""Prueba puntual del Intérprete con el modelo real (una llamada por mensaje). Uso: python scripts/dev/probar_interprete.py "msg" ..."""
import os
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ))
for l in (RAIZ / ".env").read_text().splitlines():
    if "=" in l and not l.startswith("#"):
        k, v = l.strip().split("=", 1)
        os.environ.setdefault(k, v)
os.environ["CONOCIMIENTO_INCLUIR_PENDIENTES"] = "1"
from contratos.modelos import EstadoConversacion  # noqa: E402
from servicio.conocimiento.conocimiento import temas  # noqa: E402
from servicio.interprete.interprete import mensaje_usuario, prompt_sistema  # noqa: E402
from servicio.llm.cliente import ProveedorOpenAI  # noqa: E402
from servicio.recursos.guardian import Guardian  # noqa: E402

m = ProveedorOpenAI("groq", os.environ.get("MODELO_INTERPRETE", "openai/gpt-oss-120b"), os.environ["GROQ_API_KEY"],
                    Guardian(espacio_min_s=4), temperatura=0.0)
for msg in sys.argv[1:]:
    r = m.completar(prompt_sistema(temas()), mensaje_usuario(EstadoConversacion(conversation_id="x"), msg), "interpretar")
    print("====", msg, f"({r.tokens_entrada}+{r.tokens_salida})\n" + r.texto)
