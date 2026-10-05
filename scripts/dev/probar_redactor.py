"""Compara la redacción de dos modelos con el mismo estado comunicable (llamadas reales, pocas)."""
import os
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ))
for l in (RAIZ / ".env").read_text().splitlines():
    if "=" in l and not l.startswith("#"):
        k, v = l.strip().split("=", 1)
        os.environ.setdefault(k, v)
from contratos.modelos import EstadoConversacion, Turno  # noqa: E402
from servicio.llm.cliente import ProveedorOpenAI  # noqa: E402
from servicio.recursos.guardian import Guardian  # noqa: E402
from servicio.redactor.estado_comunicable import Constructor  # noqa: E402
from servicio.redactor.redactor import redactar, RedaccionFallida  # noqa: E402

b = Constructor("es")
b.afirmar("cargo", "C1", {"COMERCIO": "x", "FECHA": "x", "HORA": "x", "CIUDAD": "x", "MONTO": "x", "PRODUCTO": "x"})
b.ofrecer("abrir_reclamo", "C1")
b.preguntar("confirmar_accion", "C1")
b.afirmar("abrir_no_asegura_devolucion")
ec = b.construir()
estado = EstadoConversacion(conversation_id="x", historial=[Turno(turno=1, rol="cliente", texto_con_marcadores="no reconozco un cobro de ayer")])
for modelo in sys.argv[1:]:
    m = ProveedorOpenAI("groq", modelo, os.environ["GROQ_API_KEY_3"], Guardian(espacio_min_s=4, espera_max_s=60))
    for i in range(3):
        try:
            r = redactar(m, estado, ec, "es", set(), None)
            print(modelo, r.origen, r.errores[:1], "|", r.redaccion.texto[:160].replace("\n", " "))
        except RedaccionFallida as e:
            print(modelo, "FALLA", str(e)[:160])
