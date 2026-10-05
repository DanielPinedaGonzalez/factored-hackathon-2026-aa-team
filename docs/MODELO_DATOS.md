# MODELO DE DATOS — tablas, ciclos de vida y reglas de acceso

**Diseño de arquitectura:** Daniel Pineda González  
**Qué responde:** qué tablas hay, qué ciclo de vida tiene cada entidad, con qué rol de base se accede y cuánto
se conserva. Motor: PostgreSQL ≥ 16.15. Referencias:
- el objeto **Caso** de los CRM de servicio (Salesforce Service Cloud: `Case`, `CaseHistory`, `CaseComment`,
  hitos de SLA) (Salesforce, s. f.-a; Salesforce Ben, s. f.);
- las categorías de disputa de las redes de tarjetas (Chargeback.io, s. f.; Stripe, s. f.);
- la auditoría de solo-agregar (*append-only*) de los sistemas financieros.

**Reglas estructurales:**
- **Nada que registre un hecho se borra.** Retirar, cancelar o cerrar son cambios de estado con motivo, autor y
  fecha, y cada cambio queda como evento. Se garantiza en la base: el rol de ejecución no tiene permiso `DELETE`
  sobre estas tablas.
- **Cada entidad con ciclo de vida tiene su tabla de eventos** de solo agregar. El estado actual es el último evento
  válido, y la transición la valida una función en la base: una transición que no está en el ciclo de vida se
  rechaza en la base, no solo en el código.
- **Toda fila de cliente lleva `customer_id`** y política RLS. El equipo humano accede por rol (§4).

## 1. Esquemas

| Esquema | Contenido | Quién escribe |
|---|---|---|
| `servicio` | Datos del banco para atender, **solo lectura** para la aplicación | El pipeline (rol de migración) |
| `atencion` | Identidad, conversaciones, casos, acciones, traspasos | La aplicación (rol de ejecución) |
| `operacion` | Registro de turnos, costos, accesos a PII, artefactos versionados | La aplicación |
| `evaluacion` | Corridas y resultados de la evaluación | Solo el corredor de evaluación, nunca en el despliegue público |

## 2. Tablas

### 2.1 `servicio` (subconjunto de demo declarado, con manifest)

| Tabla | Clave | Columnas principales | Nota |
|---|---|---|---|
| `clientes` | `customer_id` | país, segmento, estado, `detected_accent` | Sin documento, teléfono ni correo en el despliegue público: no hacen falta para atender |
| `productos` | `product_id` | `customer_id`, tipo, estado, moneda | |
| `transacciones` | `transaction_id` | `customer_id`, `product_id`, fecha, monto, moneda, `amount_usd` (derivado), comercio, ciudad, canal, estado, código, `fraud_score`, marcas de coherencia (`canal_tipo_coherente`, `moneda_pais_coherente`) | Índice (`customer_id`, fecha) |
| `tasas_cambio` | (fecha, moneda) | tasa | Para derivar USD |
| `datos_version` | — | `data_as_of`, hash del manifest | Frescura y trazabilidad |

### 2.2 `atencion`

| Tabla | Qué guarda | Claves e índices |
|---|---|---|
| `identidades_demo` | Clientes habilitados para la demo, cada uno con un **documento de demo creado por el equipo** (el `document_number` del organizador es restringido y no se despliega, `GOBERNANZA_DATOS_IA.md` §2) y su buzón de OTP de sandbox | `customer_id`; documento de demo único |
| `desafios_otp` | Desafío, intentos, vencimiento | Límite de intentos por documento e IP |
| `sesiones` | Token emitido, sujeto, vencimiento, estado | Una sesión, un sujeto |
| `conversaciones` | Cliente (si hay sesión), canal, idioma, estado, `version` | |
| `turnos` | Mensaje del cliente y respuesta, **con marcadores**, interpretación, decisión | (`conversation_id`, n) |
| `estado_conversacion` | `EstadoConversacion` vigente (CONTRATOS), incluidos los cargos en discusión con su alias | Una fila por conversación, bloqueo optimista |
| `buzon_sandbox` | El "celular" y el "correo" de la demo: el código de un solo uso llega a todos los canales registrados | `customer_id` |
| `reclamos` | El **caso**: transacción, tipo de disputa, estado, prioridad, plazo normativo, grupo (varios cargos de un mismo contacto); para la investigación (`PROCESOS.md` §P3): habilidad requerida, asesor asignado, `investigacion_vence` | **Único** (`customer_id`, `transaction_id`) mientras esté activo: un reclamo por cargo; cola: (habilidad, prioridad, creado) |
| `reclamo_eventos` | Cada cambio de estado, con autor (cliente, sistema, asesor), motivo y fecha | Solo agregar |
| `reclamo_notas` | Información adicional del cliente o del asesor (equivale a `CaseComment`) | Solo agregar |
| `adjuntos` | Archivos del cliente (JPG, PNG, PDF ≤ 5 MB, hasta 3 por conversación): tipo real, tamaño, hash, contenido (el audio no se guarda), conversación y reclamo al que se adjuntó. **Nivel restringido**: nunca a un modelo | Solo agregar; RLS por `customer_id` |
| `intenciones_accion` | `action_intent_id`: acción propuesta, recurso, parámetros, sesión, versión de la conversación, `hash_propuesta`, vencimiento, estado y resultado releído | Se consume una sola vez |
| `bloqueos` | Bloqueo temporal de un producto: origen (pedido del cliente o recomendado por riesgo), estado | Uno activo por producto |
| `bloqueo_eventos` | Cambios de estado | Solo agregar |
| `asesores` | Subconjunto de `service_agents` (activos, canal digital o híbrido): código de empleado, habilidad (`fraude`, `reclamos`, `general`), idiomas, canal, turno, país, rol (asesor o supervisor). **Sin nombre, correo ni teléfono** | `employee_code` |
| `asesor_carga` | Carga actual por asesor; la asignación la incrementa con escritura condicional | `employee_code` |
| `avisos_cliente` | Novedades de sus reclamos que el cliente no leyó: un disparador de la base las crea con cada cambio de estado que no hizo el propio cliente; se redactan al mostrarlas y quedan leídas al consultar sus reclamos | `customer_id` |
| `asesor_presencia_eventos` | Cambios de presencia (`desconectado`, `disponible`, `en_pausa`, `ausente`), canal y capacidad elegida. `ocupado` y `fuera_de_turno` se calculan | Solo agregar |
| `traspasos` | `PaqueteTraspaso`, habilidad requerida, idioma, prioridad, nivel de desborde, asesor asignado, estado, **hitos**: `primera_respuesta_vence`, `seguimiento_vence`, y la versión de `config/atencion_humana.yaml` que los calculó; la primera espera estimada (`espera_estimada_min`) | Cola: índice (habilidad, idioma, prioridad, creado) |
| `mensajes_asesor` | Respuestas del asesor al cliente dentro de la misma conversación (atención asíncrona), con su origen: `escrito`, `sugerido_sin_editar` o `sugerido_editado`, y la versión del prompt si hubo sugerencia | Solo agregar |
| `traspaso_eventos` | Asignado, aceptación vencida, tomado, desborde, transferido (con nota), fin de turno, resuelto, devuelto, reasignado | Solo agregar |
| `conocimiento_articulos` | Artículos de la base de conocimiento (`ARQUITECTURA.md` §8.8): id, versión, estado, audiencia, países, criticidad, vigencia, `revisar_antes_de`, autor, aprobado por (en la cabecera), cuerpo ES/PT, fallas seguidas (cortacircuitos, `GOBERNANZA_DATOS_IA.md` §11.8) e índice de texto completo. Se cargan desde `conocimiento/` al desplegar | (id, versión); una sola versión `publicado` por id |
| `conocimiento_eventos` | Cambios de estado del artículo y cada consulta, con versión y suficiencia (`GOBERNANZA_DATOS_IA.md` §11) | Solo agregar |
| `conocimiento_marcas` | Marcas del asesor sobre un artículo: incorrecto, incompleto o falta, con el caso de ejemplo (`PROCESOS.md` §P7) | Solo agregar |

### 2.3 `operacion`

| Tabla | Qué guarda |
|---|---|
| `registro_turnos` | Logs JSON por turno: versiones de modelo, prompt, política y artefactos; latencia; costo |
| `accesos_pii` | Quién del equipo vio datos sin enmascarar, cuándo y de qué caso |
| `eventos_seguridad` | Código fallido, límite alcanzado, token inválido, rol negado (sin PII) |
| `consumo_modelos` | Cada llamada: proveedor, modelo, propósito, tokens, peticiones, cupo restante informado por el proveedor, tamaño del mensaje, resultado. Alimenta el guardián de cupo y las métricas |
| `archivo_reinicio` | Lo que el reinicio de la demo archiva antes de borrar las filas de las identidades de demo; la auditoría lo sigue mostrando |
| `incidentes` | Toda falla no prevista, con dónde, qué, rastro, severidad y referencia |
| `parametros`, `parametro_eventos` | Parámetros de operación vigentes y cada cambio (quién, cuándo, de qué valor a cuál y por qué); los cambia un supervisor por una función de la base (`PROCESOS.md` §P9) |
| `purga_eventos` | Cada corrida de la purga por retención, con los plazos aplicados y los conteos, nunca el contenido |

## 3. Ciclos de vida completos

Quién puede hacer cada transición: **C** = cliente por la conversación (con sesión y confirmación), **S** = el
sistema por su cuenta (solo lo que permite la política), **H** = asesor o supervisor en la app de operación, según `ROLES_Y_ACCESOS.md` §3.

### 3.1 Reclamo (el caso)

```
            abrir (C, con confirmación)
                    │
                    ▼
   ┌──────────── abierto ─────────────┐
   │   agregar información (C, H)     │  retirar (C, con confirmación; motivo obligatorio)
   │   ⟲ sin cambiar de estado        │─────────────────────────► retirado
   ▼                                  │
en_revision (S al traspasar / H al tomarlo)
   │           │
   │           └─ esperando_cliente (H pide información) ─ el cliente responde (C) ─► en_revision
   ▼
resuelto_a_favor | resuelto_en_contra | no_procede   (solo H)
   ▼
cerrado (H, o S al vencer el plazo sin respuesta del cliente)
   │
   └─ reabrir (solo H, con motivo) ─► en_revision
```

- **Crear:** solo sobre una transacción real del cliente, confirmada por él. Un reclamo por transacción;
  varios cargos en un contacto = varios reclamos con el mismo `grupo`.
- **Consultar:** el cliente consulta los suyos (estado, fecha, plazo). La respuesta sale del último evento, releído.
- **Editar:** el cliente **no edita** los hechos del reclamo (vienen de la base del banco). Lo que hace es **agregar
  información** (una nota), que queda como evento. El tipo de disputa lo corrige solo H.
- **Retirar:** el cliente puede desistir mientras no esté resuelto, con confirmación. Queda `retirado` con motivo.
  Nunca se borra.
- **Resolver y cerrar:** siempre H (el sistema no decide el fondo ni mueve dinero). El sistema solo cierra por
  vencimiento administrativo, con evento.
- **Toda resolución lleva su explicación:** `resuelto_en_contra` y `no_procede` exigen una explicación para el cliente
  y la lista de documentos que la sustentan; sin ellas, la base rechaza la transición. El cliente puede pedir los
  documentos y una revisión, que el supervisor atiende reabriendo con motivo (`CASOS.md` PR-12).

### 3.2 Bloqueo temporal de producto

```
activo ──bloquear (C con confirmación; o S la recomienda y C confirma)──► bloqueado_temporal
bloqueado_temporal ──desbloquear──► activo
bloqueado_temporal ──H confirma compromiso──► escalado_a_reemplazo  (fuera del alcance: tarjeta nueva)
```

- **Desbloquear:** si el bloqueo lo pidió el cliente por su cuenta y no hay señal de riesgo acumulada, lo puede
  deshacer él (autenticado y con confirmación). Si hubo recomendación por riesgo o una señal de riesgo, **solo H**
  (verificación C_III: el camino de corrección sigue abierto, pero con una persona).
- **Consultar:** el estado del producto siempre se relee.

### 3.3 Conversación

```
abierta ──(sin actividad X min)──► inactiva ──(el cliente vuelve)──► abierta
abierta ──(resuelto y el cliente se despide / cierre)──► cerrada
abierta ──(traspaso)──► con_humano ──(H la devuelve)──► abierta | ──(H cierra)──► cerrada
```

Al volver el cliente otro día se abre una conversación **nueva**, que recupera (bajo demanda, de la base) sus
reclamos activos y el estado final de la anterior. Nada se "recuerda" en el modelo.

### 3.4 Traspaso (modelo de centro de contacto, `EXPERIENCIA_CLIENTE.md` §3)

```
en_cola ──(asesor elegible, PROCESOS §P2.4)──► asignado ──(H lo abre en 60 s)──► en_atencion
asignado ──(no lo abre a tiempo)──► en_cola (mismo lugar)
en_atencion ──(H transfiere con nota: otra especialidad o supervisor)──► en_cola (conserva prioridad y contexto)
en_atencion ──(H responde y espera al cliente)──► esperando_cliente ──(el cliente responde)──► en_atencion
en_atencion ──► resuelto (H) | devuelto_al_sistema (H, con nota)
```

- **No existe la transferencia sin contexto:** todo cambio de asesor lleva el paquete más la nota.
- **Asignación, desborde, turnos y tiempo estimado:** `PROCESOS.md` §P2.
- **Hitos:** `primera_respuesta_vence` según la prioridad y `seguimiento_vence`. Una alarma interna avisa antes del
  vencimiento; si vence, el supervisor lo ve en rojo y el cliente recibe un aviso honesto.
- **El cliente** recibe, redactado por el sistema con los hechos del evento: su posición y el tiempo estimado
  (calculado con la cola real), cada cambio relevante y la respuesta del asesor en el mismo chat.

### 3.5 Intención de acción

`propuesta → confirmada → ejecutando → completada | fallida | desconocida → (relectura) completada | fallida`,
o `propuesta → descartada` (vence el TTL o el cliente no confirma). ARQUITECTURA §6.3.

### 3.6 Lo que no hace el cliente por conversación, y por qué

- **Borrar su historia o sus datos:** es un derecho (habeas data), pero su trámite no es parte de este flujo →
  traspaso con la solicitud registrada.
- **Cambiar datos de contacto o identidad:** traspaso.
- **Pedir el abono o reembolso:** se registra como petición en la nota del reclamo; decide H.

## 4. Roles de base (implementan `ROLES_Y_ACCESOS.md`)

| Rol de base | Rol de la persona | Puede |
|---|---|---|
| `app_migraciones` | Pipeline | Escribir `servicio`, crear esquemas, cargar asesores y artículos. Nunca usado por la API |
| `app_api` | — | Solo conectarse. Miembro de los roles de abajo con `GRANT … WITH INHERIT FALSE, SET TRUE` (PostgreSQL 16): no hereda sus privilegios y en cada transacción asume uno con `SET LOCAL ROLE`, según el token (`SEGURIDAD.md` §3) |
| `app_ejecucion` | Visitante, cliente, asistente | Leer `servicio` y escribir `atencion`/`operacion`, **sin DELETE**, con RLS por `customer_id` fijado con `SET LOCAL` |
| `app_asesor` | Asesor | Ver la cola de sus habilidades e idiomas (enmascarada) y, sin enmascarar, solo los casos asignados a él y abiertos (`app.asesor_id` con `SET LOCAL`); cada vista sin enmascarar queda en `accesos_pii`; responder, pedir información, transferir, resolver |
| `app_supervisor` | Supervisor | Ver todas las colas enmascaradas; reasignar; cambiar la presencia de un asesor; reabrir; desenmascarar con motivo, auditado |
| `app_observador` | Observador (auditoría, jurado) | Solo lectura, siempre enmascarada, de colas, casos, decisiones y registros de auditoría |

Todos `NOSUPERUSER NOBYPASSRLS`, con `FORCE ROW LEVEL SECURITY` en cada tabla con `customer_id` y en `traspasos`,
`reclamos` y `mensajes_asesor`.

## 5. Retención

| Dato | Retención en la demo |
|---|---|
| Conversaciones y turnos | 90 días |
| Adjuntos | Lo mismo que el reclamo al que pertenecen; sin reclamo, 90 días |
| Entrada cruda enviada a un modelo | No se guarda |
| Registro de turnos, eventos de casos, accesos a PII | 90 días |
| Consumo de modelos | Mientras dure el proyecto (lo exige el reporte de costo) |

El reinicio de la demo copia tal cual cada fila que borra (reclamos, bloqueos, casos humanos, sus eventos y los
mensajes del asesor) a `operacion.archivo_reinicio`, que solo admite inserciones: la auditoría no se pierde.

Los plazos viven en `config/retencion.yaml` y los aprueba cumplimiento. La purga (`scripts/purgar_retencion.py`,
semanal en GitHub Actions) vacía el contenido vencido sin borrar los hechos de los casos: el texto de las conversaciones
cuyo último turno venció y que no tienen un caso vivo, y el archivo de los adjuntos sin reclamo; borra solo registros
técnicos vencidos (registro de turnos, accesos a datos personales, eventos de seguridad). Nunca toca un reclamo ni sus
eventos. Cada corrida deja su evento en `operacion.purga_eventos`.

## Referencias

Completas, en formato APA 7, en `BIBLIOGRAFIA.md`.
