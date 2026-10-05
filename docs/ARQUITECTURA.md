# ARQUITECTURA — sistema "no reconozco este cargo" (AA TEAM)

**Diseño de arquitectura:** Daniel Pineda González  
**Qué responde:** cómo está construido el sistema y por qué. Sigue arc42, la plantilla estándar de 12 secciones para
documentar arquitecturas (arc42, s. f.); las decisiones van como registros de decisión (ADR, §9). Contratos por
componente: `CONTRATOS.md`. Tablas y ciclos de vida: `MODELO_DATOS.md`. Vocabulario: `00_MAPA_SISTEMA.md` §2.

## 1. Introducción y objetivos

Un sistema de atención bancaria, en español y portugués, para el cliente que no reconoce un movimiento. Lo autentica,
encuentra el movimiento en sus datos reales, se lo muestra, decide el camino con reglas explicables, actúa solo con su
confirmación y verificando el resultado, y pasa a una persona cuando no le corresponde decidir. Requisitos del reto:
`01_DIAGNOSTICO.md` §1 (R1-R14). Objetivos de calidad: §10.

## 2. Restricciones

- Plazo corto, un equipo de una persona y 3 GB de RAM.
- Cero presupuesto: llaves gratuitas; despliegue gratuito (Render: API de 512 MB y sitios estáticos; Neon de 0,5 GB; GitHub Actions).
- Datos sintéticos solo en español, con las limitaciones medidas en el diagnóstico.
- Repositorio público al final; nada privado ni secreto en él.
- No se mueve dinero ni se aprueba crédito (el reto no lo autoriza).

## 3. Contexto y alcance

```
 Cliente (web, ES/PT) ──► [ Sistema AA TEAM ] ◄── Asesor y supervisor (app de operación)
                              │        │
                 Modelo de lenguaje    Base del banco (sintética, solo lectura)
                 (API gratuita)        + base de atención (casos, eventos)
```

Dentro del alcance:
- identificar movimientos;
- abrir, consultar, completar y retirar reclamos;
- bloquear y desbloquear productos de forma temporal;
- traspasar a una persona.

Fuera:
- resolver el fondo del reclamo;
- abonos y reembolsos;
- reemplazo de tarjeta;
- cambios de datos personales;
- otras gestiones bancarias (se reconocen y se traspasan).

## 4. Estrategia de solución

1. **El modelo entiende; el código decide y ejecuta.** Las llamadas al modelo (interpretar, comparar descripciones y
   redactar) producen estructuras que el código valida. Ninguna salida del modelo tiene autoridad por sí misma.
2. **El contexto completo es la condición de todo lo demás.** Si el sistema no entiende la conversación entera, no
   sirve. Por eso el contexto tiene su propio diseño (§8.1) y sus propias pruebas.
3. **Nada se afirma sin estar verificado.**
4. **No actuar es una respuesta válida.**
5. **Nada de código fijo que imite inteligencia:** ni frases fijas al cliente ni listas de palabras sobre lo que el
   cliente escribe (§8.4).

### 4.1 Compromisos explícitos (qué elegimos y qué pagamos)

| Eje | Elegimos | Pagamos | Cómo se mide |
|---|---|---|---|
| Autonomía frente a supervisión humana | Solo acciones reversibles, con confirmación; el fondo del reclamo y el dinero, siempre una persona | Menos resolución automática; más casos a la cola humana | Resolución automática segura sobre elegibles; escaladas innecesarias |
| Exactitud frente a cobertura | Abstenerse, aclarar o traspasar ante la duda | Más turnos y más traspasos | Escaladas faltantes frente a innecesarias; resultados inseguros con denominador |
| Latencia frente a control | Dos llamadas por turno (interpretar y redactar), una tercera cuando el cliente describe el movimiento (comparar), y verificación en código | Más latencia que una sola llamada | p50/p95 local y desplegado |
| Costo frente a calidad | Modelos gratuitos en Groq: `gpt-oss-120b` interpreta (razonamiento medio: con bajo, a veces omitía una señal de riesgo, medido) y redacta (razonamiento bajo). `gpt-oss-20b` se midió como Redactor y quedó descartado: agregaba datos que no estaban en el estado (una moneda inventada) y copiaba la estructura interna al texto | Límite de cupo; menor tamaño de la evaluación | Costo por caso y por resolución; cupo medido |
| Privacidad frente a capacidad | El modelo ve marcadores, nunca datos reales; no lee imágenes (§8.9) | La IA no puede "mirar" un comprobante; lo verá una persona cuando haya un caso | Prueba de campos por prompt; adjuntos revisados por humanos |
| Reproducibilidad frente a aprendizaje | Modelos entrenados una vez, congelados y versionados | El sistema no mejora solo con el uso | Mismas versiones → mismas decisiones; deriva vigilada |
| Disponibilidad frente a honestidad | Sin modelo, el sistema no improvisa ni usa frases de respaldo: pasa a una persona y el chat muestra el estado real de la espera (§8.4) | Más carga humana durante una caída | Frases fijas en la conversación = 0 |

### 4.2 Dónde va IA y dónde va lógica determinista

| Tarea | Quién | Por qué |
|---|---|---|
| Entender lo que el cliente escribe, con toda la conversación | Modelo de lenguaje | Es lenguaje libre; las listas de palabras fallan justo con quien no dice "disputa" |
| Redactar la respuesta y la sugerencia al asesor | Modelo de lenguaje | Tono y claridad en dos idiomas, sin frases fijas |
| Calcular fechas, montos y candidatos | Código | Un cálculo tiene una sola respuesta correcta |
| Decidir si un movimiento real corresponde a cómo lo nombró el cliente | Modelo de lenguaje (A3b), eligiendo solo entre alias | "la transferencia", "lo del súper" o un nombre mal escrito son sentido, no palabras; el código valida y el cliente confirma |
| Decidir el camino (automatizar, persona, abstenerse) | Código (política) | Tiene que ser explicable, igual para casos iguales y auditable |
| Estimar el riesgo de fraude | ML (M1) | Hay etiqueta válida y se puede garantizar el error con estadística |
| Enrutar cuando no hay modelo | Código (A11), con el estado de la conversación | El contexto ya dice qué se estaba haciendo: nodo, cargo en curso y señales acumuladas |
| Autorizar, ejecutar y verificar acciones | Código y base (RLS) | Ninguna salida del modelo tiene autoridad |
| Asignar a un asesor | Código (enrutador) | Reglas de negocio declaradas; misma cola → misma asignación |
| Revisar una imagen o decidir el fondo del reclamo | Persona | Datos sensibles y decisiones con efecto sobre el dinero |

## 5. Vista de bloques (componentes y capas)

### 5.1 Componentes

Cada componente tiene **una** responsabilidad. Ninguno busca a otro por su cuenta: el orquestador les pasa lo que
necesitan.

| # | Componente | Tipo | Responsabilidad única | Nunca hace |
|---|---|---|---|---|
| A1 | **Intérprete** | Modelo de lenguaje | Entender el mensaje **dentro de la conversación completa** y devolver una `Interpretacion` estructurada | Decidir, calcular fechas o montos, ver IDs reales |
| A2 | **Orquestador** | Python | Llevar el estado de la conversación, recorrer el grafo (§6) y llamar a los demás en orden | Interpretar texto |
| A3 | **Resolutor de referencias** | Python | Convertir lo interpretado en candidatos reales por lo que se calcula: fechas relativas y montos aproximados → 0, 1 o 2+ movimientos del cliente | Elegir en silencio entre 2+; comparar descripciones por palabras |
| A3b | **Comparador de descripciones** | Modelo de lenguaje | Decidir por el sentido cuáles de los candidatos de A3 corresponden a cómo el cliente nombró el movimiento (el comercio, el tipo de operación, el destino), eligiendo alias de una lista cerrada de descripciones reales | Ver IDs, montos o fechas; generar texto; elegir fuera de la lista (el código valida cada alias y el cliente confirma el movimiento) |
| A4 | **Motor de política** | Python | Las cuatro verificaciones (§8.3) sobre hechos verificados de toda la conversación | Leer el mensaje del cliente |
| A5 | **Señal de riesgo (M1)** | Artefacto ML | Convertir el `fraud_score` en señal calibrada y aplicar el umbral certificado | Clasificar el caso como fraude |
| A6 | **Servicio bancario** | Python + Postgres | Identidad, lecturas y escrituras con autorización y RLS | Confiar en un ID que no venga del token |
| A7 | **Verificador de acciones** | Python | Releer el estado tras cada escritura; resolver el estado `desconocida` | Reintentar una escritura a ciegas |
| A8 | **Redactor** | Modelo de lenguaje | Escribir la respuesta con hechos verificados, la conversación y el idioma | Decidir, inventar datos, recibir la señal de riesgo |
| A9 | **Verificador de redacción** | Python + identificador de idioma | Comprobar marcadores, cifras, acciones afirmadas e idioma | Juzgar el texto con listas de palabras |
| A10 | **Traspaso** | Python | Armar el `PaqueteTraspaso` y dejarlo en la bandeja | Volcar la transcripción cruda |
| A11 | **Enrutamiento sin modelo** | Python | Elegir habilidad y prioridad del traspaso con lo que el estado ya sabe cuando no hay modelo (§8.4) | Ejecutar acciones; escribir al cliente |
| A12 | **Guardián de cupo y pool de llaves** | Python | Espaciar las llamadas y contar tokens y peticiones contra los límites que informa el proveedor, con un guardián por llave compartido por todos los componentes; repartir las llamadas entre las llaves de cada papel (`config/llaves.yaml`) en un pool LRU con enfriamiento por 429 y estados NOMINAL, DEGRADADO y SATURADO (`servicio/llm/pool.py`); límites por IP/sesión | Delegar el control al modelo; recortar el mensaje del cliente; esperar indefinidamente con todas las llaves saturadas |
| A13 | **Registro** | Python | Registro por turno (versiones, decisiones, pasos con su latencia); cada llamada a un modelo, exitosa o fallida, con su razón real (código y mensaje del proveedor, límite, error de red) y la llave que respondió; cada incidente no previsto con dónde, qué y el rastro (al cliente, un error genérico con su referencia); cada rechazo de la API como evento de seguridad; todo con su origen (operación, pruebas, evaluación) y en su propia transacción, sin tumbar nunca la conversación (`servicio/registro/consumo.py`) | Guardar PII sin redactar; enmascarar la razón de un fallo en el registro; perder lo registrado cuando el turno se revierte |
| A14 | **Enrutador de atención humana** | Python | Repartir conversaciones en vivo y reclamos por investigar por habilidad, idioma, prioridad y capacidad; desborde, hitos y avisos al cliente (`PROCESOS.md` §P2) | Transferir sin contexto; prometer un tiempo que la cola no permite; cambiarle el idioma al cliente |
| A15 | **Servicio de conocimiento** | Python | Entregar el artículo vigente de un tema del catálogo, filtrado por audiencia y país (§8.8) | Buscar por parecido semántico; responder sin artículo |
| A16 | **Asistencia al asesor** | Python + A8 | Armar la guía del caso (código), los artículos sugeridos y, a pedido, un borrador de respuesta redactado por A8 (`PROCESOS.md` §P2.8) | Enviar al cliente; proponer acciones de fondo; mostrar la señal de riesgo en el borrador |
| A17 | **Filtro de datos sensibles** | Python | Borrar números de tarjeta del mensaje del cliente **antes** de guardarlo o enviarlo a cualquier modelo (§8.11) | Interpretar la intención; dejar pasar un número completo |

Solo para evaluación y demo: **E1 Simulador de clientes** (modelo de otra familia, con personajes), **E2
Evaluador** (compara el estado final con la verdad de referencia) y **E3 Juez auxiliar** (tono y claridad; no
decide métricas).

### 5.2 Capas

```
┌─────────────────────────────── Canal ────────────────────────────────┐
│ Web chat del cliente (ES/PT)          App de operación (equipo humano)│
└───────────────┬───────────────────────────────────┬──────────────────┘
                │ HTTPS                             │ HTTPS (rol asesor/supervisor)
┌───────────────▼───────────────────────────────────▼──────────────────┐
│ API (FastAPI)  — autenticación, límites, logs JSON por turno          │
├───────────────────────────────────────────────────────────────────────┤
│ Orquestador de conversación = MÁQUINA DE ESTADOS explícita (§6)       │
│   ├─ Intérprete (LLM, salida JSON con esquema)        ← no confiable  │
│   ├─ Validador de la interpretación (Pydantic + catálogos)            │
│   ├─ Motor de política: 4 verificaciones (Python, YAML por país) ← decide│
│   ├─ Señal de riesgo M1 (score calibrado + umbral certificado)        │
│   ├─ Herramientas bancarias (servicio simulado, contrato + RLS)       │
│   ├─ Verificador de acciones (relee el estado real)                   │
│   ├─ Redactor (LLM) + Verificador de redacción (Python)               │
│   └─ Traspaso a humano (JSON validado)                                │
├───────────────────────────────────────────────────────────────────────┤
│ PostgreSQL ≥ 16.15: datos de servicio (oro), casos, sesiones, auditoría│
│ trazas — con Row-Level Security por cliente y por rol del equipo      │
├───────────────────────────────────────────────────────────────────────┤
│ Pipeline de datos (batch + incremental): CSV → bronce → plata → oro   │
│ DuckDB + Parquet, contratos en SQL, linaje, reporte de calidad        │
└───────────────────────────────────────────────────────────────────────┘
```

Por qué así:
- **Máquina de estados y no un "agente libre":** el reto premia saber cuándo no actuar. Un grafo pequeño y explícito
  es auditable, testeable nodo por nodo y reproducible (Yao et al., 2024; Pai & Xian, 2026).
- **Motor de política separado del modelo:** "Enforce permissions and policy outside model-generated prose"
  (enunciado) y separación de control y dato contra la inyección (Debenedetti et al., 2025).
- **Postgres con RLS:** el acceso a cada cliente se aplica en la base, no en el prompt (R12). Si el código tuviera un
  error, la base igual negaría la fila.
- **DuckDB para el pipeline:** 3 GB de RAM (DIAGNÓSTICO §2.7).

### 5.3 Estructura del código

**Una regla:** un componente = un módulo = un contrato (`CONTRATOS.md`) = su carpeta de pruebas espejo. Un módulo
importa solo `contratos/` y lo que el orquestador le pasa; ninguno llama a otro por su cuenta (§5.1). Así cada archivo
tiene una sola responsabilidad y se prueba solo.

```
contratos/
  catalogo.yaml            comandos, servicios, intenciones, acciones, motivos de traspaso, señales, temas (D-14)
  modelos.py               EstadoConversacion, Interpretacion, HechosVerificados, DecisionPolitica,
                           PaqueteTraspaso, RegistroTurno (Pydantic → JSON Schema)
servicio/
  api/                     rutas FastAPI, verificación del token y del rol, límites
  identidad/               formulario seguro y código de un solo uso del sandbox (N1, §8.11)
  canal/filtro_sensible.py A17
  llm/                     clientes de modelos (proveedor real, puente de archivos, falso), un modelo por rol
  datos/                   conexión con SET LOCAL ROLE y sujeto del token (INV-RLS)
  orquestador/             A2: grafo, guardas, estado, pila de temas
  interprete/              A1: prompt generado desde el catálogo + lector de marcadores
  resolutor/               A3: fechas, montos, candidatos; A3b: comparador de descripciones
  politica/motor.py        A4, función pura
  riesgo/                  A5: lee los artefactos de M1
  herramientas/            A6: una función por herramienta, escritura condicional
  verificacion/            A7 (acciones) y A9 (redacción)
  redactor/                A8 y el estado comunicable
  traspaso/                A10 y A11 (enrutamiento por el estado cuando no hay modelo)
  recursos/                A12: guardián de cupo (tokens, peticiones, espaciado) y presupuestos
  registro/                A13
  enrutador/               A14
  conocimiento/            A15: carga y búsqueda de `conocimiento/`
  asistencia_asesor/       A16
prompts/                   interprete.md, comparador.md, redactor.md (simulador.md y linea_base.md, solo evaluación)
politica/                  mx.yaml, co.yaml, ar.yaml
config/                    formatos, atención humana, identidad, llaves, retención, textos legales
conocimiento/              publico/, interno/
migraciones/               SQL numerado: esquemas, roles, RLS, funciones de transición
scripts/                   operación (migrar, humo, verificar, escanear llaves); dev/ (puente, mediciones); diagnostico/ (datos)
pipeline/  ml/             datos (bronce → plata → oro) y M1
evaluacion/                verdad de referencia, E1-E3, corridas, reporte
apps/web/                  un sitio estático con tres rutas (`INTERFACES.md`)
tests/                     espejo de servicio/, pipeline/ y ml/; más las pruebas candado y de seguridad
```

**Candados** (pruebas en `tests/candados/` y `tests/riesgo/`, no convenciones): ningún texto al cliente en un `.py`;
ninguna lista de palabras sobre el mensaje del cliente; ningún catálogo de frases; el número del umbral nunca escrito
a mano; la verdad de referencia no importa la política; ninguna llave en el repositorio; todo lo que lee un modelo, en
positivo y sin ejemplos; ningún dato ausente rellenado con otro; todo tipo de movimiento con nombre en los dos
idiomas.

**Dependencias:** la política, el resolutor y la señal de riesgo son funciones puras: no consultan la base ni llaman a
un modelo; reciben lo que el orquestador les pasa. La API importa el módulo de personajes de `evaluacion/` solo para
la vista en vivo.

## 6. Vista de ejecución: el grafo de la conversación

Estado persistido por conversación en Postgres (`atencion.estado_conversacion`, un JSON validado con el esquema
`EstadoConversacion`). No hay memoria implícita: todo lo que el sistema "sabe" en un turno está en esa fila o se consulta en el momento.

### 6.1 Nodos

| Nodo | Qué hace | Quién decide |
|---|---|---|
| N0 `SIN_SESION` | Pide autenticarse; solo responde información pública (horarios, cómo reportar) | Código |
| N1 `AUTENTICANDO` | **Formulario seguro dentro del chat** (§8.11): documento + código de un solo uso (OTP) enviado a la vez a **todos** sus canales registrados (celular y correo) → token firmado, 15 min. Lo escrito en el formulario va directo al servicio de identidad: nunca al historial ni al modelo | Servicio de identidad |
| N2 `ESCUCHANDO` | Interpreta el mensaje: intención, idioma y lo que dijo del movimiento (monto, fecha y cómo lo describe) | LLM → validado |
| N3 `BUSCANDO_CARGO` | Consulta los movimientos **del cliente autenticado** por fecha y monto → 0, 1 o 2+ candidatos; si el cliente describió el movimiento, el Comparador (A3b) deja los que corresponden | Código (SQL con RLS); A3b elige alias, el código valida |
| N4 `ACLARANDO` | Falta un dato o hay 2+ candidatos: una sola pregunta natural que pide todo lo que falta, o muestra las opciones reales numeradas | Código arma las opciones; LLM redacta |
| N5 `MOSTRANDO_HECHOS` | Muestra el movimiento con sus hechos (tipo, comercio y ciudad si los tiene, fecha, hora, monto, producto, estado) y pregunta si lo reconoce. Si el estado es `Declined`/`Reversed`, dice con el hecho verificado que no hubo cobro; si es `Pending`, que puede no concretarse. En ambos casos quedan disponibles la revisión y el bloqueo a pedido | Código arma; LLM redacta; verificador comprueba |
| N6 `EVALUANDO` | No lo reconoce → motor de política con riesgo calibrado, plazo del país y las cuatro verificaciones → camino | Motor de política |
| N7 `PROPONIENDO` | Propone la acción permitida (abrir reclamo; bloquear el producto) y pide confirmación explícita | Código; LLM redacta |
| N8 `EJECUTANDO` | Ejecuta con clave de idempotencia; reintentos acotados | Herramientas |
| N9 `VERIFICANDO` | Relee el caso o el estado del producto; solo si coincide se afirma | Código |
| N10 `RESUELTO` | Confirma lo verificado (número de caso real, plazo según política) | LLM redacta; verificador |
| N11 `TRASPASO` | Arma el paquete para el humano y le dice al cliente qué pasa y cuándo | Código + LLM redacta |
| N12 `CERRADO_SIN_RECLAMO` | El cliente reconoció el cargo (confusión o compra de alguien de su casa): cierra sin reclamo, y **siempre** ofrece "si aun así quieres reclamar, lo hago" y el bloqueo si el producto está en otras manos. El derecho de reclamar es del cliente (C_III) | Código |
| N13 `FUERA_DE_ALCANCE` | Intención bancaria que el flujo no cubre: dice qué sí puede hacer, u ofrece transferir | Código |
| N14 `ABSTENCION` | Contenido no bancario, manipulación o inyección detectada: no ejecuta nada y responde neutro | Código |

### 6.2 Bordes (transiciones) y guardas

| De → A | Guarda (condición verificable) |
|---|---|
| N0 → N1 | pide algo que requiere datos de cuenta |
| N0/N2 → N5 | el cliente pulsa "no reconozco este cargo" sobre un movimiento propio (evento del canal, no texto): el cargo llega identificado por el código y no pasa por el Intérprete. Sin sesión, primero N1 (D-22) |
| N1 → N2 | token válido (firma, vigencia, `customer_id` del token) |
| N0/N1 → N11 | sin sesión y sin poder identificarse (comando `no_puede_identificarse` o tres códigos fallidos): traspaso marcado "identidad no verificada", a `fraude` con prioridad 1 si hay una señal de seguridad; no se bloquea ni se muestra nada (`CASOS.md` C3, D8). Con una señal de seguridad y sin sesión todavía, primero se pide la identidad para poder proteger el producto y se recuerda que hay una persona; verificada, se ofrece el bloqueo y luego se traspasa (N2 → N11). El Intérprete corre en N0 y N1 igual que en N2 |
| N1 → N11 | 3 intentos de OTP fallidos → traspaso de seguridad. Anti-enumeración: respuesta idéntica y tiempo similar exista o no el documento, límite por IP y por documento, evento de seguridad en la auditoría |
| cualquiera → N1 | token vencido o inválido en cualquier turno (sesión vencida, R8) |
| N2 → N3 | comando `iniciar(disputas.reportar_cargo)` o `iniciar(movimientos.consultar)` (§8.2.1, §8.2.2) |
| N2 → N4 | intención válida pero sin ningún dato del cargo |
| N2 → N13 | comando `fuera_de_alcance` |
| N2 → N14 | comando `no_puedo` (no bancaria) o señal `manipulacion` |
| N2 → N11 | pide persona, o `senales_riesgo` ∩ {`engano_por_tercero`, `coaccion`, `vulnerabilidad_declarada`, `credencial_comprometida`, `producto_en_manos_de_otro`} ≠ ∅: traspaso sin más preguntas, con lo ya verificado. **Si hay engaño, coacción, credencial comprometida o el producto está en manos de otro, y hay un producto que proteger, primero se ofrece el bloqueo** (N7 → N8 → N9, con confirmación) y, confirmado o rechazado, se traspasa a `fraude` con prioridad 1 y el resultado del bloqueo en el paquete: proteger va antes que esperar (`CASOS.md` PR-4). Sin sesión: no se bloquea nada y el traspaso va marcado "identidad no verificada" |
| N2 → N3 | con `cargos_referidos[]` de 1 a 5: cola de cargos; cada uno recorre N3-N9 con su propio reclamo e idempotencia. Más de 5 → los identificados + traspaso |
| N3 → N5 | exactamente 1 candidato: **siempre se muestra y el cliente dice si lo reconoce**, aunque ya haya dicho "no lo reconozco" (nada se propone sobre un cargo que no ha visto; antes un atajo saltaba este paso) |
| N3 → N4 | 0 candidatos (se piden los datos que faltan), 2-5 (se listan con alias, más recientes primero), más de 5 (se dice cuántos hay y se pide el monto o la fecha; nunca se elige en silencio), o hay candidatos por monto y fecha pero ninguno con la descripción del cliente (se le muestran para que elija el suyo) |
| N4 → N3 | el cliente aportó datos nuevos o eligió una opción mostrada (por número o texto exacto, validado contra la lista) |
| N4 → N11 | se alcanza el `max_sin_progreso` del nodo (§8.1, regla 1: 5 donde se elige entre opciones o se da una fecha o un monto) sin que cambie nada en el estado (falta de progreso, no conteo): se ofrece una persona en vez de interrogar más |
| N5 → N12 | `reconoce = si`, sin `engano_por_tercero` ni `coaccion` |
| N5 → N11 | `reconoce = si` **con** `engano_por_tercero` o `coaccion` (estafa autorizada: nunca "usted lo autorizó, no procede"). Primero se ofrece el bloqueo, igual que en N2 → N11 |
| N5 → N5 | `reconoce = no_seguro`: se muestra una vez más el detalle del movimiento; si persiste, se trata como `no` **por decisión del cliente**, que puede cerrarlo si luego lo reconoce |
| N5 → N6 | `reconoce = no`, o lo reconoce pero el monto está mal o el cargo está duplicado (error de procesamiento) |
| N6 → N7 | política = `automatizable` (§8.3) |
| N6 → N11 | política = `revision_humana` o alguna de las cuatro verificaciones sin cumplir |
| N7 → N8 | confirmación explícita del cliente, validada, sobre la acción mostrada **en este turno** y en la **misma sesión autenticada**. Tras re-autenticarse, la confirmación se pide de nuevo. Si el mismo mensaje trae además un `corregir` sobre un dato de la acción, la confirmación no vale: se muestra la acción corregida y se pide otra vez (`INV-CONFIRMA`: la confirmación es de la acción exacta mostrada). Por texto, la confirmación solo vale si el Intérprete leyó **únicamente** `confirmar`; con otra cosa a la vez no se ejecuta y se recuerda lo pendiente (el botón siempre vale) |
| N7 → N12 / N11 | rechaza la acción / pide persona |
| N8 → N9 | la herramienta respondió (éxito o error tipado) |
| N8 → N11 | error tras reintentos acotados (2) o circuito abierto |
| N9 → N10 | el estado releído coincide con lo solicitado; `YA_EXISTE` → se informa el reclamo existente, releído |
| N9 → N11 | no coincide, o el resultado es incierto (tiempo agotado): se relee por clave de idempotencia **antes** de traspasar y el paquete dice el número real o "estado desconocido, clave X, verificar" (**nunca se afirma éxito**) |
| cualquier nodo → mismo nodo | **consulta lateral:** intención informativa (horarios, cómo funciona un reclamo, plazos, estado de un reclamo propio). Se responde con la fuente permitida y se vuelve al mismo nodo con el estado intacto; si hay una acción pendiente, se recuerda en una frase |
| N10/N12 → N2 | pregunta nueva tras resolver: ciclo nuevo con el caso resuelto como contexto; nunca se reinicia la conversación ni se fuerza un proceso |

### 6.2b Rutas por intención (el mismo grafo, todo el ciclo de vida)

| Intención (§8.2.2) | Ruta | Acción y confirmación |
|---|---|---|
| `disputas.reportar_cargo` | N2 → N3 → (N4) → N5 → N6 → N7 → N8 → N9 → N10 / N11; desde un movimiento, N5 directo | `abrir_reclamo`, confirmado |
| `movimientos.consultar` | N2 → N3 → (N4) → mostrar hechos → N10 | Sin acción |
| `disputas.consultar_reclamo` | N2 → leer reclamos del cliente → (elegir si hay 2+) → N10 | Sin acción; la respuesta sale del último evento releído |
| `disputas.agregar_informacion` | N2 → elegir reclamo → N7 → N8 → N9 → N10 | `agregar_informacion_reclamo`, confirmado; solo si el reclamo no está cerrado |
| `disputas.retirar_reclamo` | N2 → elegir reclamo → N7 (con motivo) → N8 → N9 → N10 | `retirar_reclamo`, confirmado; solo si no está resuelto. Nada se borra |
| `tarjetas.bloquear` | N2 → elegir producto → N6 → N7 → N8 → N9 → N10 | `bloquear_producto`, confirmado; siempre disponible para el cliente |
| `tarjetas.desbloquear` | N2 → elegir producto → N6 → N7 → N8 → N9 → N10, o N11 | Solo si lo bloqueó el cliente y no hay señal de riesgo; si no, traspaso |
| `tarjetas.consultar_estado` | N2 → leer estado → N10 | Sin acción |
| `consulta_informativa` | Cualquier nodo → responde → vuelve al mismo nodo (pila) | Sin acción |

### 6.3 Estados de una acción (explícitos; no existe "algo salió mal, intentamos otra vez")

| Estado | Significado | Siguiente |
|---|---|---|
| `propuesta` | La política la permite; se muestra al cliente con su `action_intent_id` | `confirmada` / `descartada` |
| `confirmada` | Confirmación válida en esta sesión y esta versión de conversación | `ejecutando` |
| `ejecutando` | Escritura condicional en curso | `completada` / `fallida` / `desconocida` |
| `completada` | Releída y coincide | N10 |
| `fallida` | Error tipado y **sin efecto** comprobado | N11 (traspaso) |
| `desconocida` | Timeout sin saber si se escribió | Relectura por `action_intent_id`: `completada` o `fallida`; si la relectura también falla, N11 con "estado desconocido". **Nunca una segunda escritura ciega** |
| `descartada` | El cliente no confirmó, o expiró el TTL | — |

### 6.4 Fallas parciales

| Falla | Qué hace el sistema |
|---|---|
| El LLM no responde a tiempo | Reintento acotado; si el circuito se abre, **sin modelo** (§8.4): A11 enruta por el estado y traspasa. No ejecuta nada |
| La base no responde (lectura) | No afirma nada; mensaje de indisponibilidad; traspaso si persiste |
| Timeout de escritura | Estado `desconocida` (§6.3) |
| Falla no prevista del código | El turno se revierte y queda como incidente con su rastro; en una transacción nueva, la conversación pasa a una persona por el camino sin modelo, con el motivo `falla_del_sistema` y la referencia del incidente. El mensaje que falló no se guarda (pudo traer un secreto sin marcar): el paquete le pide al asesor que el cliente lo repita. Si el rescate también falla, el cliente recibe un error con la referencia |
| Timeout de verificación | Se trata como `desconocida` |
| Se corta la conexión del chat | Al reconectar, el chat pide el estado a la base y sigue en el mismo punto. Cada mensaje lleva un identificador del cliente: un reenvío no se procesa dos veces |
| Solicitud duplicada | `action_intent_id` ya consumido → devuelve el resultado ya registrado |
| Proveedor de IA caído o cupo agotado | **Sin modelo** (§8.4): A11 enruta por el estado, traspaso con paquete "sin resumen de IA", el chat muestra el aviso de espera (interfaz, con datos de A14) y alarma roja al supervisor (`PROCESOS.md` §P8) |
| Datos vencidos (`data_as_of`) | Informa lo histórico; no automatiza sobre cargos posiblemente nuevos |
| Respuesta parcial del LLM (salida cortada o que no parsea) | Esquema inválido → un reintento con el error → traspaso a una persona con la conversación. El fallo queda registrado como error de diseño |
| Llega algo que no es texto (imagen, audio, archivo, sticker) | Nunca bloquea: entra al estado como hecho (`adjunto_recibido`) y se responde con la verdad, en el mismo nodo (§8.9) |

Límites:
- sin tope de turnos: el traspaso por estancamiento es por falta de progreso (`max_sin_progreso` del nodo: 3 por defecto, 5 donde equivocarse es legítimo; §8.1);
- por turno, una interpretación y una redacción, cada una con un reintento, y una comparación cuando hace falta;
- versión optimista en la fila de conversación contra dobles envíos.

**Escenarios de referencia** (los tres que exige el reto):
- normal: identifica, confirma, abre el reclamo, verifica;
- ambiguo: 2+ candidatos o datos faltantes, se aclara con opciones reales;
- requiere persona: señal de riesgo o política no automatizable, traspaso con paquete.

## 7. Vista de despliegue

Render (API Docker y un sitio estático con tres rutas), Neon (PostgreSQL), GitHub (código y Actions), llaves gratuitas del
modelo. Camino de despliegue, migraciones, verificación, reversión y secretos: **`DESPLIEGUE.md`**. Protección del
enlace público, conjunto de demo y latencia: `02_PLAN.md` §5.

## 8. Conceptos transversales

### 8.1 Contexto de la conversación

El contexto es la lección más importante de construir asistentes en producción, y la pieza que más se prueba
aquí. El diseño sigue la práctica publicada por quienes construyen agentes a escala:
- el modelo lee **la transcripción completa y el estado estructurado** (*slots*) en cada turno (Rasa CALM [Rasa, s. f.-a, s. f.-b]);
- el contexto es un recurso finito: se le da **el conjunto más pequeño de información de alta señal**; lo durable
  vive **fuera del contexto**, en notas estructuradas, y se trae **justo a tiempo** cuando hace falta (Anthropic,
  *context engineering* (Anthropic, 2025)).

**Regla 1: presupuesto de contexto, no tope de turnos.**
- **La conversación nunca se corta por número de turnos.** La transcripción se envía completa mientras quepa en el
  presupuesto del historial (6.000 caracteres, `PRESUPUESTO_HISTORIAL_CARACTERES`, medido contra el cupo por minuto).
- Si no cabe, se **compacta sin resumen libre del modelo**: todo lo durable de los turnos antiguos ya vive en el
  `EstadoConversacion`. Se conservan literales el primer mensaje del cliente y los turnos más recientes que quepan. Los
  demás salen del historial enviado y siguen guardados en la base.
- **El traspaso por estancamiento es por falta de progreso, no por conteo.** Cada nodo declara
  `max_sin_progreso` en la configuración del flujo:
  - por defecto 3;
  - 5 donde equivocarse es legítimo (elegir entre opciones, dar una fecha o un monto).

  Solo cuentan los turnos en que **no cambió nada** en el estado: ningún dato nuevo, ningún cargo avanzó, ninguna
  acción. Al llegar al umbral se ofrece una persona; nunca se bloquea en silencio. Los valores iniciales vienen de
  un sistema conversacional en producción del autor. Se **calibran** con las conversaciones de desarrollo: se mide
  cuántos turnos sin progreso necesitan las conversaciones que sí terminan bien, y se elige el umbral que no corte
  ninguna de ellas. Se reporta.

**Regla 2: el estado es la nota estructurada, calculada y no recordada.** Lo mantiene el orquestador en la base
(`EstadoConversacion`, CONTRATOS):
- nodo actual;
- última pregunta hecha al cliente;
- cargos en discusión con su estado;
- acción pendiente;
- señales de riesgo acumuladas;
- datos ya dados;
- pila de temas (Regla 4);
- idioma.

**Regla 3: memoria entre conversaciones, justo a tiempo.** Cuando el cliente vuelve otro día, la conversación nueva
consulta en la base sus reclamos, sus bloqueos y los avisos que no leyó. Nada se guarda "en el modelo".

**Regla 4: pila de temas para interrupciones y regresos.** Un tema nuevo (una consulta de horario, otro cargo) se
apila encima del actual. Al terminarlo, se vuelve al de abajo **con su estado intacto**, y se le recuerda al cliente
lo pendiente. Es el mecanismo estándar de *dialogue stack* (Rasa, s. f.-a, s. f.-b).

**Regla 5: cada agente ve lo que necesita y nada más.**

| Qué | Intérprete (A1) | Redactor (A8) |
|---|---|---|
| Transcripción dentro del presupuesto (con marcadores) | Sí | Sí |
| `EstadoConversacion` y pila de temas | Sí | Sí |
| Mensaje actual | Sí | Sí |
| Esquema de servicios, comandos y catálogos (§8.2) | Sí | — |
| Estado comunicable del turno (en marcadores, `CONTRATOS.md` A8) | — | Sí |
| IDs reales, documento, nombre, teléfono | **Nunca** | **Nunca** |
| Señal de riesgo, camino interno de la política | **Nunca** | **Nunca** |
| Preferencia de comunicación (lenguaje simple, pasos cortos), si hay vulnerabilidad declarada | — | Sí: es una indicación de forma, no una señal (`CASOS.md` C5) |

**Qué tiene que resolver el contexto** (cada punto con prueba en CONTRATOS §A1, en ES y PT, con variantes):
- referencias hacia atrás ("ese", "el segundo", "el que te dije");
- correcciones ("no, eran 180, no 150");
- varias cosas en un mensaje;
- interrupción y regreso;
- señales repartidas en varios turnos;
- volver después de resolver;
- volver otro día;
- cambio de idioma.

### 8.2 Clasificación: comandos, servicios, tipos de disputa y señales

No se clasifica "a ojo". Se usan tres esquemas reconocidos, cada uno para una pregunta distinta.

**8.2.1 Comandos de diálogo: qué movimiento hace el cliente en la conversación.** Siguen el catálogo de comandos del
entendimiento de diálogo de Rasa CALM (Rasa, s. f.-a, s. f.-b). El Intérprete emite una **lista de comandos**, no una sola etiqueta:

| Comando | Cuándo | Qué hace el sistema |
|---|---|---|
| `iniciar(servicio.intencion)` | Pide algo nuevo | Apila el tema y abre su flujo |
| `dar_dato(campo, valor)` | Aporta un dato pedido o no pedido | Lo guarda en el estado |
| `corregir(campo, valor)` | Cambia un dato ya dado | Reemplaza, no reinicia |
| `elegir(alias)` | Escoge una opción mostrada | Valida contra las opciones mostradas |
| `confirmar` / `negar` | Responde a la acción propuesta | Solo vale sobre la propuesta vigente |
| `cancelar(tema)` | Abandona lo que estaba haciendo | Desapila; el estado queda registrado |
| `aclarar` | El mensaje admite dos lecturas | Se pregunta con las opciones reales |
| `consulta_informativa` | Pregunta de conocimiento (horarios, plazos, cómo funciona) | Responde y vuelve al tema (pila) |
| `charla` | Saludo, agradecimiento | Respuesta breve; el estado no cambia |
| `pedir_persona` | Quiere un humano | Traspaso |
| `no_puede_identificarse` | No le llega el código o perdió el celular | Sin sesión, traspaso "identidad no verificada" (N0/N1 → N11) |
| `fuera_de_alcance` | Otra gestión bancaria | Dice qué sí puede hacer u ofrece una persona |
| `no_puedo` | No se entiende o es no bancario/manipulación | Abstención |

**8.2.2 Servicios, intenciones y campos, guiados por esquema.** Cada servicio declara sus intenciones y campos, con
una descripción en lenguaje natural que el Intérprete lee. Es el paradigma *schema-guided* (Rastogi et al., 2020): agregar un servicio
es agregar su esquema, sin tocar el Intérprete.

| Servicio | Intenciones | Campos |
|---|---|---|
| `movimientos` | `consultar` | producto?, cuándo, monto, descripción |
| `disputas` | `reportar_cargo`, `consultar_reclamo`, `agregar_informacion`, `retirar_reclamo` | cargo(s), tipo de disputa, información adicional, motivo de retiro |
| `tarjetas` | `bloquear`, `desbloquear`, `consultar_estado` | producto |
| `informacion` | `consulta_informativa` | tema |

Intenciones de otras gestiones bancarias → `fuera_de_alcance`, con la categoría registrada para el humano. La
taxonomía de 77 intenciones bancarias de BANKING77 (Casanueva et al., 2020) es la referencia de cobertura para esas categorías; no se
usan sus datos sin aprobación del organizador.

**8.2.3 Tipo de disputa: la causa, alineada con las redes de tarjetas.** Las redes clasifican las disputas en cuatro
familias: fraude (10.x), autorización (11.x), error de procesamiento (12.x) y disputa de consumo (13.x) (Chargeback.io, s. f.; Stripe, s. f.). Se
agregan las dos causas que no son contracargo:

| `tipo_disputa` | Familia | Ejemplos |
|---|---|---|
| `no_autorizada` | Fraude (10.x) | Tarjeta robada, compra no hecha por el cliente |
| `error_procesamiento` | Procesamiento (12.x) | Cargo duplicado, monto o moneda incorrectos |
| `consumo` | Consumo (13.x) | No recibido, defectuoso, suscripción cancelada |
| `autorizacion` | Autorización (11.x) | Cobro sin autorización válida del emisor |
| `estafa_autorizada` | Fuera de contracargos (APP) | El cliente pagó engañado: traspaso prioritario |
| `reconocida` | — | Confusión aclarada: se cierra sin reclamo |

El Intérprete **propone** el tipo con la evidencia del mensaje; el código lo valida contra el catálogo. El tipo
final de un caso no automatizable lo confirma el humano. **Límite declarado:** los datos no traen tipos de disputa
etiquetados, así que la exactitud de esta clasificación se mide solo en los casos de evaluación construidos.

**8.2.4 Señales de riesgo** (qué está en juego, no qué se quiere): `engano_por_tercero`, `coaccion`,
`vulnerabilidad_declarada`, `credencial_comprometida`, `producto_en_manos_de_otro` (robo, pérdida o "la tiene otra
persona": el producto puede usarse sin el cliente), `manipulacion`. Se acumulan y no se borran (§8.1).

### 8.3 Política: cuatro verificaciones antes de cada acción

**Filtro de admisibilidad, diseño de Daniel Pineda González:** antes de actuar sobre una persona, un sistema debe poder
responder cuatro preguntas. Son **cuatro verificaciones que el código calcula** con números explícitos, sobre hechos
verificados. Cada una tiene su propia medida y su propia consecuencia cuando no se cumple (falta identificar el cargo: se
vuelve a aclarar; hace falta una persona: la decide el equipo; no hay umbral certificado: el sistema no recomienda bloquear).
Ninguna compensa a otra: un puntaje alto en una no compra una violación en otra.

1. **¿Qué tan difícil es deshacer esto, y qué tan seguros estamos?** Cada acción tiene una irreversibilidad
   declarada, con su razón (`politica/comun.yaml`):
   - consultar, abrir un reclamo o agregarle información = 0 (se deshacen sin costo);
   - retirar un reclamo = 0,2 (el cliente puede volver a reclamar dentro de la ventana);
   - bloquear o desbloquear = 0,3 (reversible, pero cambia el uso del producto mientras dure);
   - abono o reembolso = 1: nunca automático.

   La certeza es el **mínimo** de tres certezas que se miden por separado:
   - autenticación: 1 con token válido;
   - identificación del cargo: 1 si hay un solo candidato y el cliente lo confirmó;
   - para un bloqueo que el sistema recomienda por su cuenta: 1 − cota del FDR del umbral certificado.

   Si la irreversibilidad supera la certeza, no se actúa.
2. **¿Tratamos igual los casos iguales?** La decisión es función pura de los hechos verificados y de la versión de
   la política: nunca del tono, la redacción, el idioma ni el acento. Se prueba con pares metamórficos.
3. **¿Queda abierta la corrección, y siempre se puede llegar a una persona?**
   - sin confirmación no hay acción;
   - toda acción tiene cómo revertirse;
   - el cliente puede pedir una persona en cualquier momento;
   - una señal de riesgo dicha en cualquier turno pesa en todos los siguientes.
4. **¿Se cuida la relación con el cliente?**
   - el texto no imputa;
   - el sistema solo recomienda un bloqueo por su cuenta si el umbral certificado lo permite (FDR ≤ 1%);
   - la conversación termina con las opciones del cliente intactas.

**Cómo se combinan:** una acción es admisible solo si pasa las cuatro. Ninguna compensa a otra: se tratan como
restricciones y no como pesos de un puntaje, igual que en los procesos de decisión con restricciones (Altman, 1999) y en
el ordenamiento cuando los pesos no se conocen con precisión (Kirkwood & Sarin, 1985) (no hay un puntaje
que se sume). Se evalúa **sobre toda la conversación**, no solo sobre el último mensaje: así se detiene la
manipulación repartida en varios turnos, donde cada mensaje parece inocente. Cada decisión guarda las cuatro
respuestas con sus números. Esa es la explicación que ven el asesor y el jurado: sale de reglas y datos, no
del razonamiento del modelo.

**Entrada:** `HechosVerificados`:
- cliente, producto, transacción y su estado (de la base);
- probabilidad calibrada `p` (o `sin_score`);
- días desde la transacción contra el reloj del sandbox;
- monto en USD: de `amount_usd`, o derivado con `daily_exchange_rates` del día; si no hay tasa, `desconocido` →
  revisión humana, nunca un monto supuesto;
- reclamos previos del cliente (90 días);
- señales del eje B validadas;
- **jurisdicción = país del cliente titular** (`customers.country`). Los productos no traen país: es una derivación
  declarada; si falta, `jurisdiccion_desconocida` → humano. Nunca el idioma: el portugués es idioma de
  servicio, no jurisdicción;
- **valores desconocidos son un tipo propio, nunca 0 ni vacío:** cualquier dato material `desconocido` (monto USD,
  jurisdicción, regla aplicable) prohíbe automatizar;
- **señales de riesgo acumuladas en el servidor y monótonas:** una señal de engaño o coacción dicha en un turno no
  desaparece porque el siguiente no la mencione;
- **tope por cliente:** 2 o más reclamos en 90 días → humano, sin inferir culpa.

**Cómo se aplica cada verificación en este dominio (todas deben cumplirse para `automatizable`):**

| Verificación | En este dominio | Si no se cumple |
|---|---|---|
| 1 · Irreversibilidad frente a certeza | Solo acciones **reversibles** se ejecutan solas: abrir reclamo (siempre reversible) y bloqueo temporal (reversible). Abonos y reembolsos **nunca** se ejecutan (el reto no autoriza mover dinero): se recomiendan al humano | La acción no se ofrece; va al humano |
| 1 · Certeza de identificación | Hay un solo candidato, verificado en la base, y el cliente confirmó que es ese | Vuelve a aclarar |
| 2 · Mismo caso, mismo trato | Dos casos con los mismos hechos reciben el mismo camino: la decisión es función pura de `HechosVerificados` + versión de política; nunca del texto ni del tono. Se prueba con pares metamórficos (mismo caso, otra redacción, otro idioma, otro acento) | Fallo de prueba = error del sistema |
| 3 · Corrección y persona siempre disponibles | Siempre existe un camino al humano y el cliente puede pedirlo en cualquier nodo. Van a revisión humana: jurisdicción o monto desconocidos, monto ≥ umbral del país, `sin_score`, señal sobre el umbral certificado o en la zona de incertidumbre, 2+ reclamos en 90 días, moneda incoherente con el país, fuera de la ventana de reclamo, estafa autorizada, señal de seguridad; y el desbloqueo tras riesgo | `revision_humana` |
| 4 · Cuidar la relación | El texto no acusa ni insinúa culpa. Se garantiza **por estructura**, no con listas de palabras ni plantillas: el redactor nunca recibe `p`, el camino interno ni ninguna señal de sospecha; recibe el estado comunicable (hechos neutros en marcadores y lo que se ofrece o pregunta, `CONTRATOS.md` A8), y redacta libremente. Se mide fuera de línea con el juez auxiliar. El sistema solo **recomienda** el bloqueo por su cuenta cuando el umbral certificado lo permite (PLAN §2) | Se mide y se reporta |

**Salida:** `DecisionPolitica` = {camino: `automatizable` | `revision_humana` | `abstencion`, acciones_permitidas[],
restricciones_evaluadas[{id, cumple, evidencia}], plazo_normativo, version_politica}. La explicación al cliente y al
humano se genera **desde esta estructura**, no desde el razonamiento del modelo (R11).

**Normativa — solo lo verificado; lo demás, `desconocido → humano`:**

`politica/{pais}.yaml` es una **política sintética de demo, declarada como tal**. No es asesoría legal ni pretende
representar toda la regulación. Cada país declara su umbral de revisión por monto, su ventana de reclamo, su plazo de
investigación (días naturales o hábiles) y la fuente de cada valor; un valor sin fuente no se carga. Lo verificado en
fuente primaria:
- **MX (CONDUSEF):**
  - tarjeta de **débito**, operación dentro de las 48 h previas al reporte: abono a más tardar el 2.º día hábil,
    **solo si el banco no exigió dos factores de autenticación**. Ese dato no existe → el abono queda
    `desconocido` y se recomienda al humano, nunca se ejecuta;
  - dictamen en 45 días.
- **CO (Decreto 587 de 2016):** aplica **solo** a reversión de pagos de comercio electrónico (5 días hábiles para
  pedirla, 15 para hacerla efectiva). No es una regla general de cargos no reconocidos.
- **AR:** marco general en el *Texto ordenado de Protección de los Usuarios de Servicios Financieros* del BCRA, con un
  plazo **general** de resolución de reclamos de hasta 10 días hábiles (BCRA, s. f.; BCRA Usuarios, s. f.). No se
  verificó un plazo propio de los cargos no reconocidos ni un abono provisional → esos quedan `desconocido`.

No hay `br.yaml`: no existen cuentas de Brasil en los datos.

**Esquema de cada regla crítica** (la política no acepta una regla sin estos campos): `nombre`, `condicion`,
`accion`, `excepciones`, `fuente` (URL primaria o "sintética de demo"), `version`, `vigente_desde`,
`verificada_el`, `prueba` (id de la prueba que la ejercita).

**Estado de la transacción:** `Declined`/`Reversed` → sin reclamo de cobro por defecto (no salió dinero), con revisión
y bloqueo a pedido. `Pending` → explicar y permitir reclamo o bloqueo a pedido.

### 8.4 Redacción y verificación

**Regla anti-código-fijo (obligatoria en todo el sistema):**
- **Todo texto que ve el cliente lo redacta el modelo**, con los hechos verificados del turno, la conversación
  reciente y el idioma. No hay plantillas de frases en Python ni en YAML para la conversación normal: ni saludos, ni
  confirmaciones, ni despedidas.
- **Python nunca interpreta el texto libre del cliente** con listas de palabras. Lo interpreta el modelo en una
  salida estructurada; Python solo valida esa estructura contra catálogos que el propio modelo vio.
- **Una sola excepción, cerrada:** los textos legales `LITERAL` (la divulgación del primer turno y el aviso de
  privacidad, `GOBERNANZA_DATOS_IA.md` §7), que agrega el código tal cual. La divulgación presenta a la asistente
  por su nombre (Lora) y lo legal; el saludo que va antes lo escribe el Redactor, en el idioma del cliente,
  correspondiendo a su saludo o, si entró sin saludar, al momento del día. El momento del día es un hecho del reloj:
  lo calcula el código con la zona horaria del país del cliente (la del banco, sin sesión); el modelo nunca mira el
  reloj. No existe un "modo sin IA" con frases de respaldo ni un catálogo de avisos.
- **Sin modelo, una persona.** Cuando no hay modelo (el proveedor cayó, el circuito está abierto, A12 da el cupo por
  agotado, o la interpretación o la redacción de una conversación fallaron tras su reintento):
  - nada se ejecuta; la acción pendiente queda como propuesta en el paquete;
  - A11 enruta por lo que el estado ya sabe (nodo, cargo en curso, señales acumuladas; sin nada de eso, habilidad
    `general`) y A10 traspasa con el paquete `sin_resumen_ia`;
  - el chat muestra el **aviso de espera** (`INTERFACES.md` §1): un elemento de la interfaz con el número de caso,
    la posición y el tiempo estimado reales o la hora en que abre la atención, con datos de A14. Es interfaz, no
    conversación: no redacta nada ni depende del caso;
  - la siguiente palabra que lee el cliente es de la persona. El supervisor ve la alarma (`PROCESOS.md` §P8).
- **Salida ilegible no es caída (`no_se_entendio`).** Si el modelo respondió pero su salida del Intérprete no se pudo leer
  tras el reintento (p. ej. un mensaje con muchos errores de tipeo), el servicio no está caído: el estado comunicable lleva la
  pregunta `no_se_entendio` (la guía del catálogo no es una frase: el Redactor la dice con sus palabras, sin culpar al cliente y
  retomando lo ya sabido) y `EstadoConversacion.no_entendidos` pasa a 1. Si el mensaje siguiente tampoco se entiende, o el modelo
  no está disponible, la conversación pasa a una persona como arriba. Una interpretación válida reinicia el contador.
- **Un fallo del modelo se corrige en el diseño, nunca con una frase.** Es la lección más cara de un sistema previo
  del autor: una frase fija "para este caso que falla" se convierte en cientos. Si la redacción o la interpretación
  fallan, el caso pasa a una persona y el fallo queda registrado para corregir el prompt, el estado comunicable o el
  verificador.
- **Candado automático:** una prueba falla si encuentra texto en español o portugués dirigido al cliente dentro de
  un `.py`, o comparaciones del mensaje del cliente contra listas de palabras.

**Cómo redacta:**
- Un prompt corto por rol, sin ejemplos narrativos. Recibe:
  - el **estado comunicable** del turno: lo que puede afirmar, preguntar, ofrecer, lo que debe ir exacto o literal
    y lo que no se comunica, por clases (`CONTRATOS.md` A8), siempre con marcadores y **nunca** como texto armado;
  - la conversación reciente;
  - el idioma.
- **Marcadores en vez de datos:** cifras, fechas, plazos, alias, números de caso y nombres de comercio
  llegan como `{MONTO_1}`, `{FECHA_1}`, `{MOVIMIENTO_1}`, `{COMERCIO_1}`, `{CASO}`, `{PLAZO}`. El código los
  reemplaza después con el valor formateado. `{MOVIMIENTO_n}` es el tipo del movimiento en el idioma del cliente
  (`config/formatos.yaml`, `tipos_movimiento`); el comercio y la ciudad llegan solo cuando el movimiento los tiene:
  un dato ausente se omite, nunca se rellena con otro. El texto no confiable de la base nunca pasa por la generación.
  El único componente que lee nombres de comercio reales es el Comparador (A3b), que no genera texto: devuelve alias
  de una lista cerrada, delimitada como dato, que el código valida.
- **La salida del redactor es estructurada:** `{texto, acciones_afirmadas[], idioma}`. El modelo **declara** qué
  acciones su texto da por hechas (la IA declara, Python valida con datos reales).

**Jerarquía de fuentes:** la base y el proceso mandan sobre la conversación. Si lo que dice el cliente choca con un
dato de la base (otro monto, otra fecha), el Redactor recibe el dato de la base como `AFIRMAR` y la diferencia como
`PREGUNTAR`: nunca afirma como hecho lo que dijo el cliente ni elige en silencio entre los dos.

**Verificador (determinista, sobre la estructura, sin listas de palabras):**
- cada marcador obligatorio aparece y no hay dígitos fuera de los marcadores;
- cada acción de `acciones_afirmadas` existe en el registro como `completada`;
- el idioma declarado coincide con el del cliente, y un identificador de idioma pequeño (modelo estadístico, no
  lista de palabras) lo confirma.

Lo que la estructura no puede atrapar (una afirmación no declarada, el tono) se **mide** fuera de línea con el juez
auxiliar y se reporta. Si la verificación falla: se re-redacta una vez con el error explicado; si vuelve a fallar,
se usa el borrador del Intérprete si pasa la verificación; si no, traspaso a una persona con la conversación, y el
fallo queda registrado como error de diseño. El aviso de traspaso lo redacta el Redactor; si tampoco puede, esa
conversación sigue sin modelo (arriba): el chat muestra el aviso de espera y responde la persona.

### 8.5 Idiomas

- Español y portugués (`contratos/idiomas.py` es la única fuente de la lista). El idioma de la conversación es un dato del estado, y lo entiende
  el modelo, no el código con listas de palabras:
  - el Intérprete declara el idioma del **mensaje**; el primer mensaje fija el de la conversación y, después, un mensaje con texto suficiente
    (12 caracteres o más) en el otro idioma la cambia; uno más corto (un "ok", un "não") no la voltea;
  - el cliente puede **pedir** un idioma con el selector ES/PT del chat: es un evento del canal (`cambiar_idioma`) que no pasa por el modelo. Lo pedido
    manda, se mantiene (`idioma_pedido`) y ningún mensaje posterior lo cambia solo; a mitad de un trámite se confirma el cambio (hecho
    `idioma_cambiado`) y se retoma lo pendiente. Un comando `pedir_idioma` para el Intérprete se probó y se retiró: bajó su detección de
    inyecciones de 20/20 a 11/20 en B6 (`evaluacion/EXPERIMENTOS.md`, E-02). **Límite declarado:** pedir el idioma con una frase escrita en el
    otro idioma no se entiende; sí se entiende un cliente que escribe en el otro idioma;
  - el código fija el idioma, el Redactor escribe en él con los hechos del turno y el identificador de idioma lo verifica. Los datos que dependen
    del idioma (nombres de movimientos, artículos) viven en `config/` y `conocimiento/`.
- **El idioma no cambia ninguna decisión.** La jurisdicción sale del país del cliente titular, nunca del idioma.
- Los marcadores se formatean según el idioma y el país (fechas, separadores de miles, moneda).
- Un mensaje en otro idioma se responde en español ofreciendo español o portugués, y no se procesa la solicitud.
- **Límite declarado:** los datos del banco están solo en español. El portugués es construido por el equipo y
  verificado por retrotraducción, no por un hablante nativo.

### 8.6 Prompts: dónde viven y cómo se relacionan con el código

- **Un prompt por agente de lenguaje:** `prompts/interprete.md`, `comparador.md` y `redactor.md` (y, solo en
  evaluación, `simulador.md` y `linea_base.md`). Las instrucciones están en un solo idioma; el idioma de salida es un parámetro.
- **Las partes que describen el dominio no se escriben a mano:** comandos, servicios, intenciones, campos,
  catálogos y clases del estado comunicable se **generan desde el catálogo único** de `contratos/` (D-14). Si se
  agrega un servicio, el prompt se actualiza solo y nunca queda desincronizado del parser ni del router.
- **Versionados:** cada llamada registra el hash del prompt, del catálogo y del modelo (A13). Un cambio de prompt es
  un cambio de código: pasa por las pruebas de contexto y por la evaluación de desarrollo antes de aceptarse.
- **Reglas de escritura** (valen para todo lo que lee un modelo: prompts, descripciones del catálogo y mensajes de
  corrección del código):
  - instrucciones en positivo; si hace falta una negación, va en la misma oración que lo que se hace en su lugar;
    sin absolutos negados;
  - lo importante al principio o al final;
  - fuentes nombradas;
  - una instrucción por concepto: si aparece en dos lugares, sea en el prompt o en el catálogo, es un error;
  - la etiqueta de un dato dice qué es, no cuándo usarlo;
  - **sin ejemplos semánticos ni frases citadas:** el modelo los toma como reglas y como léxico fijo; se prefieren
    definiciones, esquemas y validación. Una lista cerrada de valores del formato de salida es contrato, no ejemplo;
  - un mensaje de corrección dice qué hacer, no solo qué estuvo mal.

  La prueba candado `test_lo_que_lee_un_modelo_va_en_positivo_y_sin_ejemplos` los revisa sobre los prompts ya armados
  con el catálogo inyectado, y `test_catalogo_define_sin_ejemplos_entre_parentesis` sobre el catálogo.
- **Qué nunca va en un prompt:**
  - permisos;
  - umbrales;
  - reglas de política;
  - IDs reales;
  - la señal de riesgo.

  Lo que decide vive en código.

### 8.7 Datos, ciclos de vida y acceso

Tablas, ciclos de vida completos (crear, consultar, completar, retirar, desbloquear, reabrir), roles de base y
retención: `MODELO_DATOS.md`. Quién es quién y qué puede hacer: `ROLES_Y_ACCESOS.md`. Amenazas y controles:
`SEGURIDAD.md`. Cómo fluye un caso entre actores: `PROCESOS.md`. Regla central: **nada que registre un hecho se borra**, y cada cambio es un evento.

### 8.8 Base de conocimiento

**Qué es:** lo que el banco sabe y quiere comunicar, con dueño y fuente: cómo funciona un reclamo, plazos por país,
qué es un bloqueo temporal, qué hacer ante una estafa, a quién acudir si el cliente no queda conforme. **No son
frases del asistente**: son contenido que el Redactor usa como fuente y redacta con sus palabras (`INV-TEXTO` sigue
valiendo).

**Dos audiencias:**
- **pública:** la consulta el Asistente para el cliente o el visitante;
- **interna:** procedimientos del equipo (criterios de tipo de disputa, desbloqueo tras riesgo, cómo recomendar un
  abono, trato a clientes vulnerables). La consultan asesores, supervisores y observadores; nunca llega al cliente.

**Formato:** un archivo por tema en `conocimiento/{publico|interno}/{tema}.md`, versionado en el repositorio, con los
datos obligatorios de `GOBERNANZA_DATOS_IA.md` §11.3. Los públicos tienen cuerpo en español y portugués; los internos,
en español, porque todos los asesores de la plantilla lo hablan (`01_DIAGNOSTICO.md` §2.6). Cada artículo termina con
una tabla de **respaldo**: cada afirmación con su cita (Autor, año) de `BIBLIOGRAFIA.md`. El Redactor recibe solo el
cuerpo, nunca el respaldo. Índice: `conocimiento/README.md`.

**Las cifras no viven en el artículo.** Su bloque `datos` apunta a la regla que decide (`politica.mx.ventana_investigacion_dias`,
`config.identidad.sesion_minutos`) y el código pone el valor al servirlo: la fuente determinística siempre gana
(`GOBERNANZA_DATOS_IA.md` §11.1). En la prosa aparecen como marcadores `{nombre}`, que llegan al Redactor como `EXACTO`
y el verificador comprueba igual que cualquier otra cifra (§8.4).

**Gobierno:** estados, aprobación por otra persona, revisión periódica, vigilancia de las fuentes, cortacircuitos y
rastro: `GOBERNANZA_DATOS_IA.md` §11.

**Cómo la usa el Asistente:**
1. El Intérprete emite `consulta_informativa(tema)`, con el tema tomado del catálogo. El catálogo se genera desde
   los artículos publicados (D-14): agregar un artículo agrega su tema al esquema sin tocar el prompt a mano.
2. A15 trae el artículo público vigente para el país del cliente (o el general, si no hay sesión).
3. El Redactor lo recibe como `RESPONDER`, con su id y versión. Responde con **un solo artículo**, cita su id y
   versión (el verificador comprueba que sea el entregado) y declara la **suficiencia**: completa, parcial (responde lo
   que cubre y dice el límite), insuficiente o ambigua (no responde; aclara u ofrece una persona).
4. Si el Intérprete no nombra un tema, A15 corre la misma búsqueda de texto completo que usa el asesor, solo sobre
   los artículos **públicos** vigentes de su país, y entrega el mejor con la misma cita verificada y suficiencia.
   Si tampoco hay artículo, **no se inventa**: se dice que esa información no está disponible aquí y se ofrece una
   persona.

**Los horarios de atención humana** no se escriben en un artículo: salen de `config/atencion_humana.yaml`, la misma
fuente que usa el enrutador (`PROCESOS.md` §P2.7).

**Cómo la usa el asesor:** búsqueda de texto completo en Postgres (español y portugués) sobre los artículos internos y
públicos, dentro de la app de operación. Sin base vectorial: el corpus es chico y de temas cerrados, y la respuesta
tiene que ser exacta. Su mejora sigue el proceso P7 (`PROCESOS.md`).

**Artículos** (27, en `conocimiento/`; cada uno sale de un protocolo de `CASOS.md` §1):
- públicos (15): cómo funciona un reclamo; plazos por país; qué pasa con mi dinero; consultar, completar y retirar
  un reclamo; bloqueo temporal y desbloqueo; robo o pérdida de la tarjeta; qué hacer ante una estafa; nunca te
  pedimos tu clave; cómo te identificamos; cambiar o recuperar tu clave; otras gestiones (límite, reposición, datos);
  si llamas por otra persona; hablar con una persona; si no quedas conforme; privacidad y uso de IA;
- internos (12): criterios de tipo de disputa; investigación de un reclamo; robo o pérdida (bloquear primero);
  desbloqueo tras riesgo; recomendación de abono; trato a clientes vulnerables; clave o código entregado; verificar
  identidad sin código; estafa autorizada; lo que el asesor no decide en este flujo; autorización de terceros; cómo
  transferir con nota.

### 8.9 Entradas que no son texto (y la voz)

**Regla (obligatoria): nada que llegue bloquea la conversación.** El canal mira el **tipo** de lo que llegó (texto,
imagen, audio, archivo, sticker) por sus metadatos y su contenido binario, no por su significado: no es interpretar
al cliente. Lo que no es texto entra al estado como un hecho, `adjunto_recibido{tipo, tamaño}`, y el Redactor responde
con la verdad en el mismo nodo. Nunca hay silencio.

**Imágenes y documentos como evidencia.** Los bancos piden evidencia según el motivo: fotos de un producto defectuoso,
correos del comercio, comprobantes o recibos (Nu México, s. f.-a; Revolut, s. f.).
- Se aceptan JPG, PNG y PDF de hasta 5 MB, hasta 3 por conversación.
- Se adjuntan al reclamo con `agregar_informacion_reclamo`, con confirmación del cliente. Si no hay reclamo, quedan en
  la conversación y viajan en el paquete de traspaso.
- **La IA no los lee.** Un comprobante puede traer números de cuenta y datos personales (nivel restringido,
  `GOBERNANZA_DATOS_IA.md` §2): no sale hacia un modelo externo. Al cliente solo se le dice lo verificado, según el estado real: con **un reclamo abierto**
  se propone agregarlo (con confirmación); con **el caso ya en la fila** entra al paquete del asesor (sin esto quedaba guardado pero
  fuera del paquete, armado antes); **sin ninguno de los dos** el hecho `adjunto_sin_revision` dice que nadie lo revisa por ahora, sin
  hora de revisión. Nunca "lo está revisando una persona": una persona no responde a la velocidad del asistente.
- Se piden solo cuando el tipo de disputa los necesita (consumo, error de procesamiento); en un cargo no autorizado,
  no se le pide al cliente que pruebe nada.
- Controles: `SEGURIDAD.md` T-4 (tipo real por contenido, tamaño, metadatos y cola de la imagen descartados, PDF con contenido activo rechazado y servido solo como descarga, visible solo en la app del asesor, nunca a un modelo).

**Audio.** Una nota de voz se recibe como adjunto y se le dice al cliente que por ahora se atiende por escrito. No se
transcribe.

**La voz como canal: declarada, no construida.** El 85% de los contactos del banco entra por teléfono
(`01_DIAGNOSTICO.md` §2.2). La voz sería una capa encima del mismo sistema: el audio pasa a texto, entra al mismo
Intérprete, y la respuesta verificada se convierte en voz. El grafo, la política y la verificación no cambian.

### 8.10 El reloj de la persona

El tiempo lo pone el código con la zona horaria del país del cliente (la del banco, sin sesión): nunca el servidor ni
el modelo (`servicio/resolutor/reloj.py`). Los datos sintéticos terminan en una fecha de corte; en una conversación en
vivo se desplazan en bloque para que ese último día sea hoy en la zona del cliente. Todo lo interno (política, señal
de riesgo, plazos, búsqueda de cargos) trabaja en el marco de los datos, donde las diferencias entre fechas no cambian;
solo se convierte en los bordes: lo que dice el cliente ("el 15", "ayer", "hace dos horas") se interpreta en su fecha
y hora reales, y toda fecha que se le muestra sale en su fecha real. Un movimiento posterior a la hora actual del
cliente todavía no ocurrió y no se muestra. La evaluación fija su propio reloj, sin desplazamiento: es reproducible.

### 8.11 Identidad y datos sensibles en la conversación

**Cómo lo hacen los bancos.** En Nu, Revolut o Bank of America el chat vive dentro de la app, con la sesión ya
iniciada. En WhatsApp, los bancos piden los datos sensibles en un formulario (*WhatsApp Flows*) que viaja cifrado
directo al servidor del banco; al chat solo vuelve el resultado (Meta, s. f.). Y ninguno pide la clave: Nubank avisa que nunca
pide clave, token ni código de seguridad por mensaje, porque es el anzuelo de la "falsa central" (Nubank, s. f.-c).

**Aquí:**
- **Canal principal: dentro de la app del banco.** El cliente ya inició sesión en la app y el chat hereda esa
  sesión: desde el primer mensaje puede ver sus productos y actuar (en un robo, sus tarjetas y el bloqueo con un
  botón). En la demo, el inicio de sesión de la app se simula con el mismo servicio de identidad.
- **Canal sin sesión (sitio web):** la identidad se pide en un **formulario seguro dentro del chat**: documento y
  código de un solo uso que llega a la vez a todos sus canales registrados (en la demo, los buzones del sandbox del
  celular y del correo). Si perdió el celular, le llega al correo. Mientras espera identidad, el formulario reaparece
  debajo de cada respuesta. El teléfono y el correo registrados nunca se cambian por el chat: es la puerta de la toma
  de cuenta (`SEGURIDAD.md` S-5). Lo escrito ahí va directo al servicio de identidad; en el historial solo queda
  "identidad verificada" o "no verificada".
- **Nunca se pide clave, PIN, token ni código de seguridad**, ni se aceptan por mensaje. La divulgación del primer
  turno lo dice (`GOBERNANZA_DATOS_IA.md` §7).
- **Sin preguntas de conocimiento** ("¿cuál es tu ciudad de nacimiento?"): se adivinan o se averiguan.

**Números de tarjeta escritos en el chat.** La norma de tarjetas (PCI DSS) exige que el número completo se muestre solo
con los últimos cuatro dígitos y que el código de seguridad no se guarde nunca (Call Centre Helper, s. f.). Antes de guardar el mensaje o
enviarlo a un modelo, A17 busca secuencias de 13 a 19 dígitos (con espacios o guiones) que pasen el dígito de control
de las tarjetas, y las reemplaza por `[tarjeta borrada]`. Es una regla sobre la **forma** del dato, igual que borrar
documentos de los registros: no interpreta lo que el cliente quiere. Al estado entra el hecho `dato_sensible_borrado`,
y el Redactor le dice al cliente que lo borró por su seguridad y le muestra sus tarjetas por los últimos cuatro
dígitos.

**Claves y códigos escritos en el chat.** Por su forma no se distinguen de un monto o una fecha, así que A17 no puede
borrarlos. Los entiende el Intérprete: marca el tramo del mensaje que es un dato secreto (`datos_secretos[]`) y el
código lo borra del turno **antes de guardarlo** (la IA declara, Python borra). Queda la señal
`credencial_comprometida`, y el Redactor le advierte al cliente que nunca comparta su clave y le dice cómo cambiarla.

**Límite declarado:** una clave o un código de seguridad escritos sueltos no se pueden distinguir de un monto o una
fecha. No se detectan; se previenen con el aviso del primer turno y con no pedirlos nunca.

**Casos de borde:**
- **"Me robaron la tarjeta, envíenme mi clave":** la clave no se envía ni se cambia aquí (lo hace el procedimiento
  seguro del banco, fuera del sistema). Tras autenticarse, se le ofrece bloquear la tarjeta de inmediato y reclamar
  los cargos que no reconozca, y el caso va a `fraude` con prioridad 1.
- **También le robaron el celular** y no recibe el código: traspaso a `fraude`, prioridad 1, "identidad no
  verificada". El asesor sigue el procedimiento de verificación del banco (declarado). El sistema no bloquea nada
  sin identidad verificada.

## 9. Decisiones de arquitectura (ADR)

| # | Decisión | Por qué | Alternativa descartada |
|---|---|---|---|
| D-01 | Grafo explícito de estados, no un agente libre | Saber cuándo **no** actuar es lo que se califica; un grafo pequeño se prueba nodo por nodo | Agente con herramientas y política en el prompt (queda como línea base) |
| D-02 | Llamadas separadas al modelo: interpretar, comparar descripciones y redactar | Separa entender de escribir; cada una se valida por su lado | Una llamada que decide y redacta a la vez |
| D-03 | Transcripción completa dentro del presupuesto + estado estructurado (ver D-09) | El contexto no se pierde en resúmenes libres | Resumen móvil escrito por el modelo |
| D-04 | Estado de la conversación en la base, calculado | Lo que el sistema "sabe" es consultable y auditable | Memoria implícita en el prompt |
| D-05 | Verificaciones de política en código, sin puntaje único | Una violación no se compensa | Puntaje ponderado |
| D-06 | Autorización en la base (RLS) además del servicio | Si el código falla, la base igual niega | Autorización solo en el código |
| D-07 | Marcadores en vez de datos hacia el modelo | Privacidad y verificación de cifras | Datos reales en el prompt |
| D-08 | Umbral de bloqueo como artefacto certificado | Controla el riesgo que le importa al cliente | Umbral fijado a mano |
| D-09 | Presupuesto de contexto + estado estructurado + compactación por estado, sin tope de turnos | Práctica publicada de ingeniería de contexto (Anthropic, 2025); el traspaso sale por falta de progreso, no por conteo | Tope fijo de 12 turnos |
| D-10 | Comandos de diálogo + servicios guiados por esquema | Estándar de diálogo con LLM (Rasa, s. f.-a, s. f.-b; Rastogi et al., 2020); agregar un servicio no toca el Intérprete | Una lista plana de intenciones |
| D-11 | Tipo de disputa alineado a las familias de las redes de tarjetas | Es como clasifica la industria (Chargeback.io, s. f.; Stripe, s. f.) | Categorías inventadas |
| D-12 | Eventos de solo agregar y sin DELETE en la base | Auditoría y ciclo de vida verificables; nada se pierde | Borrado físico o lógico con una marca |
| D-13 | Salida del modelo en marcadores de texto con gramática estricta, parseados a objetos tipados; JSON solo en transporte | En un sistema del autor en producción se midió que forzar JSON hace que el modelo priorice el esquema sobre el contenido | JSON obligatorio sin medir |
| D-14 | Un solo catálogo (comandos, servicios, acciones) del que salen esquema, prompt y router | Evita desincronizar varios lugares por cada acción nueva | Listas repetidas en varios módulos |
| D-15 | Base de conocimiento por tema de catálogo, sin búsqueda vectorial | Corpus chico y cerrado; respuesta exacta y versionada; una pregunta sin tema no se inventa | RAG con embeddings |
| D-16 | Enrutamiento por habilidades sobre los asesores reales de `service_agents`, con desborde por niveles | Es la práctica de los centros de contacto (Salesforce, s. f.-b, s. f.-c); la plantilla real (2 especialistas de fraude en portugués) obliga el desborde | Especialidades inventadas y asignación "al primero disponible" |
| D-17 | El segmento del cliente solo ordena la espera humana; nunca entra a la política | "Mismo caso, mismo trato" (§8.3); la diferencia por segmento se mide y se reporta | Política o permisos distintos para Premium |
| D-18 | El asesor recibe asistencia (borrador, guía, artículos), nunca un envío automático | La práctica de las herramientas de atención (Nubank, s. f.-b, s. f.-a); la persona decide y responde por lo que envía | Sin asistencia (solo búsqueda) o un segundo agente conversacional que responde solo |
| D-19 | Prioridad estricta con envejecimiento hasta el nivel 3 | La seguridad va siempre primero, y ningún caso espera para siempre | Prioridad estricta sin envejecimiento; o mezclar espera y prioridad en un puntaje |
| D-20 | Ninguna frase fija en la conversación (solo textos legales `LITERAL`); sin modelo, la conversación pasa a una persona y el chat muestra el aviso de espera de la interfaz | Un fallo del modelo se corrige en el diseño; una frase "para el caso que falla" se multiplica, y un catálogo "mínimo" es la puerta de entrada | Modo sin IA con catálogo de frases; plantillas por situación de la conversación |
| D-21 | La IA no lee adjuntos; los revisa una persona | Privacidad: un comprobante trae datos restringidos | Modelo de visión externo |
| D-22 | Dos entradas al mismo flujo: desde el movimiento o desde la conversación | Así lo hacen los bancos digitales (`PROCESOS.md` §P1); desde el movimiento no hay ambigüedad sobre el cargo | Solo conversación libre |
| D-23 | Identidad en un formulario seguro fuera del historial y del modelo | Patrón de los bancos en WhatsApp Flows (Meta, s. f.); el documento y el código no deben quedar en la conversación | Pedir el documento y el código como mensajes |
| D-24 | Borrar números de tarjeta antes de guardar o llamar a un modelo | PCI DSS (Call Centre Helper, s. f.); el cliente puede escribirlo aunque no se le pida | Confiar en que nadie lo escriba |
| D-25 | La descripción del cliente la compara un modelo que solo elige alias de descripciones reales | "La transferencia", "lo del súper" o un nombre mal escrito son sentido, no palabras; el código valida el alias y el cliente confirma | Comparar por palabras en común |
| D-26 | Un movimiento se nombra por su tipo en el idioma del cliente; un dato ausente se omite | Más de 7 de cada 10 movimientos reclamables no tienen comercio | Rellenar el comercio con el tipo del dato |
| D-27 | Prioridad 3 por dinero en juego: el 10 % más alto de cada tipo de movimiento | El monto no predice fraude en los datos, pero es daño posible; relativo al tipo, sube como mucho 1 de cada 10 casos | Un umbral fijo en dólares (subiría casi todas las transferencias) |
| D-28 | Parámetros de operación en la base, cambiados por un supervisor con motivo | El presupuesto de modelo y los plazos de servicio los decide cada banco, no el código; cambian sin desplegar y cada cambio queda auditado | Valores fijos en el código o en la configuración del repositorio |

## 10. Requisitos de calidad

Escenarios medibles:
- resolución automática segura;
- escaladas correctas;
- cero acciones no autorizadas (con cota);
- p95 de latencia;
- costo por caso;
- consistencia entre idiomas.

Definiciones y umbrales: `02_PLAN.md` §4.

## 11. Riesgos y deuda técnica

- La mejora de M1 depende de un corte perfecto del conjunto sintético.
- El texto del cliente no tiene tope de longitud: un mensaje muy largo consume cupo de todos. Se mide y queda como
  límite declarado del sistema (`SEGURIDAD.md` D-1).
- El portugués se verifica solo por retrotraducción.
- El cupo gratuito limita el tamaño de la evaluación.
- La política de demo es sintética fuera de lo verificado.
- Los hitos de atención humana y las horas de los turnos son valores de diseño, sin proceso real con que calibrarlos
  (`01_DIAGNOSTICO.md` §2.6).
- La atención en portugués depende de muy pocos asesores; el desborde lo mitiga, no lo resuelve.

## 12. Glosario

`00_MAPA_SISTEMA.md` §2 (una sola fuente).

## Referencias

Completas, en formato APA 7, en `BIBLIOGRAFIA.md`.
