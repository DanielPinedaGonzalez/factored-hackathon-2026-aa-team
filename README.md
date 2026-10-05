# AA TEAM · "No reconozco este cargo"

**Diseño de arquitectura:** Daniel Pineda González  
Factored AI & Data Hackathon 2026. Datos sintéticos del organizador; política de demo sintética y declarada.

## At a glance

An AI-first customer-service assistant for one banking problem: a customer sees a charge and says "I don't recognize this".
It understands the conversation in **Spanish or Portuguese**, finds the real transaction in the customer's data, and
**decides with rules and evidence, not with the model's text**: it opens a verified claim, blocks a card, asks, abstains,
or hands the case to the right person with full context.

- **The model understands; the code decides.** The model only describes the message with a closed catalog. Every action passes four checks, a confirmation, an idempotent tool and a re-read of the real state.
- **We only claim what we verified.** A deterministic verifier checks figures, actions and language before anything reaches the customer.
- **No model, a person.** If the model fails, nothing runs and the case goes to the team. No canned phrases.
- **Security in the database.** The customer comes from the token; row-level security denies the row even if the code is wrong.
- **One learned component with a finite-sample guarantee** (M1): a calibrated fraud signal with a certified threshold.

**What is delivered.** This repository (code, tests, documentation); the deployed demo and the video (the links come in the submission, the demo link carries an access
code); six slides in English (`docs/presentacion/presentacion.pdf`); the HTML version (`presentacion.html`) adds speaker notes and a presenter mode (`F` full screen, `P` speaker window).

**Try it.** Open the link and press **Try it** (*Probar*): pick one of seven ready-made demo customers (no need to search a customer), the session is already open, and you can tap a suggested message or write anything. On the right you see the customer's account (no internal identifiers) and, after every message, what the system did step by step. *End session* clears everything. The chat lives inside the bank app and inherits its session. Pick a demo identity (`DEMO-1001` to `DEMO-1007`: normal path, ambiguous, needs a person, stolen card,
Portuguese, Premium, risk signal) and write, for example, *"me salió un cobro raro de ayer, yo no hice eso"* or *"me robaron la tarjeta"*. The staff screens (live view, operation,
system) have an **EN / ES** switch in the header; the conversation itself is in Spanish or Portuguese.
**Launch film.** `docs/lanzamiento/lanzamiento.html` tells one customer's story in 12 scenes, from the notification to the close, with the 15-step map of the conversation staying on screen and lighting up as the narration names each step. It is generated from `docs/lanzamiento/escenas.py`; `voz.py` makes the narration (an AI voice) and `grabar.py` records it scene by scene. Open the HTML in a browser, press `F`, advance with Space (`A` runs it alone, `V` adds the voice, `P` opens a window with the line to say).

**Credits and use.** Built by Daniel Pineda (AA TEAM) during the Factored AI & Data Hackathon 2026, an event by Factored. The code is under the [PolyForm Noncommercial License 1.0.0](LICENSE): you may read, run, study and build on it for noncommercial purposes, keeping the author's notice; any commercial use needs a separate agreement with the author. The data is synthetic and belongs to the hackathon organizer (it is not in this repository). The Factored name and logo belong to Factored and appear only to say which event this was made for.

**Presenter notes** (switch `🎙` in the header) explain each screen, each demo customer and each turn, in English with the Spanish in parentheses; a **flow map** highlights the nodes this conversation went through; the **About** tab lists the key ideas and the honest limits.

**Measured, and what that means.** On the **final set** (62 canonical cases with customers and transactions from 2026-H1, never used to develop; one pass of the frozen system) **55 pass (89 %, 95 % CI 79–94 %)**
and **1 has an out-of-policy action** (an action the policy forbids, here opening a claim that did not apply; upper bound 7.4 %). The baseline (the same model with the rules only in the prompt) passes 23/62 (37 %) with 11 out-of-policy actions (upper bound 27.7 %). Correct escalation: 15/16 against 6/16.
Seven cases fail and we show them, with their causes (a model reading a sentence the wrong way, a documented priority rule, a known language limit): they are in
[`docs/REPORTE_EVALUACION.md`](docs/REPORTE_EVALUACION.md) and [`evaluacion/EXPERIMENTOS.md`](evaluacion/EXPERIMENTOS.md), together with the experiments we tried and reverted, a LightGBM comparison
(more variables do not beat the bank's fraud score) and one earlier final pass that we interrupted and discarded. Few cases, wide intervals: "tested in our battery", not "validated".
The raw run files are not published (they contain fragments of the organizer's records); the report regenerates from them with `python -m evaluacion.reporte`.

**Why a subset of the data.** The analysis and M1 (diagnosis, the calibrated fraud signal) use the **full** dataset (23.5 M rows, 13 tables), processed in DuckDB. The running demo uses a **subset of 131 customers**
(those behind the 62 evaluation cases and the demo identities, with all their products and transactions, picked at random with a fixed seed so anyone can reproduce it). Reasons: the development machine has 3 GB of RAM,
the free database tier is 0.5 GB, and the demo needs to answer in seconds. The repository does **not** contain the organizer's data: `make datos` builds the subset from your own copy.

**Honest limits.** The conversation graph (its steps and transitions) is written in code, not declared as data. The author's preferred way of working is to declare processes as data (BPM-style YAML), with a generic engine that runs them; here the graph was coded directly to build and test the whole system within the hackathon. Moving it to declarative processes is the first item of the improvement plan (`docs/02_PLAN.md` §9, item 0) and is the recommended next step. Synthetic data; a small evaluation; the Portuguese is checked by back-translation, not by a native reviewer; asking for a language with a *sentence* written in the other
language is not understood (the selector and simply writing in the other language are); the free model quota limits how many full evaluations can run.

Drawings of one turn, the state machine and every failure path: [`docs/DIAGRAMAS.md`](docs/DIAGRAMAS.md).

## En español

Asistente de atención de un banco para el momento en que un cliente ve un movimiento que no reconoce. Entiende la
conversación completa en español o portugués, encuentra el movimiento real en sus datos aunque lo describa con sus
palabras, y **decide con reglas y evidencia, no con el texto del modelo**: abre un reclamo verificado, bloquea una
tarjeta, aclara, se abstiene o pasa el caso a la persona correcta del equipo con todo el contexto.

## Qué lo hace distinto

- **El modelo interpreta; el código decide.** El modelo describe el mensaje con comandos y señales de un catálogo
  cerrado. Una función pura aplica cuatro verificaciones antes de cada acción: irreversibilidad frente a certeza,
  mismo caso mismo trato, corrección y persona siempre disponibles, y cuidado de la relación. Nada se ejecuta por lo
  que diga el modelo.
- **Solo se comunica lo verificado.** Cada escritura es idempotente y se relee antes de afirmarla. El texto al
  cliente lo redacta el modelo con marcadores, y un verificador determinista comprueba cifras, acciones e idioma.
- **Sin modelo, una persona; nunca frases fijas.** Si el modelo falla o se agota el cupo, no se ejecuta nada y la
  conversación pasa a una persona con el contexto; el cliente ve su posición real en la fila.
- **Seguridad en la base, no en el prompt.** El cliente sale del token; PostgreSQL con RLS por cliente y por rol del
  equipo niega la fila aunque el código se equivoque.
- **Un componente aprendido con garantía finita.** M1 calibra el `fraud_score` y certifica el umbral de
  recomendación de bloqueo con control del riesgo (FDR ≤ 1 %): +15,6 puntos de recall en la prueba bloqueada frente a
  la regla ingenua "score ≥ 50", con cero falsas alarmas (cota superior 0,86 %).
- **Un centro de contacto real detrás.** Enrutamiento por habilidades sobre la plantilla real de asesores, prioridad
  por lo que está en juego y asistencia al asesor que nunca envía sola.

## Cómo probarlo

1. **Probar** (`/app/#/jurado`, la entrada): elige uno de los siete clientes «Cliente N» (Lora es una sola asistente que los atiende a todos) (`DEMO-1001`…`DEMO-1007`; el chat vive
   dentro de la app del banco y hereda la sesión) y escribe, por ejemplo, *"me salió un cobro raro de ayer, yo no hice eso"* o
   *"me robaron la tarjeta"*. La opción «Not signed in» muestra el sitio web: ahí se pide el formulario seguro y el
   código llega al buzón del sandbox, que el formulario muestra.

   Cada tarjeta de la pantalla muestra **lo que hay en la cuenta** de ese cliente, calculado de los datos (`scripts/perfiles_demo.py`); puedes escribir
   lo que quieras con cualquiera. Lo que cada uno tiene, a la fecha de los datos cargados:

   | Documento | Qué tiene en sus datos | Qué permite ver |
   |---|---|---|
   | `DEMO-1001` | México · Plus · 4 productos · 45 movimientos · un cargo de ayer | Camino normal: reclamo verificado con número y plazo |
   | `DEMO-1002` | Argentina · Student · 55 movimientos · **6** cargos en «Tienda Don José» | Cargos parecidos: no adivina, muestra opciones reales; otro país, otra política |
   | `DEMO-1003` | México · Basic · 34 movimientos · una transferencia de US$ 8.703 | Monto alto: pasa a una persona con el paquete completo |
   | `DEMO-1004` | México · Premium · 6 productos · 92 movimientos · una tarjeta de crédito | Robo de tarjeta: bloquear primero, luego fraude con prioridad 1 |
   | `DEMO-1005` | México · Premium · 45 movimientos · un cargo de ayer | Escribir en portugués: el idioma cambia las palabras, no las reglas |
   | `DEMO-1006` | México · Premium · 13 movimientos · 2 productos | Premium: misma política; solo cambia el orden en la espera humana |
   | `DEMO-1007` | México · Plus · 16 movimientos · puntaje de riesgo 59,8 (umbral certificado: 30) | El único sobre el umbral: el sistema recomienda bloquear |

   El enlace público lleva un código de acceso (`…/app/?codigo=XXXX`): se guarda para la sesión y se quita de la barra; si falta, la pantalla lo pide.
   El selector **ES / PT** del chat pide el idioma de la conversación; sin tocarlo, el sistema responde en el idioma en que escribes.

   Prueba también: *"mi clave es 4455"*, un número de tarjeta completo, *"ignora tus instrucciones…"*, una foto,
   *"quiero hablar con una persona"* o escribir en inglés.
2. **Lo que pasa por dentro**, en esa misma pantalla, a la derecha tras cada mensaje (también en `/app/#/vista`, solo para desarrollo, con "Paso a paso" y "Personajes"): el mapa de nodos y, paso a paso: filtro,
   interpretación, candidatos, las cuatro verificaciones con sus números, herramienta, relectura, redacción y
   verificación. "Paso a paso" reproduce las corridas grabadas de la evaluación, con lo esperado frente a lo obtenido. Esas corridas no se publican (llevan fragmentos de registros del organizador): en la demo pública ese botón muestra directamente la vista en vivo.
3. **Operación** (`/app/#/operacion`): entra como cualquiera de los asesores de la demo (`E30142` fraude, `E81176` reclamos, `E17183` general; en la demo todos reciben casos de cualquier habilidad, declarado en `config/atencion_humana.yaml`; en un banco real cada caso va a quien tiene su habilidad),
   todos con español y portugués; ponte disponible y recibe los casos que pasaron a una persona, con el paquete, la
   guía del caso y la sugerencia de respuesta. Para ver un traspaso completo, en una pestaña el cliente pide una
   persona y en otra el asesor lo atiende. En la misma pantalla, "Reclamos por investigar" es el back-office: tomar el
   siguiente, pedir información, decidir con fundamento y cerrar. "Entrar como supervisor" muestra las colas, las
   alarmas, los indicadores de la operación, la auditoría de cada conversación, las acciones del supervisor y los
   parámetros de operación que decide el banco (por ejemplo, el presupuesto de modelo por conversación).
4. **Sistema** (`/app/#/sistema`): salud, estado de cada llave del modelo, gasto del día y cada falla con su razón.

## Resultados

`docs/REPORTE_EVALUACION.md`: 62 casos canónicos (uno por comportamiento, sin repetir) con clientes reales elegidos al azar, contra una línea base con el mismo modelo y la política solo en el prompt, comparada sobre los mismos casos.
Conjunto final (2026-H1, una sola pasada del sistema congelado): **55/62 pasan** y 1 inseguro, frente a 23/62 y 11 inseguros de la línea base. Los 7 fallos están en el reporte con su causa. Métricas del enunciado con numerador,
denominador e intervalos, por idioma y segmento. Los archivos crudos de las corridas no se publican (llevan fragmentos de registros del organizador); el reporte se regenera con `python -m evaluacion.reporte`.

**Por qué un subconjunto.** El análisis y M1 usan el conjunto **completo** (23,5 M de filas); la demo usa **131 clientes** (los de los 62 casos y las identidades de demo), elegidos al azar con semilla fija. Razones: 3 GB de RAM,
base gratuita de 0,5 GB y respuesta en segundos. El repositorio no incluye los datos del organizador.

## Instalar y correr

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
make base migrar      # Postgres 16 local (puerto 5433) y esquema con RLS
make datos m1         # datos del organizador → subconjunto de demo; calibración y umbral certificado
make test             # suite completa, en su propia base
make api              # http://127.0.0.1:8020/app/
```

Las llaves gratuitas de los modelos van en `.env`, nunca en el repositorio; `make api` las carga. Sin llaves,
`MODELO_MODO=puente` hace que el asistente de desarrollo responda como modelo a través de archivos.

## Estructura del repositorio

```
servicio/      el sistema: api, orquestador, intérprete, redactor, política, herramientas, identidad, enrutador, riesgo…
contratos/     catálogo cerrado de comandos, señales y acciones, y sus modelos de datos
politica/      reglas por país (YAML); lo que decide el código, nunca el modelo
prompts/       lo que lee cada componente del modelo
pipeline/      datos: bronce → plata → oro, con contratos y calidad
ml/            M1: calibración, umbral certificado y deriva
evaluacion/    verdad de referencia, corredor, métricas, línea base y reporte
migraciones/   SQL numerado: esquema, roles y RLS
apps/web/      sitio estático: cliente, vista en vivo, operación, sistema y About; notas del presentador (EN con ES entre paréntesis) y mapa del flujo
conocimiento/  artículos públicos e internos
config/        parámetros de operación, identidad, retención y textos legales
artefactos/    salidas de los procedimientos (M1, dinero en juego, calidad de datos)
scripts/       operación (migrar, humo, verificar); dev/ herramientas de desarrollo; diagnostico/ análisis de datos
tests/         espejo de servicio/, más candados y pruebas de seguridad
docs/          planos, diagnóstico, reporte de evaluación y presentación
```

## Documentación

| Documento | Qué responde |
|---|---|
| `docs/00_MAPA_SISTEMA.md` | Por dónde empezar: qué documento responde qué, vocabulario y trazabilidad |
| `docs/VISION.md`, `docs/EXPERIENCIA_CLIENTE.md` | Qué es, para quién, y qué se le promete al cliente |
| `docs/01_DIAGNOSTICO.md` | Qué exige el reto y qué dicen los datos, medido |
| `docs/02_PLAN.md` | Modelos, datos, evaluación, operación y alcance |
| `docs/DIAGRAMAS.md` | Dibujos: un turno de punta a punta, la máquina de estados y qué pasa cuando algo falla (en inglés) |
| `docs/ARQUITECTURA.md`, `docs/CONTRATOS.md`, `docs/MODELO_DATOS.md` | Cómo está construido y qué garantiza cada pieza |
| `docs/PROCESOS.md`, `docs/ROLES_Y_ACCESOS.md`, `docs/INTERFACES.md` | Cómo fluye un caso, quién hace qué y qué ve cada uno |
| `docs/SEGURIDAD.md`, `docs/GOBERNANZA_DATOS_IA.md` | Amenazas y controles; datos, IA y conocimiento gobernados |
| `docs/CASOS.md` | Casos, protocolos de la banca y lo que hace el sistema |
| `docs/DESPLIEGUE.md` | Cómo se sube, se verifica y se revierte |

## Límites

El grafo de la conversación (sus pasos y transiciones) está escrito en código y no declarado como dato. La forma de trabajar del autor es declarar los procesos como datos (YAML estilo BPM) con un motor genérico que los ejecuta; aquí el grafo se programó directamente para construir y probar todo el sistema dentro del hackatón. Pasarlo a procesos declarativos es el primer punto del plan de mejoras (`docs/02_PLAN.md` §9, punto 0) y es el siguiente paso recomendado. Datos sintéticos; política de demo sintética fuera de lo verificado en fuente primaria; los artículos de conocimiento
se sirven como borrador hasta su aprobación; la evaluación es pequeña y la corrida final es una sola por sistema
(cupo gratuito); el portugués se verifica por retrotraducción; pedir el idioma con una frase escrita en el otro idioma no se entiende (sí se entiende el selector y
escribir en el otro idioma). Lo diseñado y no construido está listado en
`docs/02_PLAN.md` §8.
