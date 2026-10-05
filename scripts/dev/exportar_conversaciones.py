"""Exporta conversaciones reales (modelo real) tal como están guardadas en la base, a un Markdown liviano.

Uso: .venv/bin/python scripts/dev/exportar_conversaciones.py  →  una carpeta local de muestra (no se publica)
"""
import json, psycopg, yaml
from pathlib import Path
RAIZ = Path("/home/daniel/Documentos/013Foundings/hackaton/factored-hackathon-2026-aa-team")
casos = {c["id"]: c for c in yaml.safe_load((RAIZ / "evaluacion/ground_truth_cases.yaml").read_text())["casos"]}
ELEGIDOS = ["A1", "B2", "A4", "C1", "C3", "C5", "D2", "B6", "V5", "F5"]
c = psycopg.connect("postgresql://aa_admin:aa_admin_local@127.0.0.1:5433/aa_team")
def ultima(caso):
    return c.execute("""select t.conversation_id from atencion.turnos t join operacion.registro_turnos r using (conversation_id)
        where t.conversation_id like %s and r.registro->'versiones'->>'modelo' like '%%gpt-oss%%'
        group by 1 order by max(t.creado) desc limit 1""", (f"eval_{caso}_%",)).fetchone()
lineas = ["# Conversaciones reales: muestra", "",
          "Diez conversaciones de la evaluación con el modelo real (`openai/gpt-oss-120b` en Groq), copiadas tal como",
          "quedaron en la base: el texto del cliente y la respuesta final del asistente, sin editar. El cliente es un",
          "personaje simulado que habla con clientes y movimientos reales de los datos. Debajo de cada respuesta, lo que",
          "la pantalla mostró además del texto (tarjetas, formularios, avisos) y, al final, lo que quedó en la base.", "",
          "Son grabaciones del 26 y 27 de septiembre, con versiones anteriores de los prompts. Se dejan como quedaron;",
          "tres cosas que se ven en ellas ya cambiaron: la presentación dice \"asistente automática\" (hoy \"virtual\");",
          "en B2, turno 3, el Redactor copió la estructura interna al cliente (desde entonces el verificador rechaza",
          "cualquier código interno); y en la conversación de la demo, la transferencia aparece como el comercio",
          "\"Transfer\" (hoy se nombra por su tipo).", ""]
DEMO = ("demo", "c_wsYQE83d1iDx3Q", {"meta": "Conversación real en la demo: una transferencia que el cliente no reconoce.",
                                     "idioma": "es", "personaje": "una persona del equipo"})
for caso in ELEGIDOS + ["demo"]:
    if caso == "demo":
        cid, d = DEMO[1], DEMO[2]
    else:
        fila = ultima(caso)
        if not fila:
            continue
        cid, d = fila[0], casos[caso]
    turnos = c.execute("select n, rol, texto, respuesta, creado from atencion.turnos where conversation_id = %s order by n", (cid,)).fetchall()
    lineas += [f"## {caso} · {d['meta']}", "",
               f"Conversación `{cid}` · {turnos[0][4]:%Y-%m-%d %H:%M} UTC · idioma {d['idioma']} · personaje {d.get('personaje', '—')}", ""]
    for n, rol, texto, resp, _ in turnos:
        if rol == "cliente":
            lineas += [f"**Cliente:** {texto}", ""]
        else:
            r = resp or {}
            final = (r.get("texto_final") or "").strip()
            quien = "Asistente" if rol == "asistente" else "Sistema"
            lineas += [f"**{quien}:** " + (final.replace("\n", "  \n") if final else "*(sin texto: solo interfaz)*"), ""]
            ui = (r.get("salida") or {}).get("ui") or []
            if ui:
                lineas += ["> Pantalla: " + "; ".join(
                    f"{u['tipo']} " + json.dumps({k: v for k, v in u.items() if k != "tipo" and v not in (None, "", [])}, ensure_ascii=False)
                    for u in ui), ""]
    # Lo que hizo el sistema, desde el registro de cada turno (nunca se borra): acciones verificadas y traspasos
    hechos = []
    for (reg,) in c.execute("select registro from operacion.registro_turnos where conversation_id = %s order by creado", (cid,)):
        for p in reg.get("pasos", []):
            det = p.get("detalle") or {}
            if p["componente"] == "verificacion_accion" and p["estado"] == "ok":
                hechos.append(f"{det.get('accion')} verificado")
            elif p["componente"] == "traspaso" and p["estado"] == "ok":
                hechos.append(f"traspaso {det.get('numero')} a {det.get('habilidad')}, prioridad {det.get('prioridad')}")
            elif p["componente"] == "politica":
                hechos.append(f"política: {det.get('camino')}" + (f" ({', '.join(det.get('motivos') or [])})" if det.get("motivos") else ""))
    lineas += ["**Lo que hizo el sistema (registro de turnos):** " + ("; ".join(dict.fromkeys(hechos)) or "ninguna acción ni traspaso"),
               "", "---", ""]
out = RAIZ / "privado" / "CONVERSACIONES_MUESTRA.md"
out.write_text("\n".join(lineas), encoding="utf-8")
print(out, len(lineas), "líneas")
