# EXPERIENCIA DEL CLIENTE — un sistema para el banco, diseñado desde quien reclama

**Diseño de arquitectura:** Daniel Pineda González  
**Qué responde:** qué le duele al cliente, qué se le promete y cómo vive el paso a una persona. Es el punto de partida
del diseño: el sistema es del banco (`VISION.md`), pero cada decisión se toma desde lo que vive el cliente, y los
demás planos implementan lo que aquí se promete.

## 1. Lo que le duele al cliente (con evidencia)

| Dolor | Evidencia |
|---|---|
| **El problema es masivo.** Un cargo que no reconoce es la queja bancaria número uno | Colombia, 2025: 2,76 millones de quejas contra bancos ante la Superintendencia Financiera; la primera causa, **39,8%, transacción no reconocida**; ~11% transacciones mal aplicadas (El Colombiano, 2026) |
| **El chatbot no reconoce la disputa** si no usa las palabras exactas | El regulador financiero de EE. UU. documenta que en chatbots y guiones "solo palabras o sintaxis específicas" disparan el reconocimiento de una disputa (§3.1.1) (CFPB, 2023) |
| **No puede llegar a una persona** a tiempo: el *doom loop* | Mismo informe, §3.2, "obstaculizar el acceso oportuno a la intervención humana": bucles de respuestas repetitivas sin salida a un humano (CFPB, 2023) |
| **Tiene que repetir su historia** cada vez que lo pasan | 74% de los consumidores se frustra al repetir su historia; 83% dice que tiene que repetir información al ser transferido desde la IA, mientras 96% de los responsables creen que el contexto se conserva (CRM Buyer, 2026; Contact Center Pipeline, 2025) |
| **El contexto se pierde entre canales** | Solo 13% de los centros de contacto encuestados pasa al cliente entre canales conservando el contexto (CRM Buyer, 2026; Contact Center Pipeline, 2025) |
| **"Aquí estoy para ti"… y silencio.** Promesas de atención que no se cumplen | Tiempos de espera largos o sin acceso a una persona, entre las quejas documentadas (CFPB, 2023) |
| **Un mal proceso de disputa cuesta el cliente** | ~17% de los tarjetahabientes reduce o deja de usar su tarjeta tras una disputa insatisfactoria (Mastercard, citado en [Chargebacks911, s. f.]) |
| **Sentirse acusado** cuando es la víctima | La mayoría de los "no reconocidos" son confusión o fraude real, no mala fe (diagnóstico §3.1). Tratarlo como sospechoso agrava el daño |

## 2. Las promesas del sistema al cliente

Cada promesa tiene cómo se cumple y cómo se mide. Si no se puede medir, no se promete.

| # | Promesa | Cómo se cumple | Cómo se mide |
|---|---|---|---|
| P0 | **Sabes que hablas con un asistente virtual** desde el primer mensaje, que una persona está a un pedido de distancia y que nunca te pediremos tu clave | Divulgación en el primer turno como texto legal `LITERAL`, la única excepción cerrada al texto redactado por el modelo (`GOBERNANZA_DATOS_IA.md` §7; `ARQUITECTURA.md` §8.4) | Caso: primer turno en ES y PT |
| P1 | **Te entiendo con tus palabras.** No tienes que decir "disputa" ni "contracargo" | La IA interpreta la conversación completa; no hay palabras clave (ARQUITECTURA §8.1, §8.2) | Casos de evaluación con redacciones variadas, torpes y en dos idiomas |
| P2 | **Nunca te hago repetir.** Lo que ya dijiste queda dicho, también si pasas a una persona o vuelves mañana | `datos_dados` en el estado; paquete de traspaso con hechos verificados; memoria de reclamos entre conversaciones | Métrica "veces que se pidió un dato ya dado" = 0 |
| P3 | **Siempre puedes hablar con una persona**, en cualquier momento, sin laberinto | `pedir_persona` en cualquier nodo; traspaso por estancamiento, no por agotamiento | Casos de "pedir persona" en todos los nodos |
| P4 | **Nunca te dejo en silencio sin decirte qué pasa.** Si no hay respuesta inmediata, te digo la verdad: qué sigue, quién lo tiene y cuándo | Estado del caso visible; avisos en cada cambio; plazos (hitos) con alarma interna antes de vencer (§3) | Tiempo máximo sin actualización |
| P5 | **Sabes en qué va tu caso**, siempre, sin llamar | `consultar_reclamo` en la conversación; número de caso real y releído | Casos de consulta de estado |
| P6 | **No te trato como sospechoso.** Te muestro los hechos y tú decides | El redactor no recibe señales de riesgo; el texto no imputa (ARQUITECTURA §8.3, verificación 4) | Juez auxiliar de tono + revisión de muestra |
| P7 | **Tu decisión cuenta.** Si quieres reclamar aunque el sistema crea que es una confusión, reclamas; si quieres bloquear tu tarjeta, la bloqueas | El cliente siempre puede abrir el reclamo y bloquear su producto; el sistema recomienda, no impone | Casos donde el cliente insiste |

## 3. Cómo funciona el paso a una persona (en la vida real, no en la demo)

En un banco, detrás del chat hay un **centro de contacto**: asesores con habilidades, colas, turnos y tiempos
comprometidos. Un sistema que "pasa a un humano" sin modelar eso es el que deja al cliente colgado. La mecánica
completa (quién es elegible, cómo se elige entre varios, prioridades, desborde, turnos y tiempo estimado) está en
`PROCESOS.md` §P2, y sigue la práctica estándar de los centros de contacto (Decagon, s. f.; Cisco, s. f.). Aquí, lo que el cliente vive:

**Le toca la persona que sabe de su caso y habla su idioma.** Un caso de engaño o de tarjeta robada va a un asesor de
fraude; un reclamo que la política no permite automatizar, a uno de reclamos. Si no hay nadie con esa habilidad, el
caso sube por niveles hasta alguien que pueda atenderlo, sin perder su lugar ni su contexto. **Nunca se le cambia el
idioma sin preguntarle.**

**Primero lo urgente, de verdad.** El orden de atención es: riesgo de seguridad en curso, cliente vulnerable, plazo
normativo cercano o mucho dinero en juego, y el resto. Dentro de cada nivel, un caso a punto de vencer no cede su lugar a nadie; después, a
igual urgencia, va el cliente Premium, y luego el orden de llegada. Un caso al que se le venció su tiempo sube de
nivel: nadie queda esperando para siempre (`PROCESOS.md` §P2.3).

**Traspaso "cálido", no "frío".**
- El asesor recibe el `PaqueteTraspaso`: qué pidió, hechos verificados, qué se hizo y qué falta. No le pregunta al
  cliente lo que ya está ahí.
- Si el asesor necesita pasarlo a otro, lo **transfiere con una nota**, y el siguiente recibe todo.
- Transferir en frío, sin contexto, no existe en el sistema.

**Lo que ve y vive el cliente mientras espera (la promesa P4, en concreto):**
- Al traspasar, el sistema le dice **la verdad calculada**:
  - si hay asesor disponible: que una persona del equipo va a continuar aquí mismo;
  - si hay cola: su posición y un tiempo estimado, calculado con la cola real, no inventado;
  - si no hay nadie en turno: cuándo empieza la atención y que su caso ya está registrado con el número X.
- **La conversación no se cierra.** El cliente puede irse y volver: la respuesta del asesor llega al mismo chat
  (atención asíncrona). Al volver, ve el estado de su caso.
- **Tiempos comprometidos (hitos):** primera respuesta de un asesor en minutos según la prioridad, y un seguimiento
  si el caso no avanza. Una alarma interna avisa **antes** de que venza, no después. Si un hito vence, el cliente
  recibe un aviso honesto y el supervisor lo ve en rojo.
- **Nunca "estoy aquí para ti" seguido de silencio:** el sistema solo promete lo que el estado de la cola permite
  cumplir.
- **Si el asistente virtual no está disponible,** una persona continúa la conversación y el chat muestra el aviso
  de espera con su posición real o la hora en que abre la atención. Nunca se queda "en visto" (`PROCESOS.md` §P8).
- **Si manda una foto o un documento** (un comprobante, el correo del comercio), el sistema lo recibe, lo agrega a su
  reclamo y le dice lo verificado: que quedó guardado y quién lo verá (el reclamo abierto o el caso que espera a una persona), nunca que alguien lo está mirando en ese momento. Nada de lo que envíe deja la conversación sin respuesta.

**En la demo** los asesores son un subconjunto real de la plantilla del banco sintético (`01_DIAGNOSTICO.md` §2.6),
sin sus datos personales, y el jurado puede entrar como asesor, supervisor u observador (`ROLES_Y_ACCESOS.md` §4).
**En producción**, el mismo modelo se conectaría con la plataforma de centro de contacto del banco: la cola, los
asesores y los hitos son las mismas entidades.

## 4. El recorrido del cliente, de punta a punta

1. **Escribe como habla:** "me salió un cobro raro de 180 lucas ayer".
2. **Ya está identificado:** escribe desde la app del banco, con su sesión iniciada. Si escribe desde el sitio web
   sin sesión, se identifica en un formulario seguro dentro del chat, con un código que le llega a su canal
   registrado; nunca se le pide la clave. Si escribe el número de su tarjeta, el sistema lo borra y se lo dice.
3. **Ve el movimiento real:** qué es (una compra, un retiro, una transferencia), el comercio y la ciudad si los tiene,
   la fecha, la hora y el monto. Si hay varios parecidos, elige entre las opciones reales.
4. **Decide:**
   - si lo reconoce, se cierra, y aun así puede reclamar;
   - si no lo reconoce, se le propone abrir el reclamo y, si hace falta, bloquear la tarjeta.

   Nada se hace sin su confirmación.
5. **Recibe el número de caso real y el plazo,** releídos de la base.
6. **Si el caso necesita una persona,** sabe quién, cuándo y cómo le van a responder. No repite nada.
7. **Vuelve cuando quiera:**
   - consulta el estado;
   - agrega información;
   - o retira el reclamo.

## 5. Métricas del lado del cliente (además de las del reto)

- Tiempo hasta la primera respuesta útil.
- Veces que se le pidió un dato ya dado (objetivo: 0).
- Tiempo máximo sin actualización mientras espera.
- Traspasos con contexto completo (objetivo: 100%).
- Conversaciones donde pidió una persona y no la obtuvo (objetivo: 0).

## Referencias

Completas, en formato APA 7, en `BIBLIOGRAFIA.md`.
