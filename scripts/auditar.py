"""Reconstruye una conversación desde la terminal (A13): quién hizo qué, dónde, cuándo y qué falló.

Uso: python scripts/auditar.py T-000123 | R-000123 | c_...
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from servicio.registro.auditoria import linea_de_tiempo, resolver_referencia  # noqa: E402

cid = resolver_referencia(sys.argv[1])
if cid is None:
    sys.exit(f"no se encontró {sys.argv[1]}")
d = linea_de_tiempo(cid)
print(f"conversación {cid} · reclamos {d['reclamos'] or '—'} · casos {d['casos_humanos'] or '—'}")
for e in d["eventos"]:
    marca = "  " if e["resultado"] in ("ok", "completada", "no_aplica") else "✗ "
    print(f"{marca}{e['hora']:%H:%M:%S} {e['quien'][:24]:24} {e['donde'][:28]:28} {e['que'][:30]:30} {e['resultado']:10} "
          f"{json.dumps(e['detalle'], ensure_ascii=False, default=str)[:160]}")
print(f"fallas: {len(d['fallas'])}")
