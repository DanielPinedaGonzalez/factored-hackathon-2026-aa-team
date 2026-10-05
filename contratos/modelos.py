"""Estructuras compartidas (CONTRATOS.md). Una sola definición; los módulos solo importan de aquí."""
from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Cerrado(BaseModel):
    """Base de los contratos: campos desconocidos rechazados."""
    model_config = ConfigDict(extra="forbid")


class Nodo(str, Enum):
    N0 = "SIN_SESION"
    N1 = "AUTENTICANDO"
    N2 = "ESCUCHANDO"
    N3 = "BUSCANDO_CARGO"
    N4 = "ACLARANDO"
    N5 = "MOSTRANDO_HECHOS"
    N6 = "EVALUANDO"
    N7 = "PROPONIENDO"
    N8 = "EJECUTANDO"
    N9 = "VERIFICANDO"
    N10 = "RESUELTO"
    N11 = "TRASPASO"
    N12 = "CERRADO_SIN_RECLAMO"
    N13 = "FUERA_DE_ALCANCE"
    N14 = "ABSTENCION"


# ---------- A1: interpretación ----------

class Monto(Cerrado):
    valor: float
    moneda: str | None = None
    aproximado: bool = False


class Cuando(Cerrado):
    tipo: Literal["absoluta", "relativa", "dia_semana"]
    valor: str


class CargoReferido(Cerrado):
    refiere_a: str = "nuevo"          # alias existente (C1...) o "nuevo"
    monto: Monto | None = None
    cuando: Cuando | None = None
    descripcion: str | None = None    # cómo nombró el cliente el movimiento; la compara el Comparador (A3b)

    @model_validator(mode="before")
    @classmethod
    def _estado_guardado_anterior(cls, v):
        """Conversaciones guardadas antes del campo único: el comercio o el canal dichos pasan a la descripción."""
        if isinstance(v, dict) and ("comercio_texto" in v or "canal" in v):
            v = dict(v)
            partes = [p for p in (v.pop("comercio_texto", None), v.pop("canal", None)) if p]
            v.setdefault("descripcion", " ".join(partes) or None)
        return v


class Comando(Cerrado):
    nombre: str
    args: list[str] = Field(default_factory=list)


class Interpretacion(Cerrado):
    comandos: list[Comando] = Field(default_factory=list)
    tipo_disputa_propuesto: str | None = None
    tipo_evidencia: str | None = None
    idioma: Literal["es", "pt", "otro"] = "es"
    cargos_referidos: list[CargoReferido] = Field(default_factory=list, max_length=5)
    reconoce: Literal["si", "no", "no_seguro", "ninguna"] = "ninguna"
    senales_riesgo: list[str] = Field(default_factory=list)
    datos_secretos: list[str] = Field(default_factory=list)   # tramos literales; el código los ubica y borra
    borrador_respuesta: str = ""


# ---------- A2: estado de la conversación ----------

class CargoEnDiscusion(Cerrado):
    alias: str
    atributos: dict[str, str]          # ya formateados para mostrar; viajan al modelo como marcadores
    estado: Literal["candidato", "mostrado", "reconocido", "no_reconocido", "reclamado", "descartado"] = "candidato"
    transaction_ref_interno: str       # nunca sale hacia un modelo


class AccionPendiente(Cerrado):
    codigo: str
    alias: str | None = None
    action_intent_id: str
    session_id: str
    expira: datetime


class Turno(Cerrado):
    turno: int
    rol: Literal["cliente", "asistente", "asesor", "sistema"]
    texto_con_marcadores: str


class Adjunto(Cerrado):
    adjunto_id: str
    tipo: str
    tamano: int
    adjuntado_a: str | None = None


class EstadoConversacion(Cerrado):
    conversation_id: str
    version: int = 0
    nodo: Nodo = Nodo.N0
    ultima_pregunta: dict | None = None
    cargos: list[CargoEnDiscusion] = Field(default_factory=list)
    opciones_mostradas: list[str] = Field(default_factory=list)   # alias válidos para `elegir`
    accion_pendiente: AccionPendiente | None = None
    senales_riesgo: list[str] = Field(default_factory=list)      # acumulativo, nunca se borra
    datos_dados: dict[str, str] = Field(default_factory=dict)
    idioma: Literal["es", "pt", "otro"] = "es"
    idioma_pedido: bool = False                                  # el cliente lo pidió: ningún mensaje lo cambia solo
    historial: list[Turno] = Field(default_factory=list)
    pila_temas: list[dict] = Field(default_factory=list)
    progreso: int = 0
    data_as_of: date | None = None
    adjuntos: list[Adjunto] = Field(default_factory=list)
    sin_modelo: bool = False
    tokens_consumidos: int = 0        # presupuesto por conversación (A12): al agotarse, pasa a una persona
    identidad_verificada: bool = False
    tipo_disputa: str | None = None
    reclamos_abiertos: list[str] = Field(default_factory=list)   # números de caso visibles de esta conversación
    traspaso_id: str | None = None
    no_entendidos: int = 0            # mensajes seguidos cuya interpretación fue ilegible: el primero se repregunta, el segundo pasa a una persona


# ---------- A4: política ----------

class HechosVerificados(Cerrado):
    """Salen de la base y de A5, nunca del modelo. Sin segmento del cliente (D-17)."""
    autenticado: bool
    accion: str
    candidatos: int = 0
    cargo_confirmado: bool = False
    estado_transaccion: str | None = None
    monto_usd: float | None = None            # None = desconocido
    dias_desde_transaccion: int | None = None
    jurisdiccion: str | None = None           # None = desconocida
    tipo_producto: str | None = None
    tipo_disputa: str | None = None
    senal_riesgo_p: float | None = None        # None = sin score
    supera_umbral_certificado: bool = False
    cota_fdr: float | None = None
    reclamos_previos_90d: int = 0
    senales_riesgo: list[str] = Field(default_factory=list)
    moneda_pais_coherente: bool = True
    bloqueo_pedido_por_cliente: bool = False
    recomendacion_del_sistema: bool = False


class Verificacion(Cerrado):
    id: Literal["V1", "V2", "V3", "V4"]
    cumple: bool
    numeros: dict[str, float | str | None] = Field(default_factory=dict)
    razon: str


class DecisionPolitica(Cerrado):
    camino: Literal["automatizable", "revision_humana", "abstencion"]
    acciones_permitidas: list[str]
    verificaciones: list[Verificacion]
    motivos: list[str] = Field(default_factory=list)
    plazo_normativo: dict | None = None
    version_politica: str
    hash_politica: str


# ---------- A8: redacción ----------

class ElementoComunicable(Cerrado):
    clase: Literal["AFIRMAR", "PREGUNTAR", "OFRECER", "EXACTO", "LITERAL", "NO_COMUNICAR", "RESPONDER", "RESULTADO"]
    contenido: str
    marcadores: dict[str, str] = Field(default_factory=dict)   # {"MONTO_1": "$ 180.000"} — el valor nunca va al modelo


class EstadoComunicable(Cerrado):
    elementos: list[ElementoComunicable] = Field(default_factory=list)
    preferencia: list[Literal["simple", "pasos_cortos"]] = Field(default_factory=list)
    es_primer_turno: bool = False
    articulo: dict | None = None      # {id, version, cuerpo} cuando hay RESPONDER


class Redaccion(Cerrado):
    texto: str
    saludo: str | None = None          # solo en el primer mensaje: lo escribe el modelo con el momento del día
    acciones_afirmadas: list[str] = Field(default_factory=list)
    idioma: Literal["es", "pt", "otro"] = "es"
    resumen_para_humano: str | None = None
    cita_articulo: str | None = None
    suficiencia: Literal["completa", "parcial", "insuficiente", "ambigua"] | None = None


# ---------- A10: traspaso ----------

class Nota(Cerrado):
    autor: str
    habilidad_destino: str
    texto: str


class PaqueteTraspaso(Cerrado):
    motivo_traspaso: list[str]
    solicitud: str | None = None
    sin_resumen_ia: bool = False
    servicio_intencion: str | None = None
    adjuntos: list[str] = Field(default_factory=list)
    hechos_verificados: list[dict] = Field(default_factory=list)
    acciones_realizadas: list[dict] = Field(default_factory=list)
    accion_pendiente: dict | None = None
    evidencia: dict = Field(default_factory=dict)      # solo para el asesor
    preguntas_abiertas: list[str] = Field(default_factory=list)
    idioma: str = "es"
    prioridad: int = 4
    habilidad_requerida: str = "general"
    plazo_normativo: dict | None = None
    identidad_verificada: bool = True
    notas: list[Nota] = Field(default_factory=list)
    conversation_id: str


# ---------- A13: registro ----------

class PasoRegistro(Cerrado):
    componente: str
    estado: Literal["ok", "fallo", "no_aplica"]
    detalle: dict = Field(default_factory=dict)
    latencia_ms: float | None = None


class RegistroTurno(Cerrado):
    turn_id: str
    conversation_id: str
    n: int
    versiones: dict[str, str]
    nodo_antes: str
    nodo_despues: str
    pasos: list[PasoRegistro]
    interpretacion: dict | None = None
    decision: dict | None = None
    tokens: dict[str, int] = Field(default_factory=dict)
    latencia_ms: float = 0.0
    creado: datetime
