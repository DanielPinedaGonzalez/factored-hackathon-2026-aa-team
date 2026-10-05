# Diagnóstico: el centro de contacto y el proceso de quejas (asesores, prioridad, tiempos, segmento).
# Solo biblioteca estándar y lectura por streaming: cabe en 3 GB sin DuckDB.
import csv, glob, os, statistics as st
from collections import Counter, defaultdict
from datetime import datetime

D = os.path.expanduser("~/Documentos/013Foundings/hackaton/data/")


def filas(tabla):
    for f in sorted(glob.glob(D + tabla + "/**/*.csv", recursive=True)):
        with open(f, encoding="utf-8-sig") as h:
            yield from csv.DictReader(h)


segmento = {r["customer_id"]: r["segment"] for r in csv.DictReader(open(D + "customers.csv", encoding="utf-8-sig"))}
asesores = {r["agent_id"]: r for r in csv.DictReader(open(D + "service_agents.csv", encoding="utf-8-sig"))}

# 1. Plantilla de asesores
activos = [a for a in asesores.values() if a["agent_status"] == "Active"]
digitales = [a for a in activos if a["agent_type"] in ("Digital", "Hybrid")]
print("asesores", len(asesores), "activos", len(activos), "digitales activos", len(digitales))
print("especialidad", Counter(a["specialty"] or "(vacía)" for a in asesores.values()).most_common())
print("idiomas", Counter(a["languages"] for a in asesores.values()))
print("estado", Counter(a["agent_status"] for a in asesores.values()), "turno", Counter(a["work_shift"] for a in asesores.values()))
for esp in ("Fraudes", "Quejas y Reclamos", ""):
    g = [a for a in digitales if a["specialty"] == esp]
    pt = [a for a in g if "portugués" in a["languages"]]
    print("digital", repr(esp), len(g), "con portugués", len(pt), "turnos PT", dict(Counter(a["work_shift"] for a in pt)))

# 2. Proceso de quejas
prioridad, sla, sin_asesor, esp_asignado = Counter(), Counter(), 0, Counter()
primera, resolucion = defaultdict(list), defaultdict(list)
n = 0
for r in filas("complaints"):
    n += 1
    p = r["priority"]
    prioridad[p] += 1
    sla[(p, r["sla_breached"])] += 1
    a = asesores.get(r["assigned_agent_id"])
    if a is None:
        sin_asesor += 1
    else:
        esp_asignado[a["specialty"] or "(vacía)"] += 1
    try:
        primera[p].append((datetime.fromisoformat(r["first_response_date"]) - datetime.fromisoformat(r["creation_date"])).total_seconds() / 3600)
    except ValueError:
        pass
    try:
        resolucion[p].append(float(r["resolution_days"]))
    except ValueError:
        pass
print("quejas", n, "prioridad", prioridad, "sin asesor", sin_asesor)
print("especialidad del asesor asignado", esp_asignado.most_common())
for p in prioridad:
    vencidas = sla[(p, "True")] / (sla[(p, "True")] + sla[(p, "False")])
    print(p, "primera respuesta h (mediana)", round(st.median(primera[p]), 1), "resolución días (mediana)",
          st.median(resolucion[p]), "SLA vencido", round(vencidas, 3))

# 3. Espera por segmento en llamadas
espera = defaultdict(list)
for r in filas("call_center_interactions"):
    try:
        espera[segmento.get(r["customer_id"], "?")].append(float(r["wait_time_seconds"]))
    except ValueError:
        pass
for s, v in espera.items():
    print("espera s", s, len(v), "mediana", st.median(v))
