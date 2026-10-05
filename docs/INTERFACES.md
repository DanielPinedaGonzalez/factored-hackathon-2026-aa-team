# INTERFACES — las pantallas de las tres aplicaciones

**Diseño de arquitectura:** Daniel Pineda González  
**Qué responde:** qué pantallas hay, qué muestra cada una, quién la ve y **de qué dato sale**: una interfaz no calcula
ni decide nada; pinta lo que la API entrega. Roles: `ROLES_Y_ACCESOS.md`. Procesos:
`PROCESOS.md`. Son rutas de un solo sitio estático (el menú muestra `/jurado`, `/operacion`, `/sistema` y `/acerca`; `/cliente` y `/vista` siguen existiendo para desarrollo, sin enlace; JavaScript sin paso de construcción en `apps/web/`, `DESPLIEGUE.md`), en español y portugués, y funcionan en el
ancho de un teléfono.

**Reglas para todas:**
- todo dato de la base se muestra como texto plano (sin HTML, sin caracteres de control; `SEGURIDAD.md` I-4);
- ningún texto dirigido al cliente vive en el código de la interfaz: sale de la API (`INV-TEXTO`); los rótulos de la
  interfaz (botones, títulos) son textos de interfaz, no conversación;
- toda pantalla tiene sus estados declarados: cargando, vacía, error y **sin modelo** (`PROCESOS.md` §P8).

---


## Modo jurado (`#/jurado`, la entrada por defecto)

**Sin cambiar de pantalla (4-oct).** Las tarjetas de los clientes quedan siempre a la vista: al pasar el mouse se despliega solo lo que la tarjeta no muestra (nada se repite);
al pulsar una queda **marcada** (✓) y el selector se vuelve una fila compacta que no se mueve, de modo que se cambia de cliente con un clic; el chat, la cuenta y lo que hizo
el sistema aparecen debajo, con todos los rasgos del cliente elegido. Antes, elegir reemplazaba la pantalla y había que volver con «Cambiar de cliente».

**Una sola entrada para el cliente (decisión del 3-oct).** El chat del cliente, la vista en vivo y el modo jurado hacían casi lo mismo: se
dejó una, «Probar». Trae el chat, la cuenta, lo que hizo el sistema, el mapa del flujo y la opción «Not signed in» (el sitio web sin sesión,
con el formulario seguro), que era lo único que solo tenía el chat del cliente. Las rutas `#/cliente` y `#/vista` se conservan sin enlace en el menú.

Una sola pantalla guiada para quien prueba el sistema sin conocerlo: **elige un cliente** (uno de los siete de demostración `DEMO-1001`…`DEMO-1007`, mostrados con sus rasgos reales —país, segmento, productos, movimientos, movimiento mayor, comercio repetido, señal de riesgo— calculados de los datos por `scripts/perfiles_demo.py`, no con una etiqueta escrita a mano; no se elige entre los 150 000 clientes), la sesión
ya queda iniciada y escribe lo que quiera o toca una sugerencia (rellena la caja, se puede editar). A la derecha, dos pestañas: **Cuenta del cliente** (movimientos de los últimos 45 días, sin identificadores internos) y
**Qué hizo el sistema** (la traza del último turno: filtro, interpretación, candidatos, política, herramienta, verificación; los identificadores `CLI-`/`TRX-`/`PRD-` se enmascaran antes de mostrarse).
«Reiniciar demo» borra los reclamos y bloqueos de las identidades de demostración; «Terminar sesión» limpia la sesión de este navegador. El acceso al sitio es con el código de la demo (`?codigo=`).
Es solo interfaz: no cambia el sistema que se midió.

## 0. Idioma de la interfaz

El idioma de la **interfaz** y el de la **conversación** son dos cosas distintas. La conversación con el cliente es en
español o portugués y la decide el sistema (`ARQUITECTURA.md` §8.5). Las pantallas del personal (vista en vivo,
operación, sistema) y todo lo que es de la demo (notas del presentador, tarjetas de clientes, «Reiniciar demo») tienen un
selector **EN / ES** en la cabecera: el idioma se guarda en el navegador y, la primera vez, sigue el idioma del navegador
(inglés si no es español). Así un jurado que no lee español puede seguir la demo. **El chat con Lora no lo sigue:** es el
producto y va en el idioma de la conversación, español o portugués (su propio selector ES / PT; `tLora` en `i18n.js`), nunca
en inglés, aunque la demo esté en inglés. «Reiniciar demo» no está dentro del chat: es de la demo.

- El texto en español es la clave de la traducción (`apps/web/i18n.js`, `apps/web/i18n_en.js`): lo que falte se ve en
  español y no rompe nada. Una prueba candado (`tests/candados/test_interfaz.py`) exige que todo rótulo tenga traducción.
- Se traducen los rótulos, los estados y códigos que se muestran (`en_cola`, `fraude`…) y los avisos de la cabina. No se
  traduce la conversación, ni lo que escribe el cliente o el asesor, ni los artículos de conocimiento ni las guías del caso,
  que siguen en el idioma del cliente o del equipo.


**Presenter notes (notas del presentador).** `apps/web/guia.js` pone comentarios cortos en pantalla —qué es cada pantalla, qué prueba cada cliente `DEMO-*` y qué pasó en el último turno según el nodo en que termina— siempre en inglés con el español entre paréntesis, sea cual sea el idioma de la interfaz. Un interruptor en la cabecera (`🎙 Presenter notes`, activo por defecto) los oculta todos. Son rótulos de la interfaz: las respuestas del asistente siguen saliendo del modelo.

**Mapa del flujo y pantalla About.** `apps/web/flujo.js` dibuja los quince nodos del grafo (`ARQUITECTURA.md` §6) y resalta los que esa conversación ya recorrió (los pasos de la traza dicen por cuáles pasó un turno) y el nodo actual; el traspaso (N11) se dibuja como una barra porque se alcanza desde casi cualquier paso. La pestaña **About** reúne en `guia.js` las frases clave y los límites declarados. Un candado (`tests/candados/test_interfaz.py`) comprueba que los nodos y los bordes del mapa existen en el plano.

**Marca.** `apps/web/marca.js` dibuja a Lora (un loro: *lora* se dice loro) en la barra, en la cabecera del chat y en el pie, que lleva los créditos (Daniel Pineda · AA TEAM · Factored AI & Data Hackathon 2026). Si existe `apps/web/hackathon.png` (fondo transparente) se muestra en el pie; si no, no aparece. En pantalla cada cliente de demostración se llama «Cliente N» (Lora es una sola asistente que los atiende a todos); `DEMO-100N` sigue siendo la identidad para iniciar sesión.

## 1. Chat del cliente

**Fuente de la respuesta.** Cuando una respuesta sale de un artículo del banco, el chat muestra bajo el mensaje de qué artículo salió
(«Fuente: título (id, versión)»): el Redactor declara la cita, el verificador la comprueba y el orquestador la entrega como elemento `fuente`.

```
┌──────────────────────────────────────────────┐
│ Banco · Asistente virtual         [ES | PT]  │
├──────────────────────────────────────────────┤
│ A: ¡Buenas tardes! Soy Lora, la asistente    │
│    virtual del banco. Puedes pedir una       │
│    persona en cualquier momento. Nunca te    │
│    pediremos tu clave.                       │
│ C: me salió un cobro raro de 180 lucas ayer  │
│ ┌─ Formulario seguro ─────────────────────┐  │
│ │ Documento  [__________]                 │  │
│ │ Código     [______]  (llegó a tu canal) │  │
│ │                          [Verificar]    │  │
│ └─────────────────────────────────────────┘  │
│ ┌─ Movimiento ────────────────────────────┐  │
│ │ compra · TIENDA XYZ · 17-jun · 14:32    │  │
│ │ $ 180.000 · tarjeta •••• 1234           │  │
│ │ [Lo reconozco]  [No lo reconozco]       │  │
│ └─────────────────────────────────────────┘  │
├──────────────────────────────────────────────┤
│ [Mis movimientos] [📎] [Hablar con una persona]│
│ [ Escribe aquí...                     ] [➤] │
└──────────────────────────────────────────────┘
```

| Elemento | Qué es | De dónde sale |
|---|---|---|
| Mensajes del asistente | Texto redactado y verificado | `POST /conversacion/turno` (A2) |
| Formulario seguro | Documento y código; lo escrito va directo al servicio de identidad y no entra al historial | `POST /identidad/desafio`, `POST /identidad/verificar` (`ARQUITECTURA.md` §8.11) |
| Tarjeta del movimiento | Hechos releídos de la base: tipo, comercio y ciudad si los tiene, fecha, hora, monto, producto; botones "Lo reconozco", "No lo reconozco", "No estoy seguro" = eventos del canal, no texto: no gastan una llamada al modelo | Hechos del turno; evento `elegir`/`reconoce` |
| Tarjeta de confirmación | La acción exacta propuesta y los botones "Sí, hazlo" / "No": la confirmación es un evento ligado a su `action_intent_id`, determinista (el texto libre también vale y pasa por el Intérprete) | Evento `confirmar`/`negar` |
| Estado del caso | Número, estado, plazo y quién lo tiene, siempre visible cuando hay un reclamo o un traspaso | `consultar_reclamo` y A14 |
| Mis movimientos | Lista de movimientos del titular; en cada uno, "no reconozco este cargo" (D-22) | `GET /movimientos` (RLS) |
| Adjuntar | JPG, PNG o PDF hasta 5 MB; el chat avisa lo que recibió | `POST /adjuntos` (§8.9) |
| Hablar con una persona | Siempre visible; equivale a `pedir_persona` | Evento del canal |
| Aviso de espera | Elemento de interfaz, no mensaje: número de caso, posición y tiempo estimado reales, o la hora del próximo turno; si la espera superó la estimación inicial, lo dice; en el nivel 3, un botón para seguir en español. Es lo único que ve el cliente sin modelo hasta que escribe la persona | A14 (`PROCESOS.md` §P2.5, §P2.6) |

**Canal:** al abrir, se elige "App del banco" (sesión ya iniciada, simulada con el servicio de identidad; el chat
hereda el token) o "Sitio web, sin sesión" (formulario seguro). La asistente se presenta como Lora solo en el primer
mensaje (texto legal `LITERAL`), después del saludo que escribe el Redactor.

**Estados:** sin sesión (solo información pública y el formulario, que reaparece mientras falte la identidad); sesión vencida (vuelve el formulario y se pide
de nuevo la confirmación pendiente); conexión cortada (al volver, recupera la conversación desde la base; un mensaje
reenviado no se procesa dos veces); sin modelo (traspaso y aviso de espera con la posición real; ninguna frase).

---

## 2. Vista en vivo (demo, video y jurado)

Solo la ve el rol observador (auditoría y, en la demo, el jurado), con datos sintéticos: muestra la señal de riesgo y los números de
la política, que nunca ve el cliente. **No inventa nada:** pinta el `RegistroTurno` de cada turno (CONTRATOS A13), el
mismo que usa la auditoría.

```
┌─ Modo: [En vivo] [Personajes ▾] [Paso a paso: caso C1 ▾] ─────────────────────────────┐
├─ Chat ─────────────────────────┬─ Por dentro · turno 3 de 7 ─────────────────────────┤
│ C: me robaron la tarjeta       │ 1 Filtro sensible  nada borrado                  ✓ │
│ A: Lamento lo ocurrido. ¿Blo-  │ 2 Interpretación   iniciar(tarjetas.bloquear)       │
│    queo tu tarjeta •••• 1234   │                    señal: producto_en_manos_de_otro │
│    ahora?                      │ 3 Candidatos       1 producto                    ✓ │
│ C: sí                          │ 4 Política         1✓ 2✓ 3✓ 4✓ → permitido          │
│                                │ 5 Herramienta      bloquear_producto · 212 ms    ✓ │
│                                │ 6 Verificación     releído: bloqueado            ✓ │
│                                │ 7 Redacción        verificador de marcadores     ✓ │
│                                │ 8 Siguiente        traspaso · fraude · prioridad 1  │
│                                ├─────────────────────────────────────────────────────┤
│                                │ Esperado (verdad de referencia) = obtenido       ✓ │
│ [◀ anterior]  [siguiente ▶]    │ Costo del turno · latencia · versiones             │
└────────────────────────────────┴─────────────────────────────────────────────────────┘
```

| Modo | Qué hace | De dónde sale |
|---|---|---|
| **En vivo** | El jurado conversa y el panel se llena turno a turno | `RegistroTurno` por turno (`GET /traza/{conversacion}`) |
| **Personajes** | Homero, Marge, Abe, Burns, Bart o Lisa conversan solos con el sistema (modelo de otra familia, E1). Solo en local y en el video: desplegada, la vista arranca en "paso a paso" | Igual, más el guion del personaje |
| **Paso a paso** | Se elige un caso de `CASOS.md` y se reproduce una corrida ya grabada, paso por paso, con lo esperado frente a lo obtenido en verde o rojo | Corridas guardadas de la evaluación (`evaluacion`), no gasta cupo |

Cada paso del panel corresponde a un componente (`ARQUITECTURA.md` §5.1): A17, A1, A3, A4, herramientas, A7, A8 y A9,
y el camino siguiente. Si un paso no corrió en ese turno, aparece como "no aplica", nunca como éxito.

---

## 3. App de operación

### 3.1 Asesor

```
┌─ Asesor E30142 · fraude · es, pt ─────────── Canal: [Chat ▾] Capacidad: [2 ▾] [● Disponible] ┐
├─ Mi cola ──────────────────┬─ Caso #R-0142 · fraude · prioridad 1 · hito 01:12 ──────────────┤
│ ● #R-0142  P1  01:12  es   │ Solicitud: robo de tarjeta; bloqueo hecho y verificado          │
│ ○ #R-0139  P4  12:40  pt   │ Hechos verificados · Acciones hechas · Preguntas abiertas       │
│                            │ Evidencia (solo asesor): señal, verificaciones de la política   │
│                            │ Adjuntos: comprobante.pdf  [ver]                                │
│                            ├─ Conversación (el cliente, como cita) ──────────────────────────┤
│                            │ ...                                                             │
│                            ├─ Guía del caso ─────────────┬─ Artículos sugeridos ─────────────┤
│                            │ 1 Revisar movimientos desde │ interno.robo-o-perdida-bloquear.. │
│                            │   la fecha del robo         │ publico.robo-o-perdida-de-tarjeta │
│                            │ 2 Ofrecer reclamos          │ [Buscar en la base...]            │
│                            ├─────────────────────────────┴───────────────────────────────────┤
│                            │ [Sugerir respuesta]  [ Escribir...                    ] [Enviar] │
│                            │ [Pedir info] [Transferir con nota] [Resolver] [Devolver] [Marcar artículo] │
└────────────────────────────┴─────────────────────────────────────────────────────────────────┘
```

| Elemento | De dónde sale | Regla |
|---|---|---|
| Cola | Trabajos asignados y cola enmascarada de sus habilidades | RLS de `app_asesor`; `PROCESOS.md` §P2.4 |
| Caso | `PaqueteTraspaso`, conversación, adjuntos | Sin enmascarar solo si está asignado; cada vista queda en `accesos_pii` |
| Guía y artículos | A16 y A15 | La guía la calcula el código |
| Sugerir respuesta | A16 a pedido | Nunca se envía sola; el mensaje enviado registra su origen |
| Acciones | Según rol y habilidad (`ROLES_Y_ACCESOS.md` §3) | Botón oculto si el rol no puede; la API lo niega igual |
| Adjuntos | `GET /equipo/caso/{id}/adjunto/{adjunto}` | Solo el caso asignado; cada vista queda en `accesos_pii`; el audio no se guarda |
| Buscar en la base | `GET /equipo/conocimiento` (A15) | Artículos internos y públicos |

Acciones: tomar, sugerir respuesta, enviar, transferir con nota a la habilidad elegida, resolver, devolver al
asistente (la conversación vuelve a él con el estado limpio), desbloquear tras riesgo (solo `fraude`), ver adjuntos,
buscar en la base de conocimiento y marcar un artículo como incorrecto o incompleto, con el caso de ejemplo
(`POST /equipo/conocimiento/{articulo}/marca`).

**Reclamos por investigar** (back-office, `PROCESOS.md` §P3), en la misma pantalla: la cola de su habilidad sin datos
del cliente, cuántos están por vencer y "Tomar el siguiente" (`GET /equipo/reclamos`, `POST /equipo/reclamos/siguiente`).
El reclamo tomado muestra el movimiento, la evidencia (solo para el asesor), las notas, la historia y el plazo con los
días hábiles que quedan, y permite corregir el tipo, pedir información al cliente, decidir (una negativa exige
explicación y documentos), registrar la referencia del abono y cerrar.

### 3.2 Supervisor

```
┌─ Supervisor · todas las colas ──────────────────────────────────────── [⚠ Sin modelo: no] ┐
│ Habilidad/idioma   En cola  🟢  🟡  🔴   Asesores conectados   Espera estimada            │
│ fraude · es           3      2   1   0          6                   2 min                 │
│ fraude · pt           1      0   0   1          0  → nivel 3        abre 06:00            │
│ reclamos · es         7      5   2   0          9                   6 min                 │
├─ Eventos ───────────────────────────────────────────────────────────────────────────────┤
│ 10:42 #R-0151 desborde a nivel 2 · 10:40 E81176 aceptación vencida → ausente           │
└─ [Reasignar] [Cambiar presencia de un asesor] [Reabrir reclamo] ────────────────────────┘
```

Datos (`GET /supervisor/indicadores`): colas de A14 siempre enmascaradas, con asesores conectados y espera
estimada calculada con la misma fórmula que ve el cliente; alarma roja si alguna conversación quedó sin modelo en los
últimos 15 minutos (`PROCESOS.md` §P8); eventos de traspaso; e indicadores de la operación del periodo elegido,
calculados del `RegistroTurno` (A13) con las definiciones del reporte de evaluación: conversaciones, resueltas por el
asistente (acción verificada y sin persona), pasaron a una persona, sin modelo, traspasos por habilidad, acciones
verificadas, señales de riesgo, latencia p50/p95, tokens y equivalente en USD por conversación y por resolución. Las
conversaciones de la evaluación se excluyen salvo que se pidan. Desenmascarar un caso exige motivo y queda auditado.
También: el resumen de la investigación en back-office (en cola y por vencer); **acciones del supervisor** con el
número que ve en pantalla (reasignar un caso T-… a un asesor que hable su idioma, con nota; reabrir un reclamo R-…, con
motivo; cambiar la presencia de un asesor); y los **parámetros de operación** (`PROCESOS.md` §P9), con su valor
vigente, de dónde sale y un campo para cambiarlo con motivo.

**Auditar una conversación** (`GET /supervisor/auditoria/{T-…|R-…|conversación}`): una línea de tiempo con cada
hecho de la conversación: lo que escribió el cliente, cada paso de cada componente con su latencia, la decisión de
la política, cada llamada al modelo (componente, modelo, hash del prompt, id del proveedor, tokens, espera de cupo),
cada acción con su relectura, cada evento del caso humano (asignación, sugerencia de IA pedida, transferencia,
cierre, aceptación vencida), cada mensaje del asesor con su origen y cada acceso a datos personales. Las fallas
quedan marcadas. El acceso a la auditoría también queda registrado.

### 3.3 Observador (auditoría y jurado)

La vista del supervisor en solo lectura, siempre enmascarada y sin los eventos de casos, más el acceso a la vista en
vivo (§2). No tiene botones de acción.

---

## 4. Sistema (la cabina)

Ruta `/sistema`, con el rol observador o supervisor; se actualiza sola. Compone, sin recalcular, lo que responde
`GET /sistema`: si el sistema está sano; el estado del pool de llaves (NOMINAL, DEGRADADO, SATURADO o SIN_LLAVES) con
cada llave por el nombre de su variable (nunca un fragmento del valor), sus peticiones del día y sus tokens del minuto; el gasto de IA a precio de
lista por modelo, componente y llave; los fallos por componente y motivo; la operación (conversaciones, resueltas,
pasaron a una persona, latencia); los parámetros de operación con su valor vigente y, para el presupuesto, cuántas
conversaciones llegaron al tope; y "necesita atención", con los avisos por severidad (crítica, advertencia,
informativa). Lo que hacen las pruebas automáticas y la evaluación no cuenta como operación. Cuando una llamada falla,
la pantalla dice la razón real (sin conexión, o el error y la referencia del incidente), nunca "no responde" si la API
respondió.
