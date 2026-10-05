# CONTRATOS — cada componente: qué recibe, qué entrega, qué nunca pasa

**Diseño de arquitectura:** Daniel Pineda González  
**Qué responde:** qué recibe, qué entrega y qué garantiza cada componente, con su módulo y su prueba. Los componentes
están en `ARQUITECTURA.md` §5.1 y el vocabulario en `00_MAPA_SISTEMA.md` §2. Los esquemas viven una sola vez, en
`contratos/` (Pydantic).

## Dónde vive cada contrato

| Componente | Módulo | Prueba |
|---|---|---|
| Esquemas y catálogo único | `contratos/modelos.py`, `contratos/catalogo.yaml` | todas |
| A1 Intérprete | `servicio/interprete/` (`prompts/interprete.md`) | `tests/interprete/` |
| A2 Orquestador | `servicio/orquestador/orquestador.py`, `grafo.py` | `tests/orquestador/` |
| A3 Resolutor | `servicio/resolutor/` | `tests/resolutor/` |
| A3b Comparador | `servicio/resolutor/comparador.py`, `prompts/comparador.md` | `tests/resolutor/test_comparador.py` |
| A4 Política | `servicio/politica/motor.py`, `politica/*.yaml` | `tests/politica/` |
| A5 Señal de riesgo | `servicio/riesgo/senal.py`, `artefactos/m1.json` | `tests/riesgo/` |
| A6 Herramientas | `servicio/herramientas/banco.py`, `intenciones.py` | `tests/orquestador/`, `tests/seguridad/` |
| A7 Verificador de acciones | `servicio/verificacion/acciones.py` | `tests/orquestador/` (casos E2, E5) |
| A8 Redactor | `servicio/redactor/` (`prompts/redactor.md`) | `tests/redactor/` |
| A9 Verificador de redacción | `servicio/verificacion/redaccion.py` | `tests/redactor/` |
| A10 Traspaso y A11 sin modelo | `servicio/traspaso/traspaso.py` | `tests/orquestador/test_caminos.py` |
| A12 Guardián de cupo | `servicio/recursos/guardian.py` | `tests/recursos/` |
| A13 Registro | `operacion.registro_turnos` desde el orquestador | `tests/orquestador/test_flujo_a1.py` |
| A14 Enrutador | `servicio/enrutador/enrutador.py` | `tests/enrutador/`, `tests/api/test_equipo.py` |
| A15 Conocimiento | `servicio/conocimiento/conocimiento.py` | `tests/conocimiento/` |
| A16 Asistencia al asesor | `servicio/asistencia_asesor/asistencia.py` | `tests/api/test_equipo.py` |
| A17 Filtro de datos sensibles | `servicio/canal/filtro_sensible.py` | `tests/canal/`, `tests/seguridad/test_seg.py` |
| E1-E3 Evaluación | `evaluacion/` | `tests/candados/` |

## Estructuras compartidas

### `EstadoConversacion` (lo mantiene A2, en la base; nunca el modelo)

| Campo | Tipo | Nota |
|---|---|---|
| `conversation_id`, `version` | str, int | La versión sirve de bloqueo optimista |
| `nodo` | enum N0-N14 | ARQUITECTURA §6.1 |
| `ultima_pregunta` | {codigo} | La pregunta del catálogo que el último mensaje le hizo al cliente; vacía si ese mensaje no preguntó nada |
| `cargos[]` | {alias, atributos_marcadores, estado, transaction_ref_interno} | `transaction_ref_interno` **nunca** sale hacia un modelo |
| `accion_pendiente` | {codigo, alias, action_intent_id, session_id, expira} ? | |
| `senales_riesgo` | set, acumulativo | Nunca se borra dentro de la conversación |
| `datos_dados` | dict | Lo que el cliente ya dijo, para no preguntarlo otra vez. Al Intérprete solo van los campos que declara el catálogo, con su valor; las banderas internas (claves con guion bajo) se guardan aquí pero no salen hacia el modelo |
| `idioma` | es / pt / otro | Del último mensaje |
| `historial[]` | {turno, rol, texto_con_marcadores} | Completo en la base; al modelo va dentro del presupuesto (ARQUITECTURA §8.1) |
| `pila_temas[]` | {tema, estado_guardado} | Interrupciones y regreso (§8.1, regla 4) |
| `progreso` | contador de turnos sin cambio de estado | Traspaso por estancamiento, nunca por conteo total |
| `no_entendidos` | int | Mensajes seguidos cuya interpretación fue ilegible: el primero se repregunta (`no_se_entendio`), el segundo pasa a una persona; una interpretación válida lo reinicia (ARQUITECTURA §8.4) |
| `data_as_of` | fecha | Frescura de los datos del servicio |
| `adjuntos[]` | {adjunto_id, tipo, tamaño, adjuntado_a?} | Lo que llegó y no es texto (ARQUITECTURA §8.9); el contenido nunca va a un modelo |
| `sin_modelo` | bool | Activo si el circuito está abierto, A12 da el cupo por agotado o la interpretación o la redacción de esta conversación fallaron tras su reintento. La conversación pasa a una persona (ARQUITECTURA §8.4) |

### `HechosVerificados` (entrada de A4)

Salen de la base y de A5, nunca del modelo. Detalle en ARQUITECTURA §8.3. **Nunca incluyen el segmento del
cliente** (ARQUITECTURA D-17).

## A1 — Intérprete (modelo de lenguaje)

- **Entrada:**
  - transcripción dentro del presupuesto, con marcadores;
  - `EstadoConversacion` sin campos internos, con la pila de temas;
  - mensaje actual;
  - esquema de servicios, comandos y catálogos (ARQUITECTURA §8.2).
- **Salida: `Interpretacion`** (JSON Schema cerrado; campos desconocidos rechazados):
  - `comandos[]`: lista ordenada de comandos de diálogo (ARQUITECTURA §8.2.1), por ejemplo `iniciar(disputas.reportar_cargo)`,
    `corregir(monto, 180)`, `consulta_informativa(horarios)`. Un mensaje con varias cosas produce varios comandos;
  - `tipo_disputa_propuesto` ∈ catálogo (§8.2.3), con la frase del cliente que lo sustenta;
  - `idioma` ∈ {es, pt, otro};
  - `cargos_referidos[]` (1 a 5), cada uno con:
    - `refiere_a` ∈ {alias existente, `nuevo`};
    - `monto` {valor, moneda?, aproximado};
    - `cuando` {absoluta | relativa | dia_semana}: el tipo puede omitirse si el valor está en el vocabulario del calendario (`hoy`, `ayer`, `anteayer`, `hace_N_horas`, `hace_N_dias`, `esta_semana`, `semana_pasada`, `este_mes`, `mes_pasado`, un día de la semana o una fecha); una expresión que el calendario no ubica no pierde el turno: se busca sin fecha y se dice. «Hace N días» deja un margen que crece con N (`FRACCION_INCERTIDUMBRE`, mínimo un día);
    - `descripcion`: cómo nombró el cliente el movimiento, con sus palabras (el comercio, el tipo de operación, el
      destino o el medio). Un solo campo: la compara A3b por el sentido. Un estado guardado con los campos anteriores
      (`comercio_texto`, `canal`) se lee como descripción;
  - `reconoce` ∈ {si, no, no_seguro, ninguna}, como dato del cargo en discusión;
  - `borrador_respuesta`: respuesta breve de la IA. Si el turno no trae hechos nuevos, es la respuesta, verificada
    por A9, y no se llama al Redactor. Si el Redactor falla la verificación, es el primer respaldo.

  **Formato:** marcadores de texto con gramática estricta (un campo por línea; listas, una línea por elemento),
  parseados de forma tolerante a este objeto tipado (ARQUITECTURA D-13).

  Las correcciones, elecciones, confirmaciones y el pedido de una persona se expresan **solo** como comandos
  (`corregir`, `elegir`, `confirmar`/`negar`, `pedir_persona`). Una corrección reemplaza el dato; no reinicia la
  conversación.
  - `senales_riesgo[]` ∈ catálogo cerrado (se **suman** a las acumuladas);
  - `datos_secretos[]`: los tramos literales del mensaje que son una clave, un PIN o un código. El código los ubica y
    borra del turno antes de guardarlo (A17, ARQUITECTURA §8.11); el Intérprete nunca repite su contenido.
- **Invariantes:**
  - nunca contiene IDs reales ni fechas calculadas (solo la expresión);
  - si no está seguro, lo dice (`reconoce = no_seguro` o el comando `aclarar`); no se le pide adivinar.
- **Falla:** salida que no parsea o no pasa el esquema → un reintento con el error → traspaso a una persona con la conversación, y el fallo queda
  registrado como error de diseño. Nunca una aclaración con frase fija.
- **Pruebas de contexto (obligatorias antes de dar A1 por bueno):**
  - referencia hacia atrás a 3+ turnos;
  - corrección de monto y de fecha;
  - dos cargos en un mensaje;
  - consulta lateral y regreso;
  - señal de engaño en el turno 2 con acción pedida en el turno 6;
  - cambio de idioma a mitad;
  - pregunta nueva después de resolver.

  Cada una en ES y PT, con 3+ variantes distintas, en la vista de personajes.

## A2 — Orquestador

- **Entrada:** mensaje + token, o un **evento del canal** (pulsar "no reconozco" sobre un movimiento, enviar el
  formulario de identidad, elegir una opción mostrada). Un evento no pasa por el Intérprete: el código lo valida
  contra lo que se le mostró al cliente.
- **Salida:** respuesta al cliente + `EstadoConversacion` nuevo + `RegistroTurno`.
- **Invariantes:**
  - por turno, una interpretación (A1) y una redacción (A8), cada una con un reintento, y una comparación (A3b)
    cuando el cliente describió el movimiento;
  - toda transición del grafo pasa por su guarda;
  - la versión de la conversación sube en cada turno (bloqueo optimista); un reenvío del mismo mensaje del cliente
    (`mensaje_cliente_id`) no se procesa dos veces.
- **Falla:**
  - sin modelo, o con una interpretación o una redacción inválidas tras su reintento: la conversación pasa a una
    persona y el chat muestra el aviso de espera (ARQUITECTURA §8.4);
  - una excepción inesperada revierte el turno (el estado anterior queda intacto) y queda como incidente con su
    rastro; en una transacción nueva, la conversación pasa a una persona con el motivo `falla_del_sistema` y la
    referencia del incidente. Solo si ese rescate también falla, el cliente recibe un error con la referencia.

## A3 — Resolutor de referencias

- **Entrada:** `cargos_referidos`, los movimientos del sujeto del token y el reloj de la persona (`ARQUITECTURA.md` §8.10).
- **Salida:** por cargo, `0 | 1 | 2-5 | >5` candidatos reales, con alias nuevos.
- **Invariantes:**
  - fechas calculadas solo aquí: el Intérprete escribe las partes de la fecha que dijo el cliente (día; mes y día;
    o fecha completa) o una expresión relativa, y el calendario completa lo que falta con la ocurrencia más reciente
    que no pasa del reloj de la conversación;
  - montos aproximados solo proponen candidatos (±10%), nunca los confirman;
  - con 2+ candidatos, nunca elige: devuelve la lista (o pide un dato más si hay más de 5);
  - la descripción no filtra aquí: filtran la fecha y el monto; la descripción la compara A3b.

## A3b — Comparador de descripciones

- **Entrada:** la `descripcion` del cliente y los candidatos de A3, agrupados en opciones `D1…Dn` por descripción
  real distinta (tipo de movimiento en el idioma del cliente y, si existe, el comercio). Nunca IDs, montos ni fechas.
- **Salida:** `COINCIDEN: alias, …` o `ninguna`.
- **Invariantes:**
  - un alias fuera de la lista es salida inválida: un reintento con el error; si vuelve a fallar, o si no hay
    modelo, no se filtra y el cliente elige entre los candidatos (se registra el paso `comparador` en fallo);
  - `ninguna` con candidatos por monto y fecha → hecho `descripcion_distinta` y el cliente elige entre ellos;
  - la descripción del cliente y las opciones van entre marcas de dato: una instrucción dentro de un nombre de
    comercio no cambia la salida posible (solo alias);
  - el cliente confirma el movimiento antes de cualquier acción.

## A4 — Motor de política

- **Entrada:** `HechosVerificados` de **toda** la conversación.
- **Salida: `DecisionPolitica`** =
  - `camino`: `automatizable` | `revision_humana` | `abstencion`;
  - `acciones_permitidas[]`;
  - `verificaciones[4]`, cada una {cumple, números, razón};
  - `plazo_normativo`, `version_politica`, `hash_politica`.
- **Invariantes:** función pura de los hechos (misma entrada → misma salida, byte a byte); no lee el mensaje; no
  llama al modelo; no recibe el segmento del cliente.
- **Pruebas:** pares metamórficos; una prueba por regla de la política.

## A5 — Señal de riesgo (M1)

- **Entrada:** `fraud_score` o ausente.
- **Salida:** {señal calibrada, supera_umbral_certificado: bool, versión del artefacto}.
- **Invariantes:**
  - umbral leído del artefacto versionado, nunca escrito en el código;
  - la señal nunca llega a A1 ni a A8, ni al cliente.

## A6 — Servicio bancario

- Herramientas, errores tipados, escritura condicional, `action_intent_id` e índice único de reclamo: ver
  **Herramientas** abajo. Anti-enumeración: servicio de identidad (`ARQUITECTURA.md` §6.2).
- **Invariantes:** sujeto del token; `SET LOCAL` por transacción; rol sin BYPASSRLS; FORCE RLS.

## A7 — Verificador de acciones

- **Entrada:** `action_intent_id`.
- **Salida:** `completada` | `fallida` | `desconocida`.
- **Invariante:** nunca escribe; solo relee.

## A8 — Redactor (modelo de lenguaje)

- **Se llama en todo turno**, salvo un saludo o un agradecimiento sin pedido fuera del primer mensaje: ahí la respuesta
  es el `borrador_respuesta` de A1, verificado por A9.
- **Entrada:**
  - transcripción dentro del presupuesto;
  - `EstadoConversacion` sin campos internos;
  - idioma y, en el primer turno, el momento del día del cliente para el saludo. La divulgación de que es un asistente
    virtual y de que puede pedir una persona la agrega el código como texto legal `LITERAL` (`GOBERNANZA_DATOS_IA.md` §7);
  - **estado comunicable**: la lista de lo que este turno puede decir, por clase:
    - `AFIRMAR` (hecho verificado, en marcadores);
    - `PREGUNTAR` (lo que falta, agrupado en una pregunta; nunca lo que está en `datos_dados`);
    - `OFRECER` (acción que se propone);
    - `EXACTO` (debe aparecer tal cual: número de caso, plazo);
    - `LITERAL` (texto legal que agrega Python);
    - `NO_COMUNICAR` (lo que existe pero no se dice: la señal de riesgo, el camino interno);
    - `RESPONDER` (consulta informativa y su fuente);
    - `RESULTADO` (contenido producido por una acción).

    Y una **preferencia de comunicación** (`simple`, `pasos_cortos`) que el código deriva de la señal
    `vulnerabilidad_declarada`. Es una indicación de forma: no revela la señal ni cambia lo que se dice.

  Los permisos se aplican al armarlo.
- **Salida:** `{texto, acciones_afirmadas[], idioma, resumen_para_humano?, cita_articulo?, suficiencia?}`. El resumen
  solo va cuando el nodo es N11; la cita y la suficiencia (completa, parcial, insuficiente, ambigua), cuando hubo
  `RESPONDER`.
- **Invariantes:**
  - no recibe la señal de riesgo ni el camino interno;
  - no hay frases fijas: redacta libremente dentro de los hechos.

## A9 — Verificador de redacción

- **Comprueba:**
  - marcadores obligatorios presentes y ningún dígito fuera de ellos;
  - `acciones_afirmadas` ⊆ acciones `completadas`;
  - idioma declarado = idioma detectado = idioma del cliente;
  - si hubo `RESPONDER`: la cita es exactamente el id y la versión entregados; con suficiencia insuficiente o ambigua,
    el texto no responde la pregunta.
- **Falla:** una re-redacción con el error; si el turno no trae hechos que decir, el `borrador_respuesta` de A1 si pasa
  esta misma verificación; si no, traspaso a una persona y el fallo queda registrado como error de diseño. Nunca una frase fija para tapar el
  fallo (ARQUITECTURA §8.4).

## A10 — Traspaso

- **Salida:** `PaqueteTraspaso` (abajo), entregado a A14 con la habilidad requerida (`PROCESOS.md` §P2.2), el idioma
  y la prioridad (§P2.3).

## A14 — Enrutador de atención humana

El proceso completo, con sus reglas y parámetros, está en `PROCESOS.md` §P2. Aquí, solo el contrato.

- **Entrada:**
  - trabajos: conversaciones en vivo (`traspasos`) y reclamos por investigar, cada uno con habilidad, idioma,
    prioridad, hora de llegada y el segmento del cliente (solo para ordenar);
  - asesores: habilidad, idiomas, canal, turno, presencia, capacidad y carga;
  - `config/atencion_humana.yaml` (hitos, niveles de desborde, horas de turno, tiempo de aceptación) y su versión.
- **Salida:** asignaciones, eventos del trabajo (asignado, aceptación vencida, desborde, transferido, fin de turno),
  alarmas para el supervisor y avisos al cliente con la posición y el tiempo estimado (§P2.6).
- **Invariantes:**
  - un asesor solo recibe trabajo si es elegible (§P2.4): nunca por encima de su capacidad ni fuera de su turno;
    la asignación es una escritura condicional;
  - un solo traspaso activo por conversación;
  - el orden de la cola es prioridad → alarma → segmento → llegada; un hito vencido sube la prioridad de 4 a 3 y no
    más; una transferencia conserva la hora de llegada;
  - no hay transferencia sin paquete y nota;
  - nunca se le cambia el idioma al cliente: en el nivel 3 se le ofrece seguir en español y decide él;
  - la primera espera estimada se guarda; si la real la supera en 50 %, el aviso lo dice y el supervisor recibe el
    evento, una vez por caso;
  - no se promete un tiempo que la cola no respalde; con capacidad elegible 0 no se da tiempo, se da la hora del
    siguiente turno;
  - un hito en alarma o vencido siempre genera un evento visible para el supervisor y, si vence, un aviso al cliente;
  - la conversación no se cierra mientras el caso esté con una persona;
  - sin modelo, alarma roja al supervisor; cuando el modelo vuelve, las conversaciones que ya tiene una persona se
    quedan con ella;
  - mismo estado de la cola y de los asesores → misma asignación (función determinista, con los desempates de §P2.4).
- **Pruebas:** una por regla de elegibilidad, orden y desborde; el caso "fraude en portugués por la tarde" llega al
  nivel correcto; ningún caso Premium adelanta a uno en alarma.

## A15 — Servicio de conocimiento

- **Entrada:** tema (del catálogo), audiencia (del rol del token) y país del cliente, si hay sesión.
- **Salida:** {cuerpo del artículo, id, versión, `datos` resueltos} o `SIN_ARTICULO`.
- **Invariantes:**
  - solo entrega artículos `publicado`, dentro de su vigencia y, si son de criticidad alta, con la revisión al día y
    sin una fuente cambiada pendiente de revisión (`GOBERNANZA_DATOS_IA.md` §11);
  - cada respuesta con un artículo informa si pasó la verificación al primer intento (cortacircuitos, §11.8);
  - un rol de cliente o visitante nunca recibe un artículo interno, y la respuesta es la misma `SIN_ARTICULO` que si no
    existiera (no se revela lo que no se puede ver);
  - sin tema del catálogo, busca por texto completo en los artículos públicos vigentes; sin resultado suficiente,
    `SIN_ARTICULO`: el Redactor no responde de memoria;
  - los `datos` se resuelven desde la política o la configuración al servir; el artículo nunca aporta un número propio;
  - cada consulta deja un evento (artículo, versión, suficiencia).

## A16 — Asistencia al asesor

- **Entrada:** el caso asignado (paquete, conversación, `DecisionPolitica`, motivo del traspaso) y el rol y la
  habilidad del asesor.
- **Salida:** {guía del caso (pasos, desde la política y el artículo interno), artículos sugeridos, borrador?}. El
  borrador solo se genera a pedido del asesor.
- **Invariantes:**
  - el borrador se genera con el mismo estado comunicable que A8 usaría para el cliente: sin señal de riesgo ni
    camino interno;
  - el borrador pasa por A9 antes de mostrarse;
  - el texto del cliente llega al asesor marcado como cita;
  - A16 nunca envía nada: el envío es una acción del asesor, que queda con su origen (`MODELO_DATOS.md`,
    `mensajes_asesor`);
  - la guía del caso la calcula el código; el modelo no la escribe.
- **Falla:** modelo caído o cupo agotado → guía y artículos sin borrador.

## A11 — Enrutamiento sin modelo

- **Entrada:** `EstadoConversacion` (nodo, cargo en curso, servicio e intención apilados, `senales_riesgo`).
- **Salida:** {habilidad requerida, prioridad} para A10 y A14.
- **Invariantes:**
  - solo corre con `sin_modelo`; no lee el texto del cliente ni lo interpreta;
  - la habilidad y la prioridad salen del estado con las mismas reglas de `PROCESOS.md` §P2.2 y §P2.3; sin datos
    en el estado, habilidad `general` y prioridad 4;
  - nunca ejecuta acciones ni escribe al cliente: lo que el cliente ve es el aviso de espera de la interfaz, con
    datos de A14;
  - el paquete va marcado `sin_resumen_ia`, con lo verificado hasta ese turno, la acción pendiente tal como estaba
    (propuesta, sin ejecutar) y el enlace a la conversación.

## A12 — Guardián de cupo

- **Invariantes:**
  - antes de cada llamada a un modelo, en el servidor, se compara lo que queda del cupo (peticiones y tokens por
    minuto, leídos de las cabeceras de límite del proveedor en la respuesta anterior) con lo que pide la llamada; si
    no alcanza, se usa otra llave del pool; si ninguna tiene cupo, no se llama y la conversación sigue sin modelo;
  - las llaves se reparten por papel (`config/llaves.yaml`) en un pool con enfriamiento por error 429; el estado de
    enfriamiento sobrevive a un reinicio; sin ninguna llave en el entorno, cada llamada falla con esa razón;
  - presupuesto por conversación: los tokens de cada turno se suman en el estado; al llegar al tope que decide el banco
    (`PROCESOS.md` §P9; 0 = sin tope) no se llama más al modelo y la conversación sigue con una persona;
  - las llamadas se espacian para no llegar al error 429; ninguna prueba ni corrida dispara llamadas en ráfaga;
  - el mensaje del cliente no se recorta: va delimitado como dato no confiable y su tamaño queda en `consumo_modelos`;
  - límites por IP, sesión y conversación.

## A17 — Filtro de datos sensibles

- **Entrada:** el mensaje del cliente, tal como llegó; y, después de A1, los tramos de `datos_secretos[]`.
- **Salida:** el mensaje con los números de tarjeta reemplazados por `[tarjeta borrada]` y la marca
  `dato_sensible_borrado` si hubo alguno.
- **Invariantes:**
  - corre **antes** de guardar el turno y antes de cualquier llamada a un modelo; nada lo salta;
  - detecta por forma (13 a 19 dígitos con dígito de control válido), nunca por lo que el cliente quiere decir;
  - el original no se guarda en ninguna parte;
  - orden de un turno: A17 (números de tarjeta) → A1 → borrado de los tramos de `datos_secretos[]` → se guarda el
    turno. Nada se persiste antes del segundo paso.
- **Pruebas:** número con espacios, con guiones y pegado a texto; un monto largo que no pasa el dígito de control no
  se borra.

## A13 — Registro

- **Salida:** `RegistroTurno` (abajo).
- **Invariantes:** PII redactada antes de persistir; retención según `MODELO_DATOS.md` §5.

## E1-E3 — Evaluación (solo fuera de producción)

- **E1 Simulador:** modelo de otra familia; recibe un personaje y una meta; nunca ve la verdad de referencia.
- **E2 Evaluador:** compara el estado final y el registro con `ground_truth_cases.yaml`, que no importa la política.
- **E3 Juez auxiliar:** tono y claridad; no entra a ninguna métrica principal.

## Esquemas detallados

El esquema de `Interpretacion` está en A1 (arriba), y es la única definición.

1. **Herramientas** (servicio bancario simulado, cada una con el token):
   - lectura: `listar_transacciones(desde, hasta)`, `obtener_transaccion(ref)`, `listar_reclamos`,
     `listar_productos`, `estado_producto(ref)`, `reclamos_previos(dias)`;
   - reclamo (ciclo de vida completo, `MODELO_DATOS.md` §3.1): `abrir_reclamo(ref_visible, tipo, action_intent_id)`,
     `agregar_informacion_reclamo(ref, texto?, adjunto_id?, action_intent_id)`, `retirar_reclamo(ref, motivo, action_intent_id)`;
   - producto (§3.2): `bloquear_producto(ref, origen, action_intent_id)`,
     `desbloquear_producto(ref, action_intent_id)`, este último solo si el bloqueo lo pidió el cliente y no hay
     señal de riesgo; si no, `NO_PERMITIDO` → traspaso;
   - resolver, cerrar, reabrir y corregir el tipo de disputa **no son herramientas del sistema**: son acciones del
     asesor en la app de operación (`ROLES_Y_ACCESOS.md` §3).

   Cada escritura agrega su evento en la misma transacción. No existe ninguna herramienta que borre.

   Errores tipados: `NO_AUTORIZADO`, `NO_ENCONTRADO`, `NO_PERMITIDO` (transición fuera del ciclo de vida), `YA_EXISTE`
   y `TEMPORAL` (conflicto de versión).
   - `NO_AUTORIZADO` y `NO_ENCONTRADO` hacia el cliente se ven idénticos, en contenido y en tiempo objetivo.
   - `NO_ENCONTRADO_EN_DATOS` (con `data_as_of`) es distinto de "no ocurrió": un cargo posterior a `data_as_of` no se
     concluye inexistente.
   - **Escritura condicional dentro de una transacción contra TOCTOU:**
     `UPDATE … WHERE id = ? AND version = ? AND estado = ?`. Autorización y estado se revalidan ahí mismo; con
     `rowcount = 0`, no se ejecuta.
   - **`action_intent_id`** aleatorio, generado en el servidor al proponer la acción, ligado a la versión de la
     conversación, el sujeto autenticado, la sesión, el recurso y la acción exacta (`hash_propuesta`), con vencimiento.
     Se consume una sola vez.
   - Índice único `(customer_id, transaction_id)` en reclamos activos: un reclamo por cargo. El tipo se corrige
     dentro del mismo reclamo (lo hace el asesor), nunca abre otro.
2. **Referencias visibles:** el modelo solo ve alias efímeros por conversación (`C1`, `C2`) y nunca IDs reales; el
   código traduce alias → ID dentro de la sesión.
3. **`DecisionPolitica`:** definida en A4 (arriba).
4. **`PaqueteTraspaso`:**
   - `motivo_traspaso[]` (catálogo; de ahí sale la habilidad requerida, `PROCESOS.md` §P2.2);
   - `solicitud` (1 línea redactada, verificada) o, sin modelo, `sin_resumen_ia = true` con el servicio y la
     intención que ya estaban en el estado;
   - `adjuntos[]` (ids; el asesor los abre en la app);
   - `hechos_verificados[]` (campo, valor, fuente);
   - `acciones_realizadas[]` (acción, resultado verificado);
   - `evidencia` (transacción, señal de riesgo, restricciones evaluadas): **solo para el asesor**, nunca
     para el cliente;
   - `preguntas_abiertas[]`;
   - `idioma`, `prioridad`, `habilidad_requerida`, `plazo_normativo`;
   - `notas[]`: una por cada transferencia (autor, habilidad destino, texto).

   Sin transcripción cruda (se enlaza).
5. **`RegistroTurno`** (auditoría): turn_id, versiones (modelo, prompt, política, calibración), estado anterior y
   nuevo, interpretación, decisión, llamadas a herramientas con latencia y resultado, costo en tokens, verificación.
