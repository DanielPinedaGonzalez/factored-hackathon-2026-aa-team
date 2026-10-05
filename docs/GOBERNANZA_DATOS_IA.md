# GOBERNANZA DE DATOS E IA — qué datos, quién los ve, a dónde van, cuánto duran y cómo se controla la IA

**Diseño de arquitectura:** Daniel Pineda González  
**Qué responde:** qué datos hay, quién los ve, qué sale a la IA y a qué terceros, cuánto duran y cómo se gobiernan los
modelos y el conocimiento. Sigue una matriz de tratamientos con el vocabulario del NIST AI Risk Management Framework
(NIST, 2023, 2024). **No es asesoría legal** ni una declaración de cumplimiento certificado: dice qué hace el sistema
y con qué norma se contrasta.

**Punto de partida:** en esta demo **todos los datos de clientes son sintéticos**, del organizador. Aun así, el
sistema se diseña como si fueran reales. Así se demuestra lo que hace falta para operar, y se cumplen las reglas de
uso de datos del reto (nada privado en el repositorio público ni en llamadas a modelos externos).

## 1. Roles en el tratamiento de datos

Son roles legales. Los roles de las personas que usan el sistema están en `ROLES_Y_ACCESOS.md`.

| Rol | Quién, en la demo | Quién, en producción |
|---|---|---|
| Responsable del tratamiento | El organizador (dueño de los datos sintéticos) | El banco |
| Operador del sistema | AA TEAM | El banco o su proveedor, por contrato de encargo |
| Encargados (terceros) | Proveedores de modelos, hospedaje y base (§5) | Los que el banco apruebe |
| Titular | Clientes sintéticos | El cliente real |

## 2. Clasificación de los datos (cuatro niveles)

| Nivel | Qué es | Ejemplos en este sistema | Regla |
|---|---|---|---|
| **Público** | Se puede publicar | Código, documentos de `docs/`, métricas agregadas | Repositorio público |
| **Interno** | Del equipo, sin datos de personas | Artefactos de modelos, versiones de política, registros sin PII | Repositorio privado, logs |
| **Confidencial** | De una persona, necesario para atenderla | Transacciones, productos, reclamos, conversaciones con marcadores, `fraud_score`, señal de riesgo | Solo en la base, con RLS; **nunca** a un modelo externo, salvo el mensaje del cliente y marcadores |
| **Restringido** | Identifica directamente a la persona o sirve para suplantarla | Documento, nombre completo, correo, teléfono, dirección; códigos OTP; tokens; llaves | **No se carga al despliegue** (no hace falta para atender). OTP y tokens solo en su tabla, con vencimiento. Llaves solo en variables de entorno |

**Campo por campo (datos del organizador):**

| Tabla / campo | Nivel | ¿Se despliega? | ¿Va a un modelo externo? |
|---|---|---|---|
| `customers`: `document_number`, `first_name`, `last_name`, `email`, `mobile_phone`, `landline_phone`, `address`, `date_of_birth` | Restringido | **No** | Nunca |
| `customers`: país, segmento, estado, acento | Confidencial | Sí. El segmento solo ordena la espera humana (`PROCESOS.md` §P2.3) | Nunca |
| `products`: tipo, estado, moneda | Confidencial | Sí | Nunca (el modelo ve alias) |
| `transactions`: monto, fecha, ciudad, canal, estado | Confidencial | Sí | **Nunca como dato**: al modelo solo llegan marcadores; el valor lo inserta el código después |
| `transactions`: comercio y tipo de movimiento | Confidencial | Sí | Solo al Comparador (A3b), como descripción delimitada y sin IDs, montos ni fechas; al Redactor, como marcador |
| `transactions.fraud_score`, señal de riesgo | Confidencial (sensible para la relación con el cliente) | Sí | Nunca, ni al cliente |
| Transcripciones, encuestas, eventos digitales, campañas | Confidencial | No (no hacen falta para el flujo) | Nunca |
| Número de tarjeta o código escrito por el cliente en el chat | Restringido | **No**: A17 borra el número antes de guardar (`ARQUITECTURA.md` §8.11) | Nunca |
| Adjuntos del cliente (imágenes, PDF) | Restringido (pueden traer cuentas y datos personales) | Solo los que el cliente envía, en su tabla | **Nunca**: los revisa una persona (`ARQUITECTURA.md` §8.9) |
| `service_agents`: `first_name`, `last_name`, `email`, `phone` | Restringido | **No** | Nunca |
| `service_agents`: código de empleado, especialidad, idiomas, canal, turno, país, estado | Interno | Sí, solo activos de canal digital o híbrido | Nunca |

## 3. Registro de tratamientos

| Actividad | Datos | Dónde | Finalidad | Conservación (demo) | Base en producción (a validar con el banco) |
|---|---|---|---|---|---|
| Autenticación | Desafío OTP, sesión | `atencion.desafios_otp`, `sesiones` | Probar identidad | OTP: minutos; sesión: 15 min | Ejecución del servicio; seguridad |
| Conversación | Mensajes con marcadores, estado | `atencion.conversaciones`, `turnos`, `estado_conversacion` | Atender la solicitud | 90 días | Ejecución del servicio; aviso de privacidad |
| Evidencia del cliente | Adjuntos | `atencion.adjuntos` | Sustentar el reclamo | Lo que el reclamo | Ejecución del servicio; obligación legal |
| Reclamo y su historia | Transacción, tipo, eventos, notas | `atencion.reclamos`, `reclamo_eventos`, `reclamo_notas` | Gestionar la disputa | Lo que exija la norma financiera (en la demo, 90 días) | Obligación legal y contractual |
| Bloqueo | Producto, origen, eventos | `atencion.bloqueos`, `bloqueo_eventos` | Proteger al cliente | Igual que el reclamo | Ejecución del servicio |
| Traspaso a una persona | Paquete, mensajes del asesor | `atencion.traspasos`, `mensajes_asesor` | Atención humana | 90 días | Ejecución del servicio |
| Enrutamiento | Habilidad, idioma, prioridad y segmento del caso; presencia y carga del asesor | `atencion.traspasos`, `asesor_presencia_eventos` | Asignar al asesor adecuado | 90 días | Ejecución del servicio; relación laboral (asesores) |
| Registro técnico | Versiones, latencia, costo, decisiones; **sin PII** | `operacion.registro_turnos`, `consumo_modelos` | Auditoría y mejora | 90 días; consumo, lo que dure el proyecto | Interés legítimo; seguridad |
| Accesos a PII | Quién vio qué caso y cuándo | `operacion.accesos_pii` | Rendición de cuentas | 90 días | Obligación de seguridad |
| Entrenamiento y evaluación | `fraud_score` + etiqueta; mensajes del conjunto de prueba | Local; `evaluacion` | M1 y la evaluación | Lo que dure el proyecto | Datos sintéticos; en producción, evaluación de impacto previa |

## 4. Uso de IA: qué sale, a quién y con qué control

| Flujo | Qué sale del sistema | Proveedor | Qué vuelve | Controles |
|---|---|---|---|---|
| Interpretar (A1) | Mensaje del cliente, transcripción con marcadores, estado sin campos internos | Groq (`gpt-oss-120b`) | Comandos y borrador | Lista cerrada de campos; sin IDs, sin PII restringida, sin señal de riesgo; salida validada; sin autoridad |
| Comparar descripciones (A3b) | Cómo describió el cliente el movimiento y las descripciones reales de sus candidatos (tipo y comercio), con alias | Groq | Alias que corresponden | Sin IDs, montos ni fechas; opciones entre marcas de dato; solo alias de la lista, validados por el código |
| Redactar (A8) | Estado comunicable con marcadores | Groq | Texto con marcadores | Verificador de marcadores, cifras, acciones e idioma |
| Sugerir al asesor (A16, a pedido) | El mismo estado comunicable del cliente, con marcadores | Groq | Borrador con marcadores | Mismo verificador; nunca se envía solo; origen registrado |
| Respaldo de la demo (A1, A3b, A8 y A16, solo si todas las llaves de Groq están sin cupo) | Lo mismo que A1, A3b, A8 y A16 | OpenRouter (`nvidia/nemotron-3-super-120b-a12b:free`) | Lo mismo | Los mismos verificadores; **sin cero retención** (modelo gratuito): aceptable solo porque todos los datos son sintéticos; con datos reales se exige un proveedor con cero retención. No se usa en la evaluación |
| Simulador y juez (solo evaluación) | Guion del personaje; respuestas del sistema | Groq (`qwen/qwen3.8-27b`); OpenRouter como alternativa | Mensajes simulados; juicio de tono | Exigir **cero retención** (`zdr`) y excluir a los proveedores que entrenan con los datos (configuración de la cuenta) |
| M1 | Nada sale | Local | — | — |

**Condiciones de los proveedores, verificadas:**
- **Groq:** no usa las entradas ni las salidas para entrenar. No las retiene por defecto, salvo registros de hasta
  30 días para fallas o abuso. Permite activar **cero retención** en la consola, y **se activa** (Groq, s. f.).
- **OpenRouter:** por defecto no guarda prompts ni respuestas, solo metadatos. Cada proveedor detrás tiene su propia
  política; permite exigir cero retención y excluir a los proveedores que entrenan. **Ojo:** los modelos gratuitos
  pueden estar servidos por proveedores que entrenan si no se configura (OpenRouter, s. f.-a, s. f.-b).

## 5. Terceros

| Tercero | País | Función | Nota |
|---|---|---|---|
| Groq | EE. UU. | Modelo de lenguaje | Cero retención activada |
| OpenRouter y sus proveedores | EE. UU. y otros | Respaldo de la demo cuando Groq está sin cupo; juez auxiliar de la evaluación | El respaldo gratuito no garantiza cero retención (datos sintéticos); el juez, con cero retención y sin entrenamiento |
| Render | EE. UU. | Hospedaje de la API y de las interfaces | Variables de entorno cifradas |
| Neon | Región elegida al crear el proyecto | Base de datos | Cifrado en reposo; ramas como puntos de restauración |
| GitHub | EE. UU. | Código e integración | Sin datos de clientes |

**Transferencias internacionales:** en la demo no hay datos personales reales. En producción, enviar datos a
proveedores fuera del país exige una base legal propia en cada jurisdicción:
- **Colombia:** Ley 1581 y SIC (Ley 1581, 2012; SIC, 2024);
- **México:** la nueva LFPDPPP, vigente desde el 21-mar-2025, con la Secretaría Anticorrupción y Buen Gobierno como
  autoridad (Garrigues, 2025; LFPDPPP, 2025);
- **Argentina:** Ley 25.326, con cláusulas contractuales modelo aprobadas por la AAIP (AAIP, s. f.; IAPP, s. f.).

El diseño minimiza lo que sale (§4), y eso reduce el problema, pero no lo elimina.

## 6. Derechos de los titulares y "nada se borra"

- Conocer, actualizar, rectificar y suprimir (habeas data / derechos ARCO) son derechos del titular. En este sistema
  se atienden por **traspaso a una persona**, con la solicitud registrada. No hay autoservicio: es un flujo aparte,
  declarado como pendiente.
- **Cómo convive con "nada se borra":**
  - el sistema nunca borra durante la operación;
  - la supresión que pide el titular es un **proceso humano**: se **anonimizan** sus datos personales donde la ley
    lo permite, y se conserva lo que una obligación legal exige (por ejemplo, el registro de un reclamo
    financiero);
  - la ejecución deja un **evento de auditoría con los conteos, nunca con el contenido**, para poder demostrar que
    se hizo.

## 7. Transparencia con el cliente

- **El cliente sabe desde el primer mensaje que habla con un asistente virtual, que puede pedir una persona en
  cualquier momento y que nunca se le pedirá su clave.** Es el estándar de la ley europea de IA para chatbots (art. 50), usado como vara de exigencia
  aunque no aplica jurisdiccionalmente (Future of Life Institute, s. f.-a).
- Esa divulgación es de las pocas piezas de texto legal que el sistema agrega literal (clase `LITERAL` del estado
  comunicable), igual que el aviso de privacidad. Fuera de estos textos, ninguna frase es fija: sin modelo, la
  conversación pasa a una persona (`ARQUITECTURA.md` §8.4).
- **La explicación de cada decisión** (por qué se abrió el reclamo, por qué pasó a una persona) sale de las cuatro
  verificaciones con sus números, no del razonamiento del modelo.

## 8. Gobierno de los modelos

| Control | Cómo |
|---|---|
| **Ficha de cada modelo** (model card) | M1 y los modelos de lenguaje usados: propósito, datos, métricas por segmento, límites, versión |
| **Ficha del conjunto de datos** (datasheet) | Datos del organizador (hallazgos del diagnóstico) y conjuntos de evaluación (procedencia por fila) |
| **Versionado** | Hash de modelo, prompt, catálogo, política y artefactos en cada turno |
| **Control de cambios** | Un cambio de prompt, política o umbral pasa por las pruebas y la evaluación de desarrollo antes de aceptarse |
| **Supervisión humana** | Toda acción de fondo la decide una persona; el sistema solo ejecuta acciones reversibles con confirmación del cliente. Las sugerencias al asesor se miden (sin editar, editadas, descartadas) para detectar confianza ciega; esa medida revisa el sistema, nunca se usa para evaluar al asesor |
| **Equidad** | Las métricas del sistema se reportan por idioma y por segmento, con intervalos. En M1 no hay nada que desagregar: el fraude no depende de ningún atributo del cliente (`01_DIAGNOSTICO.md` §2.3) |
| **Deriva** | La cabina del sistema muestra por ventana los traspasos, las fallas de verificación y del modelo, y el gasto por llave. La distribución del `fraud_score` se mide mes a mes contra la ventana de calibración con el índice de estabilidad de la población (`ml/deriva.py` → `artefactos/deriva_m1.json`); con un PSI mayor que 0,2 la cabina da una alerta crítica y el umbral se vuelve a certificar |
| **Incidentes** | Registro con severidad, contención (por ejemplo, apagar la automatización y dejar solo traspasos), causa y corrección |

### 8.1 Inventario de modelos

No se puede gobernar lo que no se ve: el marco de riesgos de IA del NIST pide un inventario de los sistemas de IA
(función GOVERN, subcategoría 1.6) (NIST, s. f.). **Ningún componente usa un modelo que no esté en esta tabla**: el
registro de cada turno solo acepta modelos inventariados (T30), y un modelo o versión nuevos entran por *pull request*
con la evaluación de desarrollo (`ROLES_Y_ACCESOS.md` §5).

| Modelo | Versión | Dónde corre | Componente | Qué hace | Qué ve | Qué nunca hace | Si falla | Cómo se evalúa |
|---|---|---|---|---|---|---|---|---|
| `openai/gpt-oss-120b` | La del proveedor, registrada en cada llamada | Groq, cero retención | A1 Intérprete | Entiende el mensaje en la conversación y emite comandos | Mensaje ya filtrado (A17), transcripción con marcadores, estado sin campos internos, catálogo | Decidir, ejecutar, ver IDs, datos restringidos o la señal de riesgo | Sin modelo → persona (`PROCESOS.md` §P8) | Pruebas de contexto; batería de desarrollo |
| El mismo | Igual | Igual | A8 Redactor | Redacta la respuesta con el estado comunicable | Estado comunicable con marcadores | Afirmar acciones no completadas; recibir la señal de riesgo | Borrador de A1; luego una persona | Verificador A9; juez auxiliar |
| El mismo | Igual | Igual | A3b Comparador | Decide qué candidatos corresponden a la descripción del cliente | Descripción del cliente y descripciones reales (tipo y comercio) con alias | Ver IDs, montos o fechas; responder fuera de la lista | No se filtra: el cliente elige entre los candidatos | `tests/resolutor/test_comparador.py`; casos T1-T3 |
| El mismo | Igual | Igual | A16 Asistencia al asesor | Borrador de respuesta a pedido del asesor | El mismo estado comunicable del cliente | Enviar; proponer acciones de fondo | Sin borrador; el asesor escribe | A9; tasa de sugerencias editadas |
| M1 señal de riesgo | Hash del artefacto | Local | A5 | Calibra el `fraud_score` y aplica el umbral certificado | `fraud_score` | Clasificar fraude; llegar a un modelo de lenguaje o al cliente | Sin artefacto válido, ninguna acción se automatiza por riesgo y el caso va a una persona | `02_PLAN.md` §2, por ventana y por segmento |
| `nvidia/nemotron-3-super-120b-a12b:free` | La del proveedor, registrada en cada llamada | OpenRouter, sin cero retención | Respaldo de A1, A3b, A8 y A16 en la demo | Lo mismo que `gpt-oss-120b`, solo cuando todas las llaves de Groq están sin cupo | Lo mismo que `gpt-oss-120b` | Lo mismo que `gpt-oss-120b` | Una respuesta cortada por el límite de tokens no se usa: el caso pasa a una persona | **Sin evaluar con la batería**: la evaluación mide solo `gpt-oss-120b` |
| Identificador de idioma | `langid` | Local | A9 | Confirma el idioma de la respuesta | Texto redactado | Decidir nada | La verificación falla y se re-redacta | Casos ES/PT |
| Simulador de clientes | `qwen/qwen3.8-27b` (familia distinta del sistema) | Groq, cero retención, llave de simulación | E1, solo evaluación | Hace de cliente con un personaje | Guion y respuestas del sistema | Ver la verdad de referencia | La corrida se repite | — |
| Juez auxiliar | De otra familia; se registra si se corre | OpenRouter, cero retención | E3, solo evaluación | Califica tono y claridad con la rúbrica | Respuestas del sistema | Entrar a una métrica principal | Sin nota | Kappa contra el autor (`02_PLAN.md` §4) |

**Modelos de embeddings:** ninguno. La base de conocimiento se consulta por tema de catálogo (`ARQUITECTURA.md` D-15).

## 9. Mapeo con los marcos de referencia

| Marco | Qué pide | Dónde se cumple aquí |
|---|---|---|
| **NIST AI RMF — GOVERN** (NIST, 2023) | Roles, políticas, rendición de cuentas, inventario | §1, §8, §8.1 (inventario), §11; política versionada; accesos a PII auditados |
| **NIST AI RMF — MAP** | Contexto, usos y riesgos | `EXPERIENCIA_CLIENTE.md`; diagnóstico; §2 |
| **NIST AI RMF — MEASURE** | Medir desempeño, seguridad, equidad | `02_PLAN.md` §2, §8; §8 aquí |
| **NIST AI RMF — MANAGE** | Tratar los riesgos, monitorear, responder | Cuatro verificaciones, traspaso, guardián de cupo, incidentes |
| **Perfil de IA generativa (NIST AI 600-1)** (NIST, 2024): confabulación | Que no invente | Marcadores + verificador; `acciones_afirmadas ⊆ completadas` |
| NIST AI 600-1: privacidad de datos | Que no filtre datos | Lista cerrada de campos hacia el modelo; RLS; sin PII restringida desplegada |
| NIST AI 600-1: seguridad de la información | Inyección y abuso | Separación de control y dato; el texto no confiable no pasa por la generación; límites |
| NIST AI 600-1: configuración humano-IA | Supervisión adecuada | Traspaso siempre disponible; umbrales por falta de progreso |
| NIST AI 600-1: cadena de valor | Terceros | §5; cero retención |
| **SIC Circular 002 de 2024** (Colombia) (SIC, 2024): idoneidad, necesidad, razonabilidad, proporcionalidad | Tratar en IA solo lo idóneo y necesario | Minimización de §2 y §4: el modelo no recibe datos que no necesita |
| **ISO/IEC 42001** (sistema de gestión de IA) (ISO/IEC, 2023) | Gestión documentada del ciclo de vida | Declaración de aplicabilidad y autoauditoría (§12); **no se afirma certificación** |

## 10. Límites declarados

- No es asesoría legal. Las bases legales de producción las valida el banco.
- No hay autoservicio de derechos del titular: se atiende con una persona.
- La región de Neon y la configuración de cero retención se verifican al crear las cuentas y se registran aquí.

## 11. Gobierno del conocimiento

La base de conocimiento cambia: cambian las normas, los productos del banco y la tecnología. Nada en ella es estático,
y por eso cada cambio tiene dueño, aprobación, fecha de revisión y rastro. Este diseño toma el de la memoria
documental de un sistema propio del autor ya en producción, con sus mismas reglas: similitud no es evidencia,
evidencia no es respaldo, y respaldo no es verdad. Se contrasta con el control de información documentada de ISO 9001
(identificar, revisar y aprobar antes de usar, controlar las versiones e impedir el uso de lo obsoleto) (ISO, 2015) y
con los estados de artículo de KCS (Consortium for Service Innovation, s. f.-b).

### 11.1 Tres tipos de contenido, tres reglas

| Tipo | Ejemplo | Dónde vive | Regla |
|---|---|---|---|
| **Reglas que deciden** | Plazos por país, umbral de fraude, hitos de atención, duración de la sesión | `politica/*.yaml`, `config/`, artefactos | Las lee el código y deciden. Cambian solo por *pull request* con pruebas |
| **Contenido que explica** | "Cómo funciona un reclamo" | `conocimiento/` | Lo usa la IA para redactar. Nunca decide |
| **Normas externas** | CONDUSEF, PCI SSC, FFIEC | Fuera del sistema | Se citan en `BIBLIOGRAFIA.md`, no se copian, y se vigila si cambian (§11.6) |

**La fuente determinística siempre gana.** Un artículo no guarda plazos ni cifras: su bloque `datos` apunta a la regla
(`politica.mx.ventana_investigacion_dias`) y el código pone el valor al servirlo. Si la política cambia, el artículo
dice lo nuevo sin tocarlo, y nunca puede haber un número en el artículo distinto del que decide.

### 11.2 Estados de un artículo

```
pendiente_aprobacion ──(otra persona lo aprueba)──► publicado ──(se aprueba una versión nueva)──► reemplazado
        │                                              │
        └──(se rechaza, con motivo)──► rechazado       └──(se retira, con motivo)──► inactivo ──(se reactiva)──► publicado
```

- Solo un artículo `publicado` y **dentro de su vigencia** (`vigente_desde`, `vigente_hasta`) responde. Nada se
  borra: lo reemplazado y lo inactivo quedan con su historia, sin usarse.
- Equivale a los estados de KCS: no validado, validado y archivado (Consortium for Service Innovation, s. f.-b).

### 11.3 Datos obligatorios de cada artículo

`id`, `version`, `estado`, `audiencia`, `paises`, `protocolo`, `criticidad` (alta o media), `autor`, `aprobado_por`,
`vigente_desde`, `revisar_antes_de`, `fuentes` (claves de `BIBLIOGRAFIA.md`), `casos` (los de `CASOS.md` que lo usan) y
`datos` (referencias a las reglas). Sin alguno, el artículo no se carga.

### 11.4 Aprobación

- **Quien escribe no aprueba** (segregación de funciones). En la demo, una sola persona tiene los dos papeles: es una
  excepción declarada.
- Al aprobar se ve la **diferencia con la versión anterior**. La versión nueva reemplaza a la anterior en el mismo `id`.

### 11.5 Revisión periódica

- Criticidad **alta** (plazos, dinero, seguridad, identidad): revisión cada 90 días. **Vencida la fecha, el artículo
  público deja de usarse** y el asistente ofrece una persona: mejor callar que decir algo vencido.
- Criticidad **media**: cada 180 días. Vencida, sigue en uso y aparece en rojo para su dueño.

### 11.6 Vigilancia de las fuentes

Cada semana (`scripts/vigilar_fuentes.py`, en GitHub Actions) se guarda la huella del texto visible de cada URL de `BIBLIOGRAFIA.md` (sin etiquetas ni scripts: un cambio de diseño
de la página no cuenta). Si una fuente cambió, sus artículos quedan listados en `artefactos/fuentes_cambiadas.json`, la
corrida queda en rojo para su dueño y los artículos de criticidad alta que la citan dejan de servirse hasta que alguien
la revise (`--revisado CLAVE`). Una fuente que no responde se informa aparte; no cuenta como cambiada.

### 11.7 Cómo se responde con un artículo

- **Un artículo por respuesta** (una sola fuente). Si dos artículos se contradicen, no se elige ni se mezcla: pasa a
  una persona.
- La respuesta lleva la **cita** del artículo (id y versión), y el verificador comprueba que sea la que se entregó.
- El Redactor declara la **suficiencia**: completa (responde), parcial (responde lo que cubre y dice el límite),
  insuficiente o ambigua (no responde y ofrece una persona o aclara).
- **No se revela lo que no se puede ver:** si el cliente pregunta algo que solo cubre un artículo interno, la respuesta
  es la misma que si no existiera.

### 11.8 Protecciones automáticas

- **Cortacircuitos por artículo:** cada respuesta con un artículo informa si pasó la verificación al primer intento;
  con 3 fallas seguidas (una caída del proveedor no cuenta) la base lo retira (`inactivo`) y deja el evento para su
  dueño. Volver a cargar los artículos no lo reactiva: hace falta un evento `reactivado` o una versión nueva.
- **Qué rompe un cambio:** cada artículo lista sus `casos`; al cambiarlo, esos casos se vuelven a correr.
- **Rastro:** cada consulta queda como evento con el artículo, la versión y la suficiencia; cada respuesta al cliente
  guarda qué versión usó.

### 11.9 Documentos que sube el banco (producción, declarado)

En producción el banco subiría sus propios manuales y procedimientos. La ingesta del sistema de referencia valida el
formato, el tamaño y la calidad del texto extraído, guarda la huella del archivo y del contenido, y deja el documento en
`pendiente_aprobacion`. Un documento largo se parte en fragmentos solo **dentro** de un documento ya identificado; nunca
se elige el documento por parecido. En la demo, los artículos se escriben en el repositorio.

## 12. Declaración de aplicabilidad y autoauditoría

**Declaración de aplicabilidad.** ISO/IEC 42001 no exige todos sus controles: pide declarar cuáles aplican según una
evaluación de riesgo propia, proporcional al uso real de la IA (ISO/IEC, 2023). Para este sistema:

| Área | ¿Aplica? | Dónde se cumple |
|---|---|---|
| Inventario de sistemas de IA | Sí | §8.1 |
| Evaluación de riesgos e impacto | Sí | `SEGURIDAD.md`; `CASOS.md`; §2 |
| Ciclo de vida y control de cambios | Sí | §8; `ROLES_Y_ACCESOS.md` §5 |
| Datos para IA (calidad, procedencia) | Sí | `01_DIAGNOSTICO.md`; `02_PLAN.md` §3 |
| Información a las partes | Sí | §7; artículo `publico.privacidad-y-uso-de-ia` |
| Proveedores de IA | Sí | §4, §5 |
| Supervisión humana | Sí | §8; `PROCESOS.md` |
| Uso en gestión de trabajadores | **No, por diseño** | Ver abajo |

**La ley europea y los asesores.** El Anexo III considera de alto riesgo la IA usada para asignar tareas a
trabajadores o para vigilar y evaluar su desempeño (Future of Life Institute, s. f.-b). Aquí el enrutador que asigna
casos es **código determinista con reglas declaradas**, no un modelo que infiera; y ninguna medida evalúa al asesor
(la tasa de sugerencias sin editar revisa el sistema, §8). **Regla de gobierno:** no se usa IA para asignar casos ni para
evaluar asesores. Si un banco quisiera hacerlo, ese uso entraría en alto riesgo y necesitaría su propia evaluación.

**Autoauditoría trimestral.** Una tabla viva, sin costo externo: cada control de la declaración → la evidencia real
(prueba de `00_MAPA_SISTEMA.md` §4, registro o documento) → sí, no o parcial → responsable. El registro de cada turno
ya guarda lo que se espera de un agente auditable: modelo y versión, hash del prompt, la decisión de la política con
sus cuatro verificaciones, qué confirmó el cliente y qué hizo cada persona.

## Referencias

Completas, en formato APA 7, en `BIBLIOGRAFIA.md`.
