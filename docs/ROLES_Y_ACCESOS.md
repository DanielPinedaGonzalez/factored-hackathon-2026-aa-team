# ROLES Y ACCESOS — quién es quién, qué ve, qué hace y cómo entra

**Diseño de arquitectura:** Daniel Pineda González  
**Qué responde:** quién es quién, qué ve, qué hace, cómo entra y quién aprueba cada cambio. Es la fuente única de los
roles: `MODELO_DATOS.md` §4 los implementa en la base, `SEGURIDAD.md` dice cómo se protegen y `PROCESOS.md` en qué
momento actúa cada uno.

## 1. Los roles

Tres familias: quien pide atención, quien la da (el **cliente interno**) y quien gobierna el sistema.

| Rol | Familia | Quién es | Dónde actúa |
|---|---|---|---|
| **Visitante** | Pide atención | Cualquier persona sin autenticar | Chat del cliente |
| **Cliente** | Pide atención | Titular autenticado. Segmentos: Basic, Plus, Premium, Student | Chat del cliente |
| **Asistente** | Sistema | El propio sistema: actúa solo por encargo del cliente autenticado | API |
| **Asesor** | Cliente interno | Persona del centro de contacto, con **habilidades** (§2) | App de operación |
| **Supervisor** | Cliente interno | Responde por una cola y por sus tiempos comprometidos | App de operación |
| **Observador** | Gobierno | Auditoría, cumplimiento y el jurado en la demo: mira y no toca | App de operación, solo lectura |
| **Responsable de contenido y política** | Gobierno | Mantiene la base de conocimiento, la política por país y la configuración de atención | Repositorio (cambios revisados), nunca la app |
| **Pipeline** | Sistema | Carga los datos del banco y los artefactos | Fuera de línea |

**El cliente Premium no es un rol.** Es un atributo del cliente (`customers.segment`) con un solo efecto: el orden de
espera en la cola humana (`PROCESOS.md` §P2). Tiene los mismos permisos que cualquier cliente y la **misma política**:
el motor de política nunca recibe el segmento (`CONTRATOS.md` A4), porque "mismo caso, mismo trato" es una de sus
cuatro verificaciones (`ARQUITECTURA.md` §8.3). Las diferencias por segmento se miden y se reportan (`02_PLAN.md`
§8).

## 2. El asesor: habilidades, no roles distintos

Un asesor de fraude y uno de reclamos tienen el **mismo rol** y los mismos permisos básicos. Lo que cambia es qué
casos les llegan y dos acciones reservadas. Es el modelo de enrutamiento por habilidades de los centros de contacto:
en Nubank, por ejemplo, cada asesor tiene "insignias" por lo que sabe resolver (Nubank, s. f.-a).

| Atributo | Valores | Sale de (`service_agents`) |
|---|---|---|
| Habilidad | `fraude` (Fraudes), `reclamos` (Quejas y Reclamos), `general` (sin especialidad). Las demás especialidades no atienden este flujo | `specialty` |
| Idiomas | es, pt | `languages` (el inglés no se usa) |
| Canal | Solo `Digital` e `Hybrid` atienden chat | `agent_type` |
| Turno | mañana, tarde, noche, rotativo | `work_shift` |
| País | MX, CO, AR (define la zona horaria del turno) | `country_of_origin` |
| Estado laboral | Solo `Active` entra a la demo | `agent_status` |
| Capacidad | Chats simultáneos, 1 a 3; la elige el asesor al conectarse (§P2) | Configuración de atención |

Los datos personales del asesor (nombre, correo, teléfono) **no se cargan**. En la app, el asesor se ve con su
código de empleado (`employee_code`).

**Acciones reservadas por habilidad:**
- desbloquear un producto bloqueado por riesgo o con una señal de riesgo: solo `fraude`;
- confirmar el tipo de disputa `no_autorizada` o `estafa_autorizada`: solo `fraude`.

## 3. Matriz de permisos

✓ = puede · ✓c = puede, con confirmación explícita del cliente en la sesión · ◐ = con límites (nota) · — = no puede.

| Acción | Visitante | Cliente | Asistente | Asesor | Supervisor | Observador |
|---|---|---|---|---|---|---|
| Leer información pública (horarios, cómo reclamar) | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| Pedir una persona | ✓ (1) | ✓ | — | — | — | — |
| Ver sus transacciones, productos y reclamos | — | ✓ | ◐ (2) | ◐ (3) | ◐ (9) | — |
| Abrir, completar o retirar un reclamo | — | ✓c | ✓c (2) | ◐ (4) | — | — |
| Enviar un archivo como evidencia | — | ✓c | — | — | — | — |
| Ver los archivos de un caso | — | los suyos | — | ◐ (3) | ◐ (9) | — |
| Bloquear un producto | — | ✓c | ✓c (2) | ✓ (3) | — | — |
| Desbloquear un producto | — | ✓c (5) | ✓c (5) | ◐ (6) | — | — |
| Ver la cola | — | — | — | ◐ (7) | ✓ | ✓ enmascarada |
| Tomar un caso, responder, pedir información | — | — | — | ✓ (3) | — | — |
| Transferir con nota | — | — | — | ✓ | ✓ | — |
| Resolver el fondo, corregir el tipo de disputa | — | — | — | ✓ (3, 6) | — | — |
| Investigar un reclamo: tomar el siguiente, pedir información, corregir el tipo, decidir, registrar el abono y cerrar | — | — | — | ◐ (10) | — | — |
| Reabrir un reclamo cerrado | — | — | — | — | ✓ (con motivo) | — |
| Reasignar un caso o cambiar la presencia de un asesor | — | — | — | — | ✓ (con nota) | — |
| Cambiar un parámetro de operación | — | — | — | — | ✓ (con motivo) | — |
| Marcar un artículo como incorrecto o incompleto | — | — | — | ✓ | ✓ | — |
| Registrar una recomendación de abono | — | — | — | ✓ (8) | ✓ | — |
| Reasignar casos, cambiar el estado de un asesor | — | — | — | — | ✓ | — |
| Ver datos del caso sin enmascarar | — | sus datos | — | ◐ (3) | ◐ (9) | — |
| Buscar en la base de conocimiento interna | — | — | — | ✓ | ✓ | ✓ |
| Pedir una respuesta sugerida y ver la guía del caso | — | — | — | ✓ (3) | — | — |
| Leer auditoría y accesos a datos | — | — | — | — | sus colas | ✓ |
| Ver la vista en vivo (traza por turno con la señal de riesgo y la política; datos sintéticos, `INTERFACES.md` §2) | — | — | — | — | — | ✓ |

1. Sin sesión, el traspaso va marcado "identidad no verificada" y el asesor no ve datos de cuenta hasta autenticarlo.
2. Solo sobre el cliente del token (`INV-SUJETO`) y solo las acciones que la política permite en ese turno.
3. Solo en los casos **asignados a ese asesor** y mientras estén abiertos.
4. Abre un reclamo a pedido del cliente dentro de la conversación, agrega notas y cambia su estado (en revisión,
   esperando al cliente, resuelto). No lo retira: retirar es decisión del cliente.
5. Solo si lo bloqueó el propio cliente y no hay señal de riesgo acumulada (`MODELO_DATOS.md` §3.2).
6. Las acciones reservadas a la habilidad `fraude` (§2).
7. Solo la cola de sus habilidades e idiomas, con los casos en espera resumidos y enmascarados hasta tomarlos.
8. El abono **no** lo ejecuta el sistema: la recomendación queda en el reclamo y el back-office del banco la ejecuta
   fuera de él (`PROCESOS.md` §P3).
9. Con motivo obligatorio; queda en `operacion.accesos_pii`.
10. Solo asesores con habilidad `fraude` o `reclamos`, sobre reclamos de su habilidad, uno en revisión a la vez; la cola llega
    sin datos del cliente y, al tomarlo, ve lo necesario para investigarlo. Confirmar `no_autorizada` o `estafa_autorizada` es de
    `fraude` (§2).

**Vista enmascarada:** el cliente aparece con un alias; comercio, ciudad y monto ocultos; el paquete de traspaso sin
su sección de evidencia.

## 4. Cómo entra cada rol

| Rol | En la demo | En producción |
|---|---|---|
| Visitante | Sin credencial; límites por IP y por sesión | Igual |
| Cliente | Formulario seguro dentro del chat: documento + código de un solo uso en el buzón del sandbox → token firmado de 15 min con el `customer_id` (`ARQUITECTURA.md` §8.11) | El chat vive dentro de la app del banco y hereda su sesión |
| Asesor, supervisor, observador | Identidades de demo por código de empleado, detrás del código de acceso a la demo → token firmado de 8 h (un turno) con `rol`, código de asesor, habilidades e idiomas | Inicio de sesión único del banco (OIDC) con doble factor; rol y habilidades salen del directorio corporativo, no de la app |
| Responsable de contenido y política | No entra a la app: propone cambios por *pull request* en el repositorio | Igual, con revisión de cumplimiento |
| Pipeline | Credencial del rol de migraciones en `.env` o en los secretos de GitHub Actions | Cuenta de servicio |

El jurado entra con las identidades de demo de asesor, supervisor u observador; los datos son sintéticos. El código
de acceso a la demo no autoriza nada: cada endpoint exige su token y la base aplica RLS (`SEGURIDAD.md`).

## 5. Gobierno de los cambios

Nada que cambie el comportamiento del sistema entra sin dueño, revisión y prueba.

| Qué cambia | Propone | Aprueba | Qué debe pasar | Queda registrado en |
|---|---|---|---|---|
| Política por país (`politica/*.yaml`) | Responsable de política | Cumplimiento | Una prueba por regla; comparación con la verdad de referencia | `version_politica` en cada decisión |
| Umbral de bloqueo | Procedimiento LTT (nadie lo escribe a mano) | Responsable de modelos | Reporte por ventana (`02_PLAN.md` §2) | Artefacto versionado |
| Prompts y catálogo | Equipo técnico | Responsable técnico | Pruebas de contexto y evaluación de desarrollo | Hash en cada turno |
| Base de conocimiento | Asesor o responsable de contenido (§P7) | Responsable de contenido | Esquema del artículo; fuente citada | Versión del artículo en cada respuesta |
| Configuración de atención (hitos, capacidad, turnos, desborde) | Supervisor | Responsable de operación | Pruebas del enrutador | Versión en cada asignación |
| Parámetros de operación (`PROCESOS.md` §P9): presupuesto por conversación, días de espera al cliente | Supervisor, desde la operación | El mismo supervisor, con motivo y dentro del rango declarado | Rango de `config/parametros_operacion.yaml` | `operacion.parametro_eventos` |
| Plazos de retención | Responsable de datos | Cumplimiento | — | `config/retencion.yaml` y cada corrida en `operacion.purga_eventos` |
| Alta, baja o habilidad de un asesor | Supervisor | Responsable de operación | — | Evento del asesor |

**En la demo** una sola persona tiene todos estos sombreros. El proceso no cambia: *pull request*, pruebas y
versión registrada.

## 6. Figuras reguladas (producción; en la demo solo se declaran)

Cada país exige una figura propia de atención de reclamos, y el cliente puede acudir a ella si no queda conforme. El
sistema no la reemplaza: se lo dice al cliente (artículo público de la base de conocimiento, `ARQUITECTURA.md` §8.8).

| País | Figura | Norma |
|---|---|---|
| Colombia | Sistema de Atención al Consumidor Financiero (SAC) y Defensor del Consumidor Financiero; después, la Superintendencia Financiera | Ley 1328 de 2009 (Ley 1328, 2009; Superintendencia Financiera de Colombia, s. f.) |
| México | Unidad Especializada de Atención a Usuarios (UNE); después, CONDUSEF. El plazo para cargos no reconocidos está en `ARQUITECTURA.md` §8.3 | Ley de Protección y Defensa al Usuario de Servicios Financieros (CONDUSEF, 2021, s. f.-c) |
| Argentina | Responsable de atención al usuario de servicios financieros; después, el BCRA. Resolución en hasta 10 días hábiles | Texto ordenado *Protección de los Usuarios de Servicios Financieros* (BCRA, s. f.; BCRA Usuarios, s. f.) |

## Referencias

Completas, en formato APA 7, en `BIBLIOGRAFIA.md`.
