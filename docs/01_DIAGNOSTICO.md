# 01 — Diagnóstico: Factored AI & Data Hackathon 2026

**Diseño de arquitectura:** Daniel Pineda González  
**Qué responde:** qué exige el reto y qué dicen los datos. Todas las cifras están medidas sobre los datos oficiales
(5,1 GB, 7.671 archivos) con los scripts de `scripts/diagnostico/`; donde algo no se midió, se dice.

---

## 1. Qué exige el reto (requisitos atómicos, cada uno verificable)

Fuente: el enunciado oficial del reto (*Factored AI & Data Hackathon 2026*) y la presentación de lanzamiento
(*Datathon 2026 Kickoff*), entregados por el organizador a los equipos; no se redistribuyen en este repositorio.

| # | Requisito | Cómo se demuestra |
|---|---|---|
| R1 | Un solo flujo coherente, elegido con datos (motivos de contacto, demanda, calidad, restricciones) | Análisis reproducible (§3) |
| R2 | Contexto conversacional, aclarar ambigüedad, respuestas ancladas en datos permitidos | Demo + casos de prueba |
| R3 | Usar herramientas y reportar **solo acciones verificadas** | Registro de ejecución + relectura |
| R4 | Qué se responde solo, qué pide confirmación, cuándo abstenerse o transferir; permisos **fuera del texto del modelo** | Motor de política + capa de herramientas |
| R5 | Traspaso al humano: solicitud, hechos verificados, acciones, evidencia, preguntas abiertas (sin volcar la transcripción) | JSON de traspaso validado |
| R6 | Datos: contratos, chequeos de calidad, linaje, política de frescura/actualización | Pipeline + reporte |
| R7 | **Al menos un componente aprendido** contra una línea base, con etiquetas válidas, sin fuga, con justificación de representación, métrica, umbral y separación | Experimento reproducible |
| R8 | Evaluación en casos separados: datos malos o faltantes, sesión vencida, acceso no autorizado, inyección de prompt, fallo de herramienta, ambigüedad multilingüe | Batería de pruebas |
| R9 | Reportar: resolución automática segura (y tasa de intento), contención, calidad de escalada (faltantes e innecesarias), inseguros (con denominador), p50/p95 de latencia, costo por caso y por resolución; por idioma y segmento; variabilidad entre corridas; fallos incluidos | Reporte de evaluación |
| R10 | Español **y portugués**; reportar límites de cobertura de idioma | Casos ES/PT |
| R11 | Trazas, reintentos acotados, respaldo seguro, instalación reproducible, capacidad, monitoreo, control de acceso, retención de datos, trabajo pendiente honesto. La explicación sale de fuentes, reglas y registros, **no de la cadena de pensamiento** | Arquitectura + README |
| R12 | Autenticación con sesión o servicio de identidad de prueba (el documento o el número de cliente **no bastan**); acceso a cada cliente aplicado en la capa de servicio | Servicio de identidad simulado |
| R13 | Marcar qué datos son reales, anonimizados, sintéticos o creados por el equipo; nada privado ni credenciales en el repositorio público ni en llamadas a modelos externos | Tabla de procedencia |
| R14 | Entregables: repositorio público `factored-hackathon-2026-[equipo]`, enlace desplegado, 4-6 diapositivas, video | — |

Tres casos obligatorios en la demo: **normal** (resolución automática), **ambiguo o no soportado** (aclarar o
abstenerse), **requiere humano** (traspaso estructurado). Lema del reto: *"Understand → Decide → Act → Verify →
Escalate"*, *"AI should not be autonomous just because it can be"*, *"Catch more. Flag less"*.

Criterios de calificación (kickoff): justificación general del proyecto y documentación; ingeniería de IA (backend,
frontend y despliegue); analítica de datos (calidad de datos e *insights* relevantes de la solución); ingeniería de
datos (extracción y transformación); aprendizaje automático (selección, optimización, implementación y seguimiento
del modelo). "Primero que todo, que funcione." El kickoff sugiere además, para análisis de datos, el retorno por costo
por resolución.

---

## 2. Qué dicen los datos (medido)

### 2.1 Inventario real frente al resumen oficial

| Tabla | Resumen oficial | Medido | Nota |
|---|---|---|---|
| transactions | 5.000.000 | 4.425.008 | 0 IDs duplicados (el resumen anuncia ~2%) |
| call_center_interactions | 800.000 | 686.296 | 0 duplicados |
| call_transcripts | 200.000 | 171.321 | **546 textos distintos** |
| satisfaction_surveys | 250.000 | 212.759 | columnas `day/month/year` extra (evolución de esquema) |
| complaints | 80.000 | 67.095 | |
| customers | 150.000 | 150.000 | |
| digital_events | 10.000.000 | 15.620.994 | **más** de lo anunciado; 24% sin `customer_id`; IP extranjera solo aparece en eventos sin cliente (27,8% de esos, 0% en los demás); ningún vínculo con el fraude |

Rango: 2023-06-17 → 2026-06-18. Idioma: **solo español** (171.321 de 171.321 transcripciones `es`).

### 2.2 Lo que SÍ tiene señal

1. **La resolución varía mucho según el motivo de contacto, y la satisfacción observada está fuertemente asociada a
   la resolución** (asociación, no causalidad demostrada).

   | Motivo | Llamadas | Resueltas | Seguimiento | Duración mediana | CSAT |
   |---|---|---|---|---|---|
   | Transaccional | 240.056 | 92% | 22% | 205 s | 2,91 |
   | Producto | 150.863 | 90% | 24% | 263 s | 2,90 |
   | **Queja** | 117.021 | **44%** | **63%** | **431 s** | **2,43** |
   | Técnico | 102.899 | 70% | 41% | 360 s | 2,70 |
   | Comercial | 54.879 | 65% | 45% | 540 s | 2,66 |
   | Retención | 20.578 | 60% | 49% | 478 s | 2,61 |

   Resuelto → CSAT 3,0 / NPS 6; no resuelto → CSAT 2,0 / NPS 3, en todos los tipos de encuesta. El 85% entra por
   teléfono. Espera mediana: 120 s en todos los motivos.
2. **El `fraud_score` del banco predice el fraude.** AUC 0,776 y AP 0,55 (azar = 0,001). Con score ≥ 40, marca el
   0,05% de las transacciones, atrapa el 46,6% del fraude y tiene 100% de precisión. Con ≥ 30: atrapa el 55%, con
   79,6% de precisión. El 45% del fraude tiene score bajo y es indistinguible. Tasa de fraude: 4.316 de 4.425.008
   (0,098%).

   **Estructura exacta, leída por tramos de 5 puntos:**
   - las legítimas se reparten parejo entre 0 y 30, con 609 recortadas en 30,0 y **ninguna por encima**;
   - los fraudes se reparten parejo entre 0 y 100.

   Por eso score > 30 (estricto) = fraude seguro: atrapa el **55,0%** del fraude con 0 falsas alarmas, frente al
   **38,7%** de la regla ingenua "≥ 50". El 20,6% del fraude no tiene score. Es un artefacto del generador: se usa
   para demostrar el método (calibrar y certificar), no como hecho del mundo real.

### 2.3 Lo que NO tiene señal (el generador lo puso al azar)

| Hipótesis | Resultado |
|---|---|
| El fraude depende de canal, tipo, monto, hora, país, comercio o trimestre | Plano: 0,10% en todos |
| Rasgos de comportamiento agregan señal sobre el score (país distinto al del cliente, monto frente a su promedio, frecuencia en 24 h, fraudes del cliente) | AUC 0,49-0,50 cada uno. Nota: el promedio y los fraudes del cliente se calcularon sobre toda su historia, **con fuga de futuro a favor**, y aun así no hubo señal (auditoría) |
| Un modelo con **todas** las variables juntas supera al puntaje del banco (LightGBM, medido en 2025-H2; `scripts/diagnostico/c_ablacion_lightgbm.py`) | No: AUC 0,818 con todas contra 0,820 solo con el puntaje; sin el puntaje, 0,512 (azar) |
| El fraude se repite en las mismas personas | No: 4.233 clientes con al menos un fraude; 78 con dos o más, frente a ~89 esperados si cayera al azar según cuántos movimientos tiene cada uno  |
| La mora (≥ 30 días) depende de puntaje crediticio, ingreso, cupo, saldo, tasa o segmento | AUC 0,50; ~12% en todos |
| Las subcategorías de queja difieren en volumen, incumplimiento de plazo o monto | Uniformes: ~13.500 por categoría, 20% de incumplimiento en todas, monto medio ~2.500 |
| El canal o el acento (cliente y asesor, iguales o distintos) cambian la resolución | 76,6% ± 0,5 en todos |
| Las transcripciones reflejan el motivo de la llamada | No: **2 aperturas posibles** ("consultar saldo de tarjeta" / "saldo de ahorros") para los 6 motivos; 100% con variables sin rellenar (`{monto} {moneda}`); respuestas incoherentes |
| `detected_intents` sirve como etiqueta | No: `consulta_general` en el 95% |
| Una queja se puede unir con su llamada | No: `origin_interaction_id` vacío en el 100% |
| Una queja por "cargo no reconocido" corresponde a una transacción real | No: 0 de 4.090 con monto igual a alguna transacción del cliente; el cruce clientes-con-fraude × clientes-que-se-quejan (337 de 4.233) es el esperado por azar |

### 2.4 Calidad de datos (para el pipeline y para el reporte)

- `transaction_country` escribe "México" y "Mexico" (y el país del cliente, "México").
- **México no tiene transacciones en MXN:** todas en "USD" con mediana de 467, aunque el resumen anuncia MXN.
- `amount_usd` es nulo exactamente cuando la moneda es USD (57% de las filas): se deriva, no falta.
- `fraud_score` es nulo en el 20% de las filas, con la misma tasa de fraude que el resto.
- 25% de llegadas tardías (`process_date` distinto del día de la transacción).
- Transacciones "Approved" sin `response_code` (203.369).
- `customers.detected_accent` es nulo en el 30%.
- Esquema que cambia entre archivos en `satisfaction_surveys`.
- El resumen promete ~2% de duplicados: 0 por ID. Hay que buscarlos por contenido (pendiente de medir).
- Faltan filas frente al resumen: entre 11% y 16% según la tabla.

### 2.5 Lectura caso por caso (no promedios): ¿hay trampas escondidas?

La pregunta es si los promedios esconden estructura puesta a propósito para quien lea con cuidado. Se revisó así:

- **Transcripciones, enumeración total:**
  - hay 42 textos distintos de cliente y 42 de asesor, leídos todos completos;
  - todas las llamadas son combinaciones al azar de 2 saludos ("saldo de tarjeta" / "saldo de ahorros"), 4 frases
    de cierre del cliente y 5 del asesor, repetidas de 0 a 2 veces;
  - ninguna llamada sin variables vacías y ninguna con palabras de fraude, robo, bloqueo o "no reconozco" (0 de
    171.321).

  No hay conversaciones reales escondidas.
- **Fraude a nivel fino, con corrección por comparaciones múltiples (Bonferroni):** 24 comercios, 28 ciudades, 350
  sucursales, 339.963 productos, 134.515 clientes, 1.097 días, 6 categorías y 5 códigos de respuesta.
  - Ningún grupo concentra fraude.
  - Único borde: el 20-abr-2024, con 11 fraudes en 2.225 transacciones (p corregido = 0,019). Leídos uno por uno, son
    11 casos sin nada en común (ciudades, países, canales y comercios distintos). Es lo esperable por azar entre
    1.097 días.
- **Historias completas de clientes con fraude** (transacciones ±5 días, eventos digitales, llamadas ±30 días,
  quejas, estado de productos), leídas enteras, y luego medidas sobre todo el conjunto:
  - Después del fraude **no pasa nada**:
    - el cliente llama en los 30 días siguientes el 12,7% de las veces, igual que sin fraude (12,2%);
    - el producto sigue en uso el 28,8% de las veces;
    - nadie lo bloquea;
    - no hay queja asociada.
  - El fraude cae en productos donde no tiene sentido: 230 en préstamos personales, 133 hipotecarios, 62 en
    inversiones, 21 en seguros. Hay "fraudes" que son depósitos o ajustes.
- **Incoherencias estructurales**, que el pipeline debe marcar y el asistente no debe narrar como si fueran normales:
  - **canal y tipo generados por separado:** 325.993 "compras en cajero automático", 213.678 "depósitos en
    datáfono", retiros por la app;
  - **comercio:** solo existe en las compras (95%); 0% en los demás tipos;
  - **moneda de otro país:** ~1% (pesos colombianos en Argentina o México, etc.);
  - **fechas imposibles en productos:** 49,9% de productos abiertos antes del registro del cliente; 6,25% con
    `last_updated` posterior al fin de los datos (18-jun-2026).
- **Lo que no se sostuvo al verificarlo:** en un caso, una sesión digital parecía empezar con "Logout". Era un corte
  de la ventana de ±2 días. En un trimestre completo, las 152.094 sesiones empiezan con "Login". Se descartó.

**Conclusión de raíz, no de promedio:** los análisis son **consistentes con** tablas generadas de forma independiente
que comparten solo las claves (no se conoce el mecanismo del generador; es una inferencia, no un hecho confirmado).
No se encontró ninguna consecuencia observable del fraude en las otras tablas. Esto no invalida el reto. Define qué se puede afirmar:
- los datos sirven para **anclar** respuestas (el cliente, sus productos, sus movimientos reales);
- sirven para **medir demanda y resolución**;
- sirven para **calibrar el score**;
- **no** sirven para aprender comportamiento ni para evaluar desenlaces de disputas. Eso se construye y se declara.

### 2.6 El centro de contacto y el proceso de quejas (medido)

Script: `scripts/diagnostico/b_centro_contacto.py`.

**La plantilla de asesores (`service_agents`, 1.200).** Es la única descripción del equipo humano que traen los datos,
y es la base del enrutamiento (`PROCESOS.md` §P2):

| Atributo | Lo medido |
|---|---|
| Estado | 1.090 activos; 62 de vacaciones, 29 de licencia, 19 inactivos |
| Canal (`agent_type`) | Teléfono 588, digital 251, presencial 230, híbrido 131. **Para chat: 341 activos digitales o híbridos** |
| Especialidad | Fraudes 105, Quejas y Reclamos 78, otras seis de 82 a 97 cada una; **476 (40%) sin especialidad** |
| Idiomas | Portugués: **129 de 1.200** (68 español-portugués, 61 español-inglés-portugués) |
| Turno | Mañana 398, tarde 418, noche 181, rotativo 203 |

**La restricción que decide el diseño:** en chat, con portugués, hay **2** asesores activos de Fraudes (los dos de
mañana) y **4** de Quejas y Reclamos. En la tarde no hay ningún especialista de fraude que hable portugués. El
enrutamiento necesita desborde por niveles; asignar "al disponible con la especialidad y el idioma" deja casos sin
nadie.

**El proceso de quejas tal como está en los datos (`complaints`, 67.095):**

| Prioridad | Quejas | Primera respuesta (mediana) | Resolución (mediana) | SLA vencido |
|---|---|---|---|---|
| Critical | 3.355 | 38 h | 15 días | 19,2% |
| High | 9.890 | 37 h | 16 días | 20,5% |
| Medium | 33.439 | 38 h | 16 días | 20,1% |
| Low | 20.411 | 38 h | 16 días | 20,1% |

- **La prioridad no cambia nada:** una queja crítica espera lo mismo que una baja.
- **23.115 quejas (34%) no tienen asesor asignado.** De las asignadas, solo 2.842 (6,4%) van a Quejas y Reclamos y
  3.902 (8,9%) a Fraudes; el resto se reparte parejo entre especialidades sin relación con la queja.
- **El segmento no cambia la espera:** la mediana en llamadas es de 119 s para Basic, Plus y Premium, y de 120 s para
  Student.

**Lectura honesta:** igual que en §2.3, estos patrones planos pueden ser del generador sintético y no de un banco.
No se afirma que "el banco enruta mal". Lo que sí se puede decir es que **los datos no muestran ningún enrutamiento
por habilidad ni ninguna prioridad efectiva**, así que no hay un proceso que imitar ni un tiempo con que calibrar. El
diseño toma de los datos la **capacidad** (quién hay, qué sabe, qué idioma habla, en qué turno), y la regla de
enrutamiento sale de la práctica publicada de los centros de contacto (`PROCESOS.md` §P2).

### 2.7 Consecuencias para el diseño (lo que el diagnóstico obliga)

1. **No se puede entrenar un modelo de intención con estos datos.** Las transcripciones son plantillas vacías. El
   enrutamiento se evalúa con un conjunto construido por el equipo, declarado así (R13), en español y portugués.
2. **No se encontró señal incremental sobre el `fraud_score`** en los atributos analizados (§2.3); no se construye
   un modelo de fraude adicional. El componente aprendido válido con esta etiqueta (`is_fraud`) es la **calibración
   del score** (isotónica con separación temporal, más el manejo explícito del 20% sin score) y la **selección del
   umbral con control estadístico del riesgo** (Learn then Test sobre la tasa de recomendaciones equivocadas). El
   corte exacto en 30 (§2.2) es propiedad de este conjunto sintético, no del fraude bancario real.
3. **No existen disputas reales con desenlace.** Los casos de evaluación se construyen sobre transacciones reales del
   cliente (fraude y no fraude). El desenlace esperado se escribe en una verdad de referencia **independiente de la
   política**, antes de implementar, y se declara como construido por el equipo.
4. **El argumento de negocio que los datos sí sostienen:** las quejas se resuelven el 44% de las veces, duran el
   doble y la satisfacción observada es más baja. La resolución está fuertemente **asociada** con la satisfacción
   (CSAT 3 si se resolvió, 2 si no); no se afirma causalidad. El flujo tiene que atacar la
   resolución de quejas sobre cargos.
5. **La máquina tiene 3 GB:** DuckDB + Parquet para datos; el modelo de lenguaje por API; ML liviano.
6. **El equipo humano sale de los datos, no se inventa.** Los asesores de la demo son un subconjunto de
   `service_agents` (canal digital o híbrido, activos), con su especialidad, idiomas y turno reales, sin sus datos
   personales. Portugués y fraude son el cuello de botella (§2.6): el desborde es parte del diseño, no una excepción.

---

## 3. El flujo elegido: recepción y resolución de "no reconozco este cargo"

Por qué, con evidencia:
- **Queja es el motivo con peor resolución** (44%, 63% con seguimiento, 431 s).
- El cargo no reconocido es el único caso de queja que se puede **anclar a datos reales**: la transacción, el
  producto, el `fraud_score` y la etiqueta `is_fraud`.
- Permite los tres casos obligatorios de forma natural y encaja con el lema del reto.
- Permite un componente aprendido con etiqueta válida (§2.7, punto 2).

Límite honesto: que la subcategoría "cargo no reconocido" sea frecuente **no** es evidencia (todas son iguales).

### 3.1 Cómo lo hace un banco en la vida real (la parte delicada)

"No reconozco este cargo" no es una acusación ni una confesión: es un síntoma con varias causas posibles. En orden
de frecuencia, según la industria:

| Causa | Qué es | Trato correcto |
|---|---|---|
| **Confusión** | Compra propia que no reconoce por el nombre del comercio en el extracto, una suscripción olvidada o una compra de un familiar. Cerca del 25% de los "no reconocidos" se debe al descriptor del comercio (Chargeflow, 2026) | Mostrar el detalle (comercio, fecha, canal, ciudad) y preguntar sin presionar. Si lo reconoce, se cierra sin reclamo |
| **Error de procesamiento** | Cargo duplicado, monto distinto, reverso que no llegó | Verificar contra el registro; corregir o escalar a operaciones |
| **Fraude no autorizado** | Tarjeta o credenciales robadas | Bloqueo sugerido del producto (con confirmación), reclamo, abono provisional si la norma lo exige |
| **Estafa autorizada (APP)** | El cliente hizo el pago engañado por un tercero | No es "no autorizado". Reclamo especial y, según el país, un mecanismo propio (Pix MED en Brasil) (Agência Brasil, 2026) |
| **Disputa con el comercio** | Producto no recibido o defectuoso | Reversión de pago donde aplique (Colombia, Ley 1480 art. 51) (Decreto 587, 2016) |
| **Fraude de primera parte** | El cliente miente | El sistema **nunca** lo decide ni lo insinúa. Solo sube la revisión humana |

Reglas que salen de esto:
- **Nunca acusar.** El sistema no afirma "es fraude" ni "usted lo hizo": presenta hechos verificados y opciones.
- **La probabilidad no es veredicto.** El score calibrado solo decide *qué camino procedimental* se toma
  (acelerar, pedir confirmación, revisión humana), jamás el fondo.
- **Plazos por país:**
  - **México (CONDUSEF):** aclaración hasta 90 días. En tarjeta de **débito**, si se reporta dentro de 48 h y el banco
    no exigió dos factores de autenticación, el abono provisional se hace a más tardar el 2.º día hábil (los datos no
    traen los factores: queda `desconocido`, `ARQUITECTURA.md` §8.3). Hay 45 días para el dictamen; sin respuesta, procede a favor del cliente (CONDUSEF, s. f.-a; Infobae, 2025).
  - **Colombia:** reversión de pago en 5 días hábiles desde que conoce la causa, y 15 días hábiles para hacerla
    efectiva (Decreto 587 de 2016) (Decreto 587, 2016; Universidad Externado de Colombia, s. f.).
  - **Argentina (BCRA):** el marco es el *Texto ordenado de Protección de los Usuarios de Servicios Financieros*
    (BCRA, s. f.), con un plazo general de resolución de reclamos de hasta 10 días hábiles (BCRA Usuarios, s. f.). No se
    verificó un plazo propio de los cargos no reconocidos.
  - **Brasil (portugués):** Pix MED, 80 días desde el 1-sep-2026 (Agência Brasil, 2026). Es solo contexto: no hay cuentas de Brasil
    en los datos y el idioma no define la jurisdicción (ver `ARQUITECTURA.md` §8.5).

  En el prototipo los plazos viven en una **política sintética declarada** por país. No se afirma que sea asesoría
  legal.
- **Es sensible al historial:** las pruebas de *FraudBench* muestran que la seguridad se degrada cuando la
  conversación acumula sondeos previos; las mulas y el fraude de primera parte son los puntos débiles (Pai & Xian, 2026).

### 3.2 Intenciones: lo que le importa a un banco (taxonomía)

Aquí manda clasificar bien **qué quiere la
persona y qué está en juego para el banco**. Dos ejes, no uno:

**Eje A — qué quiere la persona (intención de servicio)**, limitado al flujo y su frontera. En el diseño, estas
intenciones se expresan con los comandos y servicios del catálogo (`ARQUITECTURA.md` §8.2):
- `desconoce_cargo`: el núcleo.
- `consultar_movimientos`: normal; también sirve de puente para identificar el cargo.
- `estado_de_reclamo`: seguimiento de uno ya abierto.
- `bloquear_producto`: puede venir sola o dentro de la disputa.
- `otra_intencion_bancaria`: fuera del flujo → se dice qué sí se puede hacer, o se transfiere.
- `no_bancaria` / `manipulación`: se abstiene.

**Eje B — qué está en juego para el banco** (determina la política, no lo que se responde):
- **Pérdida económica:** monto y probabilidad de fraude.
- **Riesgo regulatorio:** plazo legal del país.
- **Riesgo de seguridad:** credencial comprometida, ingeniería social en curso.
- **Retención:** cliente molesto y que reincide.
- **Vulnerabilidad:** adulto mayor, coacción declarada.

Vender, cobrar o retener no son intenciones del cliente en este flujo. Se registran como señales para el humano en
el traspaso, nunca como algo que el sistema persigue en medio de una queja.

---

## 4. Principios de diseño adoptados

- **Cuatro verificaciones antes de cada acción** (filtro de admisibilidad, diseño de Daniel Pineda González), implementadas como código
  que calcula y registra: irreversibilidad frente a certeza, mismo caso con mismo trato, corrección y persona siempre
  disponibles, y cuidado de la relación. Detalle en `ARQUITECTURA.md` §8.3.
- **El modelo entiende; el código decide y ejecuta.** Nunca afirmar una acción no verificada. Consultar la base en
  vez de "recordar". Con 2+ candidatos, se pregunta. Todo dato del cliente es no confiable hasta validarlo. Traspaso
  con hechos verificados.
- **Sin código fijo que imite inteligencia:** el modelo redacta con contexto completo; Python verifica.

## 5. Seguridad y agentes: lo que dice la literatura

- **Inyección de prompt** es el riesgo n.º 1 de OWASP LLM 2025; exceso de agencia es LLM06 (OWASP, 2025). La defensa por
  diseño (CaMeL) separa el control del dato: el texto no confiable nunca decide qué herramienta se llama (Debenedetti et al., 2025).
- Los agentes de servicio con herramientas fallan mucho y son inconsistentes. En τ-bench, gpt-4o resuelve menos del
  50% y pass^8 queda bajo 25% en retail. **La confiabilidad se mide repitiendo** (pass^k) (Yao et al., 2024; Sierra Research, s. f.; Rabanser et al., 2026).
- **Juez LLM:** tiene sesgos (autopreferencia); hay que validarlo contra juicio humano o determinístico (Zheng et al., 2023; Panickssery et al., 2024).

---

## 6. Restricciones del proyecto

| Restricción | Efecto en el diseño |
|---|---|
| Plazo corto y un equipo de una persona | Un flujo, profundo. Nada que no sume a R1-R14 |
| 3 GB de RAM | DuckDB/Parquet; LLM por API; ML liviano; no modelos locales grandes |
| Repositorio público | Solo código y documentos de este proyecto; secretos solo en `.env` |
| Costo | Sin presupuesto: llaves gratuitas; el cupo gratuito define el tamaño de la evaluación; modelo abierto por API (gpt-oss-120b o similar) |
| Privacidad | Al LLM solo le llega lo mínimo, seudonimizado. El dato es sintético, pero se diseña como si fuera real |

---

## 7. Riesgos detectados

1. **Sobreingeniería:** el reto dice explícitamente que más flujos, agentes o herramientas no suman.
2. **Circularidad en la evaluación:** quien genera el caso, quien responde y quien juzga no pueden ser el mismo
   modelo con el mismo prompt.
3. **Fuga temporal en la calibración:** el umbral se fija con datos anteriores al periodo de prueba.
4. **Afirmar mejoras de producción con mediciones offline:** prohibido por el enunciado.
5. **Portugués sin datos:** cobertura construida y declarada como tal.

---

## Referencias

Completas, en formato APA 7, en `BIBLIOGRAFIA.md`.
