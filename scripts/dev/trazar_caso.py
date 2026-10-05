"""Reconstruye, turno a turno, lo que hizo cada componente en un caso de una corrida guardada (sin gastar cupo del modelo).

Para cada turno muestra el nodo, las señales, lo que describió el Intérprete, lo que consultó el buscador de conocimiento,
la política y su decisión, las herramientas y el texto que vio el cliente. Es la herramienta para diagnosticar un fallo:
primero se ve QUÉ componente se desvió y recién después se discute por qué.

Uso: python scripts/dev/trazar_caso.py CORRIDA.json CASO [CASO ...]
     python scripts/dev/trazar_caso.py --todas-las-fallas CORRIDA.json
"""
import json
import sys
from pathlib import Path

COMPONENTES = ("interprete", "conocimiento", "resolutor", "politica", "herramienta", "verificacion_accion", "traspaso", "siguiente")


def trazar(corrida: dict, caso: str) -> None:
    res = next((r for r in corrida["resultados"] if r["caso"] == caso), None)
    conv = corrida["conversaciones"].get(caso)
    if res is None or conv is None:
        print(f"{caso}: no está en esta corrida")
        return
    print("=" * 110)
    print(f"{caso} | {'OK' if res['paso'] else 'MAL'} | fallas: {res['fallas'] + res['inseguro']} | nodo final: {res['nodo_final']} | herramientas: {res['herramientas']}")
    for i, (salida, reg) in enumerate(zip(conv["salidas"], conv["registros"]), 1):
        print(f" -- turno {i}: {reg.get('nodo_antes')} → {reg.get('nodo_despues')} · señales {reg.get('senales')} · sin_modelo={reg.get('sin_modelo')}")
        for paso in reg["pasos"]:
            if paso["componente"] in COMPONENTES:
                print(f"      {paso['componente']:20} {json.dumps(paso['detalle'], ensure_ascii=False)[:300]}")
        if reg.get("decision"):
            d = reg["decision"]
            print(f"      decisión de política: {d.get('camino')} · motivos {d.get('motivos')}")
        print("      cliente lee:", (salida.get("texto") or "(solo interfaz)")[:170].replace("\n", " "))


def main() -> None:
    args = sys.argv[1:]
    if not args:
        sys.exit(__doc__)
    todas = args[0] == "--todas-las-fallas"
    corrida = json.loads(Path(args[1] if todas else args[0]).read_text())
    casos = [r["caso"] for r in corrida["resultados"] if not r["paso"]] if todas else args[1:]
    for c in casos:
        trazar(corrida, c)


if __name__ == "__main__":
    main()
