# 02 — Plan técnico

**Diseño de arquitectura:** Daniel Pineda González  
**Qué responde:** qué se construye con modelos, datos, evaluación y operación, y qué queda fuera. La arquitectura, los
contratos y el modelo de datos tienen su propio plano (`ARQUITECTURA.md`, `CONTRATOS.md`, `MODELO_DATOS.md`). Las citas
(Autor, año) están completas en `BIBLIOGRAFIA.md`.

---

## 1. La idea

Un sistema que atiende al cliente que no reconoce un movimiento:
1. lo autentica;
2. encuentra el movimiento en sus datos reales;
3. le muestra los hechos para que lo reconozca o no;
4. decide el camino con una política determinista (cuatro verificaciones, `ARQUITECTURA.md` §8.3) y una señal de
   riesgo calibrada con control estadístico del riesgo (M1, §2);
5. actúa solo con confirmación explícita y verifica que la acción quedó hecha;
6. cuando no le corresponde decidir, pasa el caso a una persona con los hechos verificados.

En español y portugués, con cada paso registrado y medible.

Tres principios:
- **P1. El modelo interpreta; el código decide y ejecuta.** El modelo de lenguaje nunca elige un cliente, un permiso,
  un monto ni una acción: emite una estructura que el código valida contra datos reales.
- **P2. Nada se afirma sin estar verificado.** Toda cifra, fecha, comercio o número de caso que llega al cliente sale
  del registro de ejecución, y un verificador lo comprueba antes de enviar.
- **P3. No actuar es una respuesta válida.** Abstenerse, aclarar y traspasar son salidas de primera clase, con su
  propia métrica.

---

## 2. Componente aprendido M1: señal de riesgo calibrada con control estadístico del riesgo

El diagnóstico no encontró señal incremental sobre el `fraud_score` en ningún atributo analizado
(`01_DIAGNOSTICO.md` §2.3). El score sí predice, con un corte exacto (§2.2 del diagnóstico).

- **Qué decide la señal `p`, y solo eso:**
  - si el sistema **recomienda por su cuenta** bloquear el producto;
  - la prioridad del caso en la cola humana.

  Nunca clasifica el caso ni decide que algo es fraude. En la interfaz se llama "señal de riesgo". El cliente
  siempre puede pedir el bloqueo, con cualquier `p`.
- **Etiqueta:** `is_fraud`, del organizador.
- **Separación temporal**, sin fuga; la prueba no se toca hasta el final:

  | Ventana | Periodo | Uso |
  |---|---|---|
  | Aprendizaje | 2023-06 → 2025-06 | Calibrar y proponer el umbral |
  | LTT | 2025-07 → 2025-12 | Certificar el umbral |
  | Prueba bloqueada | 2026-01 → 2026-06 | Medir una sola vez |

  Deduplicación antes de separar; cada fila se asigna por la fecha de la transacción.
- **Calibradores:**
  - `isotonica_presente(score)`: regresión isotónica sobre las filas con score (Zadrozny & Elkan, 2002);
  - `p_ausente = P(fraude | sin score)`: frecuencia con intervalo de Wilson.
- **Riesgo que se controla: FDR(τ)**, la fracción de recomendaciones de bloqueo que caen sobre legítimas. Es la frase
  que importa al cliente y al banco: "de cada 100 recomendaciones de bloqueo, a lo sumo 1 es a un cliente legítimo".
  No se certifica el FPR: con una tasa base de fraude del 0,1 %, un FPR del 1 % permitiría marcar unas 7.400 legítimas
  por semestre. El FPR se reporta siempre.
- **Procedimiento** (control del riesgo con garantía finita, en el espíritu de *Learn then Test* [Angelopoulos et al.,
  2021]; `ml/m1_ltt.py`), escrito antes de mirar la ventana LTT:
  - rejilla fija de umbrales τ, paso 0,5 sobre 0-100; marcado = `score > τ`;
  - **selección en la ventana de aprendizaje:** el τ de mayor recall con FDR observada ≤ α (α = 1 %) y con marcadas
    suficientes para poder rechazar: con α = 1 % y δ = 5 % hacen falta al menos ⌈ln δ / ln(1 − α)⌉ = 299, aun con
    cero falsas alarmas;
  - **certificación en la ventana LTT con una sola prueba:** H0 = FDR(τ) > α, p-valor binomial exacto sobre las
    marcadas, bajo intercambiabilidad dentro de la ventana; se rechaza con δ = 5 %. Es una sola hipótesis elegida con
    datos independientes: no hay multiplicidad que corregir. Si no se rechaza, no hay umbral certificado y el sistema
    no recomienda bloqueos por su cuenta;
  - se publica, por cada τ de la rejilla en la LTT, `n_marcadas`, `FP` y `TP` (`artefactos/m1_ltt_tabla.json`); cada
    corrida queda con el hash de los datos, los parámetros y las métricas (`artefactos/corridas_m1.jsonl`).
- **Tres afirmaciones distintas, nunca mezcladas:** lo observado (conteos por ventana); la cota estadística
  (Clopper-Pearson sobre la LTT); y la garantía fuera de muestra, válida solo para datos intercambiables con la LTT
  (no para otro banco ni para datos reales).
- **Línea base:** la regla ingenua "score ≥ 50", la mitad de la escala. Los datos no dicen qué corte usa el banco.
- **Resultados:**

  | Ventana | Regla | Recall | FP / legítimas | FDR observado (cota 95 %) |
  |---|---|---|---|---|
  | LTT 2025-H2 | > 30 | 53,6 % | 0 / 743.210 | 0 (≤ 0,80 %) |
  | LTT 2025-H2 | ≥ 30 | 53,6 % | 102 | 21,4 % |
  | LTT 2025-H2 | ≥ 50 | 37,1 % | 0 | 0 (≤ 1,15 %) |
  | **Prueba 2026-H1** | **> 30** | **57,5 %** | **0 / 685.899** | 0 (≤ 0,86 %) |
  | Prueba 2026-H1 | ≥ 30 | 57,5 % | 92 | 21,0 % |
  | Prueba 2026-H1 | ≥ 50 | 42,0 % | 0 | 0 (≤ 1,18 %) |

  **+15,6 puntos de recall en la prueba bloqueada** (347 de 603 fraudes frente a 253), con cero falsas alarmas en
  ambas reglas. La regla "≥ 50" no alcanza a certificar la promesa del 1 %: con menos marcadas, su cota es 1,18 %.
- **Anti-trampa:** el número del umbral no puede aparecer escrito en el código, los prompts, los fixtures ni la
  política; una prueba lo busca. El umbral sale del procedimiento y se guarda como artefacto versionado
  (`artefactos/m1.json`). Una prueba de regresión exige que "≥ 30" dé falsas alarmas y "> 30" no.
- **Declaración:** el corte perfecto es un artefacto del generador sintético. El mérito es el método: calibrar,
  controlar el riesgo con garantía finita y separar por tiempo (Angelopoulos et al., 2021; Angelopoulos et al., 2024;
  Dal Pozzolo et al., 2018).
- **Vigilancia:** la distribución del score se mide mes a mes contra la ventana de aprendizaje con el índice de
  estabilidad de la población (`ml/deriva.py`); con un PSI mayor que 0,2 la cabina avisa y el umbral se vuelve a
  certificar. Medido: PSI máximo 0,0003.
- **Métricas que se reportan:** recall a FDR fijo, FDR con cota, FPR y tasa de marcado, por ventana. Con 0,1 % de
  positivos se añaden, solo descriptivas (`ml/metricas_m1.py`, `artefactos/m1_metricas.json`; no vuelven al umbral):
  ROC-AUC y PR-AUC del score crudo frente a la prevalencia, Brier de la probabilidad calibrada frente a la prevalencia
  constante, calibración por tramos con intervalo de Wilson, y el fraude sin score frente a `p_ausente`. Medido en
  LTT / test: ROC-AUC 0,823 / 0,857; PR-AUC 0,669 / 0,726 (azar 0,0009); Brier skill 0,667 / 0,724; el fraude sin score
  se observa en 0,092 % / 0,090 %, dentro del intervalo de `p_ausente` (0,105 %). La isotónica es un escalón: por
  encima de 30 el fraude es seguro y por debajo la probabilidad es de unas 3 en 10.000; es el artefacto del generador
  (`01_DIAGNOSTICO.md` §2.2), no una propiedad del fraude bancario. No se calculan tasas por segmento o país: el fraude
  no depende de ningún atributo (`01_DIAGNOSTICO.md` §2.3).

**Un solo componente aprendido.** El reto pide al menos uno contra una línea base, y M1 lo cumple. Un clasificador de
intención no tendría uso: la intención la entiende el modelo de lenguaje con toda la conversación, y sin modelo el
traspaso se enruta por el estado (A11, `ARQUITECTURA.md` §8.4). Las transcripciones del reto, además, son plantillas
vacías.

---

## 3. Datos

- **Bronce:** los CSV del organizador en Parquet, con su archivo de origen (linaje).
- **Plata** (`pipeline/plata.py`):
  - tipos y `amount_usd` derivado con la tasa del día cuando falta;
  - un registro por `transaction_id`: si llegó dos veces, se queda el de `process_date` más reciente (llegadas
    tardías);
  - marcas de coherencia por fila, sin corregir el dato: `canal_tipo_coherente` (41,5 % de las filas: el cajero solo
    retira o deposita, el datáfono solo compra o paga, una transferencia solo transfiere), `moneda_pais_coherente` y
    `fecha_producto_coherente`;
  - incremental: marca de agua por `process_date`; reprocesa solo los meses con llegadas nuevas.
- **Contratos de calidad**, en SQL de DuckDB, con dos niveles; cada corrida deja su reporte en
  `artefactos/calidad_datos.json`:
  - **bloquea** (clave duplicada o nula, fecha o estado inválido, score fuera de rango): detiene la carga;
  - **advierte** (anomalías conocidas del diagnóstico): se cuenta y no detiene. Sin esta separación, los datos
    sintéticos bloquearían el pipeline entero.
- **Oro** (`pipeline/oro.py`): el subconjunto de la demo cargado en Postgres con RLS: los clientes de los casos de
  evaluación y de las identidades de demo, con todos sus productos y movimientos, las tasas de cambio y la plantilla
  de asesores de chat. Lo elige `pipeline/seleccion.py` con semilla, sin elección manual; un manifiesto guarda la
  regla, la semilla, los IDs y su hash (`evaluacion/manifest_casos.json`).
- **Derivados:** el umbral de "dinero en juego" por tipo de movimiento (`pipeline/dinero_en_juego.py` →
  `artefactos/dinero_en_juego.json`, `PROCESOS.md` §P2.3).
- **Memoria:** toda transformación grande en SQL de DuckDB; nunca tablas completas en pandas (3 GB de RAM).
- **Qué ve el cliente de un movimiento:** monto, fecha, hora, producto, su tipo (compra, retiro, transferencia, pago,
  ajuste) y, si existen, comercio y ciudad. La incoherencia canal-tipo no se menciona ni bloquea la automatización;
  la incoherencia material, moneda distinta a la del país (2,25 %), hace ambiguo el monto y lleva a revisión humana.
- **Frescura:** diaria. El cliente reclama movimientos de días anteriores; la entrega incremental de archivos no exige
  *streaming* (enunciado).
- **Procedencia (R13):** banco, sintético del organizador; casos de evaluación, construidos por el equipo sobre
  clientes y movimientos reales del conjunto; política, sintética declarada salvo lo verificado en fuente primaria;
  portugués, construido por el equipo.

---

## 4. Evaluación

- **Verdad de referencia independiente:** `evaluacion/ground_truth_cases.yaml`, escrita antes del orquestador y sin
  importar `politica/*.yaml` (una prueba lo vigila). Por caso: `expected_tool_calls`, `expected_state`,
  `must_escalate`, `must_not_disclose`, `allowed_actions`, `forbidden_actions`. Cada cambio posterior queda con su
  motivo en `evaluacion/DIVERGENCIAS.md`. Así se mide corrección, no conformidad con la política.
- **62 casos canónicos**, uno por comportamiento, sin repetir (`CASOS.md` §2): camino normal, ambiguo o no soportado,
  requiere persona, seguridad, fallas del sistema, ciclo de vida, variantes adversariales, movimientos sin comercio y
  una batería en portugués (P1-P8) y cambios de idioma pedidos por el cliente (V6, V7).
  Una variante existe solo si prueba algo que su caso base no prueba (`base_case_id`).
- **Dos conjuntos de datos:** desarrollo (movimientos de 2025-H2, para iterar) y final (2026-H1, que no se corre hasta
  la corrida final). Cada caso toma al azar, con semilla, un cliente real que cumpla su perfil.
- **Qué se prueba con conversación y qué con código:** los casos cubren el ciclo de vida completo y las pruebas de
  contexto (`ARQUITECTURA.md` §8.1). Lo que no es lenguaje (escritura concurrente, tiempo agotado tras la escritura,
  cambio de sujeto en la misma conexión, datos obsoletos) son pruebas del código (`tests/`).
- **Dónde corre cada prueba:**
  - **puente de archivos:** el asistente de desarrollo hace de modelo, sin gastar cupo (`DESPLIEGUE.md` §2). Prueba que
    el código haga lo correcto con una salida bien formada;
  - **modelo real:** los casos canónicos, con las llamadas espaciadas dentro de los límites medidos (A12). Una corrida
    por sistema y conjunto. La repetición (pass^k) no cabe en el cupo gratuito y se declara.
- **Usuario simulado:** personajes (Homero, Marge, Abe, Burns, Bart, Lisa) en un modelo de otra familia. El puntaje
  sale del estado final de la base y del registro, comparado con la verdad de referencia.
- **Línea base justa:** la misma identidad, RLS, herramientas, datos y modelo. Única diferencia: la política va solo
  en el prompt y no existe el motor determinista.
- **Métricas**, definidas en `evaluacion/metricas.py`, con numerador y denominador publicados:
  - `eligible`: casos donde la verdad de referencia permite automatizar;
  - `safe_auto_resolution`: estado terminal `RESUELTO` ∧ sin violación de seguridad ∧ estado esperado alcanzado,
    sobre `eligible` y sobre los intentados;
  - `containment`, separada en correcta y falsa; nunca "no escaló" como éxito;
  - escalada correcta, faltante e innecesaria;
  - inseguros (revelación, acción no autorizada o desenlace materialmente incorrecto), con denominador;
  - latencia p50/p95; costo por caso y por resolución;
  - todo por idioma y segmento, con intervalos (Wilson). Con 0 inseguros se reporta la cota superior, nunca "cero
    riesgo".
- **Costo:** suma de tokens de entrada y salida de todas las llamadas del caso, reintentos incluidos (el simulador,
  aparte). Con llaves gratuitas no hay cobro: el equivalente en USD usa el precio público del modelo y se presenta
  como referencia.
- **Reproducibilidad:** cada llamada registra proveedor, modelo, propósito, `request_id`, hash del prompt y fecha. Las
  corridas se tratan como muestras independientes.
- **Juez auxiliar** (tono y claridad, rúbrica de 1 a 3 por dimensión: no imputa, claridad, empatía proporcionada), de
  otra familia que el sistema (Zheng et al., 2023; Panickssery et al., 2024). Nunca entra a una métrica principal. Se
  valida contra 50 respuestas puntuadas a ciegas por el autor (kappa de Cohen por dimensión; con kappa < 0,6, esa
  dimensión no se presenta).
- **Portugués:** los casos PT los genera un modelo y se verifican por retrotraducción (doble verificación de sentido,
  no revisión nativa).
- **Lenguaje de los resultados:** "probado en nuestra batería", nunca "validado"; "no encontramos señal incremental",
  nunca "el fraude es independiente"; "asociado con", nunca "causa".

---

## 5. Operación

- **Trazas:** un registro JSON por turno (`operacion.registro_turnos`) con versiones, pasos, latencia, tokens y
  decisión; cada llamada al modelo en `operacion.consumo_modelos`, exitosa o fallida, con su razón real.
- **Reintentos y cupo:** un reintento por componente con el error explicado; pool de llaves con enfriamiento por
  error 429 y circuito por llave (A12). Sin modelo: traspaso enrutado por el estado (A11).
- **Idempotencia:** `action_intent_id` e índice único de reclamo activo por movimiento.
- **Seguridad con pruebas automáticas** (`SEGURIDAD.md`): PostgreSQL ≥ 16.15; rol de ejecución
  `NOSUPERUSER NOBYPASSRLS`; `ENABLE` + `FORCE ROW LEVEL SECURITY` en toda tabla sensible; sujeto fijado con
  `SET LOCAL` dentro de cada transacción; tokens firmados (cliente 15 min, equipo 8 h).
- **Privacidad** (`GOBERNANZA_DATOS_IA.md`): lista cerrada de campos por prompt; ningún ID, señal de riesgo ni score
  llega a un modelo externo; retención en `MODELO_DATOS.md` §5.
- **Salida hacia la interfaz:** todo dato de la base como texto plano.
- **Frescura:** cada estado lleva `data_as_of`; un movimiento posterior a la fecha de corte no se concluye inexistente.
- **App de operación** (`ROLES_Y_ACCESOS.md`, `PROCESOS.md` §P2, `INTERFACES.md` §3): presencia y capacidad del asesor;
  cola por habilidad, idioma y prioridad con semáforo; caso en una sola pantalla con el paquete, la conversación, la
  guía y la búsqueda de conocimiento; responder, transferir con nota, resolver, devolver al sistema, desbloquear tras
  riesgo y marcar un artículo; investigación en back-office (cola sin datos del cliente, tomar el siguiente, pedir
  información, corregir el tipo, decidir con fundamento, registrar el abono y cerrar); supervisor con colas,
  indicadores, auditoría, reasignar, reabrir, cambiar la presencia de un asesor y los parámetros de operación;
  observador de solo lectura. Los asesores son un subconjunto
  real de `service_agents` (`01_DIAGNOSTICO.md` §2.6).
- **Vista en vivo** (`INTERFACES.md` §2): el chat y, a la derecha, lo que pasa en cada turno (nodo, interpretación,
  candidatos, las cuatro verificaciones con sus números, herramienta, relectura y redacción). Modo personajes y modo
  paso a paso sobre las corridas grabadas.
- **Modelos y cupo:** llaves gratuitas propias del proyecto (Groq y OpenRouter), repartidas por papel en
  `config/llaves.yaml` (sistema, evaluación, línea base y simulador) para que no se quiten cupo entre sí. Sistema:
  `openai/gpt-oss-120b` en Groq; respaldo de la demo: `nvidia/nemotron-3-super-120b-a12b:free` en OpenRouter; simulador:
  `qwen/qwen3.8-27b`. El modelo de cada papel se eligió midiendo calidad, latencia y tokens por turno.
- **Despliegue** (`DESPLIEGUE.md`): GitHub (código y Actions), Render (API Docker y un sitio estático con tres rutas),
  Neon (Postgres, subconjunto declarado; si supera el 70 % de 0,5 GB tras migrar, no se despliega).
- **Parámetros de operación** (`PROCESOS.md` §P9): lo que decide el banco y no el código (el presupuesto de tokens por
  conversación, los días que un reclamo espera al cliente) se ve en la cabina y lo cambia un supervisor, con motivo.
- **Mantenimiento semanal** (GitHub Actions): vigilancia de las fuentes de la bibliografía y purga por retención
  (`DESPLIEGUE.md` §4).
- **Protección del enlace público:** código de acceso a la demo (no autoriza nada: cada endpoint exige token y RLS);
  límites por IP, sesión y conversación; guardián de cupo en el servidor antes de cada llamada. El modelo nunca decide
  sobre su propio consumo.
- **Para el jurado:** identidades de demo con buzón de código del sandbox; identidades de asesor, supervisor y
  observador.

---

## 6. Repositorio

```
factored-hackathon-2026-aa-team/
  README.md          instalación, cómo probarlo, resultados y límites
  Makefile           base, migrar, datos, m1, test, api, evaluar
  docs/              los planos (00_MAPA_SISTEMA.md dice qué responde cada uno)
  contratos/         catálogo único y modelos compartidos (Pydantic)
  pipeline/          bronce → plata → oro con contratos; selección con semilla; dinero en juego
  ml/                M1: calibradores y umbral certificado
  servicio/          un módulo por componente (ARQUITECTURA.md §5.3)
  prompts/           Intérprete, Comparador, Redactor; simulador y línea base solo para evaluación
  politica/          común y por país (mx, co, ar)
  config/            formatos, atención humana, identidad, llaves, retención, textos legales
  conocimiento/      publico/ e interno/: un artículo por tema, versionado
  migraciones/       SQL numerado: esquemas, roles, RLS, funciones de transición
  evaluacion/        verdad de referencia, corredor, evaluador, métricas, línea base, corridas, reporte
  apps/web/          un sitio estático con tres rutas
  artefactos/        lo que producen los procedimientos (M1, dinero en juego, calidad, cupo medido)
  scripts/           operación: migrar, cargar conocimiento, auditar, verificar planos y despliegue, escanear llaves
  scripts/dev/       puente de archivos, medición de cupo y de trato, recorrido en navegador
  scripts/diagnostico/  diagnóstico de los datos del organizador
  tests/             espejo de servicio/, candados y pruebas de seguridad
```

---

## 7. Plataformas

| # | Plataforma | Para quién | Dónde |
|---|---|---|---|
| 1 | Chat del cliente (ES/PT), ruta `/cliente` | El cliente | Render, un sitio estático con tres rutas |
| 2 | Vista en vivo, ruta `/vista`: en vivo, personajes (en local y en el video) y paso a paso | Demo, video y jurado | Mismo sitio |
| 3 | App de operación, ruta `/operacion` | El equipo humano | Mismo sitio |
| 4 | API: identidad, conversación, herramientas, política, enrutador, registro | Las tres anteriores | Render |
| 5 | Base: servicio, atención, operación | La API | Neon |
| 6 | Pipeline, M1 y reporte de evaluación | Reproducibilidad y jurado | Repositorio |

**Lo que se reutiliza.** Diseño, no código, de un sistema conversacional del autor en producción: detector de
estancamiento, estado comunicable, verificación de la redacción, pruebas con personajes y el puente de archivos. Del
mismo sistema, tres piezas de código reescritas con pruebas propias: el puente de archivos, los feriados de Colombia
y el esqueleto del lector de marcadores. Bibliotecas: FastAPI, Pydantic, psycopg,
DuckDB, scikit-learn (isotónica), langid (idioma). Métodos publicados: τ²-bench (usuario simulado y puntaje por estado
final), *Learn then Test*, comandos de diálogo (CALM), servicios guiados por esquema (SGD) y arc42.

---

## 8. Alcance

**Construido:**
- pipeline con contratos de dos niveles, M1 calibrado y certificado;
- grafo de conversación con los tres casos obligatorios en español y portugués;
- identidad con código a todos los canales y anti-enumeración; RLS con pruebas;
- herramientas con escritura condicional e idempotencia; verificación posterior a la acción;
- Comparador semántico de descripciones y movimientos nombrados por su tipo;
- traspaso con paquete; sin modelo → persona;
- enrutador por habilidades con desborde por niveles, envejecimiento, turnos, aceptación de 60 s y transferencia con
  nota; prioridad por dinero en juego;
- asistencia al asesor: guía del caso, artículos y borrador a pedido;
- base de conocimiento de 27 artículos (15 públicos ES/PT y 12 internos) con cargador que valida la cabecera;
- adjuntos como evidencia; entrada desde el movimiento;
- registro de toda falla con su razón, cabina del sistema, indicadores y auditoría por conversación;
- evaluación contra verdad de referencia independiente y línea base;
- ante una falla no prevista del código, el caso pasa a una persona con la referencia del incidente;
- investigación en back-office (`PROCESOS.md` §P3) con alarma de plazo, avisos al cliente en cada cambio de estado y
  cierre por vencimiento cuando el cliente no responde;
- acciones del supervisor: reasignar, reabrir y cambiar la presencia de un asesor; marcas del asesor sobre artículos;
- aviso cuando la espera real supera la estimada en 50 %; oferta de seguir en español cuando nadie en turno habla el
  idioma del cliente (`PROCESOS.md` §P2.5, nivel 3);
- parámetros de operación manejados por el banco: presupuesto de tokens por conversación y días de espera al cliente;
- cortacircuitos por artículo y vigilancia semanal de las fuentes (`GOBERNANZA_DATOS_IA.md` §11.6, §11.8);
- fotos guardadas sin metadatos; purga por retención con evento de conteos;
- deriva del `fraud_score` medida mes a mes contra la ventana de calibración (PSI), con alerta en la cabina.

**Diseñado y declarado, no construido** (dependen de sistemas reales del banco o de un canal que la demo no tiene):
- voz como canal;
- integración con la plataforma de centro de contacto, el back-office de abonos y las notificaciones del banco;
- dimensionamiento de personal (Erlang).

**Fuera:** modelos de fraude por rasgos de comportamiento (no hay señal); búsqueda vectorial (`ARQUITECTURA.md` D-15);
OpenTelemetry completo; paneles de equidad en la app; pruebas de carga más allá de p50/p95 y límites básicos.
