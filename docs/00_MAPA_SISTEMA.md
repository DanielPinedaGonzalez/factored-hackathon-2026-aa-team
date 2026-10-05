# 00 — Mapa del sistema

**Diseño de arquitectura:** Daniel Pineda González  
**Qué responde:** dónde vive cada cosa, cómo se llama cada concepto y cómo se encadena cada decisión con su prueba.
Si un documento contradice a este mapa, se corrige uno de los dos.

## 1. Documentos

Una sola fuente por tema.

| Documento | Responde |
|---|---|
| `VISION.md` | Qué es, para qué banco, para quién y qué problema de negocio resuelve |
| `EXPERIENCIA_CLIENTE.md` | Qué le duele al cliente, qué se le promete y cómo vive el paso a una persona. Punto de partida del diseño |
| `01_DIAGNOSTICO.md` | Qué exige el reto y qué dicen los datos, medido |
| `02_PLAN.md` | Qué se construye con modelos, datos, evaluación y operación, y qué queda fuera |
| `ARQUITECTURA.md` | La arquitectura en arc42: componentes, grafo, contexto, clasificación, política, redacción, decisiones |
| `CONTRATOS.md` | Qué recibe, entrega y garantiza cada componente |
| `MODELO_DATOS.md` | Tablas, ciclos de vida, roles de base y retención |
| `ROLES_Y_ACCESOS.md` | Quién es quién, qué ve, qué hace, cómo entra y quién aprueba cada cambio |
| `PROCESOS.md` | Cómo fluye un caso entre todos los actores: enrutamiento, prioridades, desborde, turnos, investigación |
| `SEGURIDAD.md` | Amenazas, con su control y su prueba |
| `GOBERNANZA_DATOS_IA.md` | Qué datos hay, qué sale a la IA y a qué terceros, inventario de modelos, gobierno del conocimiento |
| `INTERFACES.md` | Qué pantallas hay, qué muestra cada una, quién la ve y de dónde sale cada dato |
| `CASOS.md` | Qué puede pasar, qué protocolo de la banca lo decide y qué hace el sistema |
| `DESPLIEGUE.md` | Cómo corre, cómo se sube, cómo se verifica y cómo se revierte |
| `REPORTE_EVALUACION.md` | Resultados medidos, con intervalos (generado por `evaluacion/reporte.py`) |
| `BIBLIOGRAFIA.md` | Todas las referencias en APA 7 (generado de `bibliografia/referencias.yaml`) |

## 2. Vocabulario canónico

Un concepto, un nombre. En código, en inglés; en documentos y en la interfaz, en español.

| Concepto | Nombre en documentos | Nombre en código | Definición | No confundir con |
|---|---|---|---|---|
| Puntaje del banco | `fraud_score` | `fraud_score` | Dato del organizador, 0-100, nulo en el 20% | La señal de riesgo |
| Señal de riesgo | señal de riesgo (`p`) | `risk_signal` | Salida de M1: probabilidad calibrada a partir del `fraud_score` (dos calibradores: presente y ausente) | "Probabilidad de que el cliente cometa fraude": nunca se presenta así |
| Umbral de bloqueo | τ | `block_threshold` | Artefacto versionado que produce el procedimiento LTT; nunca escrito a mano | La regla "≥ 50" (línea base B0) |
| Riesgo certificado | FDR de recomendación de bloqueo | `block_fdr` | Recomendaciones sobre legítimas / recomendaciones | FPR (se reporta, no se certifica) |
| Movimiento | movimiento | `transaction` | Una transacción del cliente en los datos, con su tipo (compra, retiro, transferencia, pago, ajuste, depósito); se nombra por su tipo en el idioma del cliente | Cargo en un comercio: más de 7 de cada 10 movimientos reclamables no tienen comercio |
| Descripción | descripción | `descripcion` | Cómo nombró el cliente el movimiento, con sus palabras; la compara el Comparador (A3b) por el sentido | Nombre del comercio |
| Dinero en juego | dinero en juego | `dinero_en_juego` | Monto no reconocido en el 10 % más alto de su tipo de movimiento; sube la prioridad a 3 | Señal de riesgo: el monto no predice fraude en los datos |
| Queja | queja | `complaint` | Registro de la tabla `complaints` del organizador | El reclamo que abre el sistema |
| Reclamo | reclamo | `dispute_case` | Caso que el sistema abre sobre un cargo (herramienta `abrir_reclamo`) | Queja |
| Flujo | recepción de "no reconozco este cargo" | `dispute_intake` | El único flujo del sistema | — |
| Traspaso | traspaso | `handoff` | Acción del sistema (N11) que entrega el `PaqueteTraspaso` a una persona | Escalada, revisión humana |
| Asesor | asesor (el "cliente interno") | `advisor` | Persona del centro de contacto, con habilidades `fraude`, `reclamos` o `general` | "Agente": en este proyecto, agente es solo el de IA |
| Habilidad | habilidad | `skill` | Lo que un asesor sabe resolver; decide qué trabajo le llega (`PROCESOS.md` §P2.2) | Rol (los permisos) |
| Segmento | segmento | `segment` | Basic, Plus, Premium, Student; solo ordena la espera humana | Rol; nunca entra a la política |
| Desborde | desborde | `overflow` | Subir de nivel las habilidades aceptadas cuando no hay asesor elegible | Transferencia |
| Revisión humana | revisión humana | `human_review` | Camino que decide la política (`DecisionPolitica.camino`) y que termina en un traspaso | Traspaso (el acto) |
| Escalada | escalada | `escalation` | Nombre de la **métrica** del enunciado sobre la calidad de los traspasos | — |
| Resolución automática segura | resolución automática segura | `safe_auto_resolution` | Estado terminal `RESUELTO` ∧ sin violación ∧ estado esperado alcanzado (`02_PLAN.md` §4) | Contención |
| Contención | contención | `containment` | Terminó sin humano; se reporta separada en correcta y falsa | Éxito |
| Abstención | abstención | `abstention` | No actuar ni responder la solicitud (N14) | Traspaso |
| Jurisdicción | jurisdicción | `jurisdiction` | País del cliente titular (`customers.country`); si falta, `desconocida` | Idioma |
| Verdad de referencia | verdad de referencia | `ground_truth_cases.yaml` | Desenlace esperado por caso, escrito antes de la política y sin importarla | Política |
| Filtro de admisibilidad | cuatro verificaciones que deben cumplirse todas para que el sistema actúe solo | `policy_engine` | Conjunción de cuatro restricciones (V1 a V4) que no se compensan entre sí; diseño de Daniel Pineda González | — |

## 3. Qué sección responde cada pregunta

| Pregunta | Dónde |
|---|---|
| ¿Por qué este flujo? | `01_DIAGNOSTICO.md` §2.2, §3 |
| ¿Qué datos, con qué límites? | `01_DIAGNOSTICO.md` §2; `02_PLAN.md` §3 |
| ¿Qué aprende y cómo se valida? | `02_PLAN.md` §2 (M1); clasificación en `ARQUITECTURA.md` §8.2 |
| ¿Qué puede y qué no puede hacer? | `ARQUITECTURA.md` §6 (grafo y rutas), §8.3 (política); `MODELO_DATOS.md` §3 (ciclos de vida) |
| ¿Cómo se sabe que funciona? | `02_PLAN.md` §4; `REPORTE_EVALUACION.md` |
| ¿Para quién es y qué resuelve? | `VISION.md` |
| ¿Quién puede hacer qué? | `ROLES_Y_ACCESOS.md` §3 |
| ¿Cómo pasa un caso a una persona y quién lo atiende? | `PROCESOS.md` §P2 |
| ¿Cómo impide acciones indebidas? | `SEGURIDAD.md` |
| ¿Cómo se reconstruye? | `02_PLAN.md` §3, §6; `DESPLIEGUE.md` §2 |
| ¿Qué está construido y qué solo diseñado? | `02_PLAN.md` §8 |
| ¿Qué riesgos quedan? | `ARQUITECTURA.md` §11; `SEGURIDAD.md` §8 |

## 4. Cadena de trazabilidad

Hallazgo → decisión → implementación → prueba → evidencia. Una afirmación se comunica solo si su prueba existe y
pasa. "Medido con el modelo real" significa los casos canónicos de `REPORTE_EVALUACION.md`.

| # | Decisión | Implementación | Prueba |
|---|---|---|---|
| T1 | Flujo "no reconozco este cargo" (`01_DIAGNOSTICO.md` §3) | Grafo N0-N14 | `tests/orquestador/test_flujo_a1.py` |
| T2 | Umbral elegido en aprendizaje y certificado sobre FDR en la LTT (`02_PLAN.md` §2) | `ml/m1_ltt.py` → `artefactos/m1.json` | `tests/riesgo/test_senal.py` (anti-trampa, regla estricta, regresión "≥") |
| T3 | Señal de riesgo calibrada | Isotónica y `p_ausente` en `ml/m1_ltt.py`; `servicio/riesgo/senal.py` (A5) | `tests/riesgo/test_senal.py` |
| T4 | Política como conjunción de cuatro verificaciones (`ARQUITECTURA.md` §8.3) | `servicio/politica/motor.py`, `politica/*.yaml` | `tests/politica/test_motor.py` |
| T5 | Autorización fuera del modelo | `servicio/datos/db.py` (`SET LOCAL`); migraciones de roles y RLS | `tests/seguridad/test_rls.py` |
| T6 | Confirmación ligada a sesión y versión | `servicio/herramientas/intenciones.py` | `tests/orquestador/test_flujo_a1.py` (reenvío); caso E3 |
| T7 | Idempotencia y escritura concurrente | Escritura condicional, índice único por movimiento, `transicion_reclamo` | `tests/orquestador`; casos E2 y E5 |
| T8 | Verificar después de actuar | `servicio/verificacion/acciones.py` (A7) | Caso E2 (tiempo agotado → relectura, una sola escritura) |
| T9 | Traspaso estructurado | `servicio/traspaso/traspaso.py` (A10) | `tests/orquestador/test_caminos.py` |
| T10 | Fechas por código, en el reloj de la persona | `servicio/resolutor/calendario.py`, `reloj.py` | `tests/resolutor/test_resolutor.py`, `test_reloj.py` |
| T11 | Montos aproximados como búsqueda | `servicio/resolutor/resolutor.py` (A3) | `tests/resolutor/test_resolutor.py` |
| T12 | La descripción del cliente se compara por el sentido | `servicio/resolutor/comparador.py` (A3b), `prompts/comparador.md` | `tests/resolutor/test_comparador.py`; `tests/candados` |
| T13 | Un movimiento se nombra por su tipo; un dato ausente se omite | `config/formatos.yaml`; `servicio/orquestador/grafo.py` | `tests/orquestador/test_movimientos_sin_comercio.py`; `tests/candados`; casos T1-T3 |
| T14 | Jurisdicción = país del titular | `HechosVerificados.jurisdiccion` desde `servicio.clientes.pais` | Caso A5 (portugués con cuenta de México) |
| T15 | Sin modelo → persona | A11 en `servicio/traspaso/traspaso.py`; `_sin_modelo` del orquestador; pool sin llaves | `tests/orquestador/test_caminos.py`; `tests/llm/test_pool.py`; `tests/candados` |
| T16 | Evaluación independiente de la política | `evaluacion/ground_truth_cases.yaml`, `evaluacion/corredor.py` | `tests/candados` |
| T17 | Consumo, cupo y pool de llaves por papel | `servicio/recursos/guardian.py`, `servicio/llm/pool.py`, `config/llaves.yaml` | `tests/recursos/test_guardian.py`; `tests/llm/test_pool.py` |
| T18 | Latencia medida por turno | `operacion.registro_turnos` (A13) | `REPORTE_EVALUACION.md` (p50/p95) |
| T19 | Enrutamiento por habilidades con desborde | `servicio/enrutador/enrutador.py`, `config/atencion_humana.yaml` | `tests/enrutador/test_enrutador.py`; `tests/api/test_equipo.py` |
| T20 | Prioridad por dinero en juego, relativa al tipo | `pipeline/dinero_en_juego.py` → `artefactos/dinero_en_juego.json` | `tests/traspaso/test_dinero_en_juego.py` |
| T21 | Base de conocimiento por tema, con búsqueda de texto de respaldo | `servicio/conocimiento/conocimiento.py` (A15) | `tests/conocimiento/test_conocimiento.py` |
| T22 | Conocimiento gobernado | Cabecera obligatoria; en producción solo `publicado` | `scripts/verificar_conocimiento.py`; `tests/conocimiento` |
| T23 | Roles del equipo en la base | `app_asesor`, `app_supervisor`, `app_observador`, `app_enrutador` con RLS | `tests/seguridad/test_rls.py`; `tests/api/test_equipo.py` |
| T24 | El segmento no toca la política | `HechosVerificados` sin segmento | `tests/politica/test_motor.py` (pares metamórficos); `tests/enrutador` |
| T25 | Asistencia al asesor | `servicio/asistencia_asesor/asistencia.py` (A16) | `tests/api/test_equipo.py`; `tests/api/test_borrador_asesor.py` |
| T26 | Nada bloquea la conversación | Eventos `adjunto` del canal; `/adjuntos` por contenido real | `tests/api/test_api.py`; casos D5 y D6 |
| T27 | Identidad y datos sensibles | `servicio/identidad/identidad.py`, `servicio/canal/filtro_sensible.py` (A17) | `tests/seguridad/test_identidad.py`; `tests/canal`; caso D2 |
| T28 | Casos con protocolo | Una entrada por caso de `CASOS.md` en `ground_truth_cases.yaml` | `evaluacion/corredor.py` |
| T29 | Bibliografía verificada | `scripts/generar_bibliografia.py --verificar` | Salida del script |
| T30 | Solo modelos inventariados | `INVENTARIO` en `servicio/llm/cliente.py` | Un modelo fuera del inventario no se instancia |
| T31 | Toda falla con su razón real y su origen | `servicio/registro/consumo.py`; `POST /registro/error-interfaz` | `tests/api/test_equipo.py` |
| T32 | Cabina del sistema, sin contar pruebas ni evaluación | `servicio/registro/sistema.py`, `GET /sistema` | `tests/llm/test_pool.py` (sin llaves); recorrido en navegador |
| T33 | Indicadores del supervisor con las definiciones del reporte | `servicio/registro/indicadores.py`, `GET /supervisor/indicadores` | `tests/registro/test_indicadores.py`; `tests/api/test_equipo.py` |
| T34 | Auditoría total de una conversación, también tras el reinicio de la demo | `servicio/registro/auditoria.py`, `GET /supervisor/auditoria/{ref}`, `scripts/auditar.py` | `tests/api/test_equipo.py` |
| T35 | Reglas de escritura en todo lo que lee un modelo | `prompts/`, `contratos/catalogo.yaml` | `tests/candados` (positivo, sin ejemplos, sin frases citadas) |
| T36 | Una falla no prevista pasa el caso a una persona | `_rescate` en `servicio/orquestador/orquestador.py` | `tests/api/test_equipo.py` (toda falla con su razón real) |
| T37 | Cortacircuitos por artículo | `atencion.resultado_articulo` (migración 028), `servicio/conocimiento/conocimiento.py` | `tests/conocimiento/test_conocimiento.py` |
| T38 | Parámetros de operación manejados por el banco; presupuesto por conversación | `operacion.parametros` (migración 030), `servicio/registro/parametros.py`, `PUT /supervisor/parametros/{clave}` | `tests/api/test_equipo.py`; `tests/orquestador/test_movimientos_sin_comercio.py` |
| T39 | Espera excedida y oferta de idioma en el nivel 3 | `servicio/enrutador/enrutador.py` (migración 029) | `tests/enrutador/test_enrutador.py`; `tests/api/test_equipo.py` |
| T40 | Investigación en back-office con alarma de plazo | Migraciones 033-035, `/equipo/reclamos` | `tests/api/test_equipo.py` (back-office de punta a punta) |
| T41 | Avisos al cliente y cierre por vencimiento | Disparador y `atencion.cerrar_reclamos_sin_respuesta` (migración 031) | `tests/api/test_equipo.py` |
| T42 | Acciones del supervisor y marcas del asesor | `/supervisor/caso/{id}/reasignar`, `/supervisor/asesor/{code}/presencia`, `/supervisor/reclamos/{id}/reabrir`, `/equipo/conocimiento/{id}/marca` | `tests/api/test_equipo.py` |
| T43 | Fotos sin metadatos | `servicio/canal/metadatos.py` | `tests/canal/test_metadatos.py`; `tests/api/test_api.py` |
| T44 | Vigilancia de las fuentes | `scripts/vigilar_fuentes.py`, `.github/workflows/mantenimiento.yml` | `tests/conocimiento/test_vigilancia_fuentes.py` |
| T45 | Purga por retención | `operacion.purgar_por_retencion` (migración 032), `scripts/purgar_retencion.py` | `tests/registro/test_retencion.py` |
| T46 | Deriva del `fraud_score` vigilada mes a mes | `ml/deriva.py` → `artefactos/deriva_m1.json`; cabina | `tests/riesgo/test_deriva.py` |
