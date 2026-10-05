"""Estado comunicable (CONTRATOS A8): la lista cerrada de lo que un turno puede decir, por clase.

Lo arma el orquestador con hechos verificados. Al modelo va solo la estructura con los nombres de los marcadores;
los valores se quedan aquí y el código los pone después de verificar el texto. Los permisos se aplican al armarlo:
la señal de riesgo y el camino interno nunca entran (NO_COMUNICAR).
"""
from __future__ import annotations

import json

from contratos import catalogo
from contratos.modelos import ElementoComunicable, EstadoComunicable


class Constructor:
    def __init__(self, idioma: str, es_primer_turno: bool = False, preferencia: list[str] | None = None):
        self.idioma = idioma
        self._elementos: list[ElementoComunicable] = []
        self._contador: dict[str, int] = {}
        self.es_primer_turno = es_primer_turno
        self.preferencia = preferencia or []
        self.articulo: dict | None = None
        self.hechos_usados: list[str] = []

    def _marcadores(self, valores: dict[str, str] | None) -> dict[str, str]:
        salida = {}
        for base, valor in (valores or {}).items():
            n = self._contador.get(base, 0) + 1
            self._contador[base] = n
            salida[f"{base}_{n}"] = str(valor)
        return salida

    def _agregar(self, clase: str, contenido: dict, valores: dict | None = None, nombres_fijos: dict | None = None):
        marcadores = self._marcadores(valores)
        marcadores.update(nombres_fijos or {})
        self._elementos.append(ElementoComunicable(clase=clase, contenido=json.dumps(contenido, ensure_ascii=False),
                                                   marcadores=marcadores))
        return marcadores

    def afirmar(self, hecho: str, sobre: str | None = None, valores: dict | None = None, **extra) -> dict:
        if hecho not in catalogo.cargar()["hechos"]:
            raise ValueError(f"hecho fuera del catálogo: {hecho}")
        self.hechos_usados.append(hecho)
        return self._agregar("AFIRMAR", {"hecho": hecho, "sobre": sobre, **extra}, valores)

    def preguntar(self, pregunta: str, sobre: str | list | None = None, **extra) -> None:
        if pregunta not in catalogo.cargar()["preguntas"]:
            raise ValueError(f"pregunta fuera del catálogo: {pregunta}")
        self._agregar("PREGUNTAR", {"pregunta": pregunta, "sobre": sobre, **extra})

    def ofrecer(self, accion: str, sobre: str | None = None, valores: dict | None = None) -> dict:
        return self._agregar("OFRECER", {"accion": accion, "sobre": sobre}, valores)

    def exacto(self, que: str, valores: dict) -> dict:
        return self._agregar("EXACTO", {"exacto": que}, valores)

    def resultado(self, hecho: str, accion: str, valores: dict | None = None) -> dict:
        self.hechos_usados.append(hecho)
        return self._agregar("RESULTADO", {"hecho": hecho, "accion": accion}, valores)

    def responder(self, articulo: dict) -> None:
        """El cuerpo del artículo trae marcadores propios ({mx_dias_dictamen}); sus valores salen de la política."""
        self.articulo = articulo
        cuerpo = articulo["cuerpo"]
        for k in articulo.get("datos", {}):
            cuerpo = cuerpo.replace("{" + k + "}", "{ART_" + k.upper() + "}")
        self._agregar("RESPONDER", {"articulo": f"{articulo['id']}@{articulo['version']}", "cuerpo": cuerpo},
                      nombres_fijos={f"ART_{k.upper()}": v for k, v in articulo.get("datos", {}).items()})

    def construir(self) -> EstadoComunicable:
        return EstadoComunicable(elementos=list(self._elementos), preferencia=self.preferencia,
                                 es_primer_turno=self.es_primer_turno, articulo=self.articulo)

    @property
    def vacio(self) -> bool:
        return not self._elementos


def para_modelo(ec: EstadoComunicable) -> str:
    """JSON sin valores: clase, contenido y los nombres de los marcadores."""
    return json.dumps([{"clase": e.clase, **json.loads(e.contenido), "marcadores": ["{" + m + "}" for m in sorted(e.marcadores)]}
                       for e in ec.elementos], ensure_ascii=False, indent=0)


def marcadores(ec: EstadoComunicable) -> dict[str, str]:
    salida: dict[str, str] = {}
    for e in ec.elementos:
        salida.update(e.marcadores)
    return salida


def obligatorios(ec: EstadoComunicable) -> set[str]:
    return {m for e in ec.elementos if e.clase == "EXACTO" for m in e.marcadores}
