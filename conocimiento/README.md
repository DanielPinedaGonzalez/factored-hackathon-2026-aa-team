# Base de conocimiento

Un artículo por tema. Diseño y uso: `docs/ARQUITECTURA.md` §8.8; de dónde sale cada uno: `docs/CASOS.md` §4; cómo se
mejora: `docs/PROCESOS.md` §P7.

**Formato y gobierno:** `docs/GOBERNANZA_DATOS_IA.md` §11. Cabecera YAML con los datos obligatorios (§11.3); cuerpo
`## es` y `## pt` en los públicos, solo español en los internos; al final, la tabla `## Respaldo` con cada afirmación y
su cita (Autor, año) de `docs/BIBLIOGRAFIA.md`, que el Redactor no recibe. El bloque `datos` no guarda números: apunta
a la política o la configuración (`politica.…`, `config.…`), que siempre ganan.

**Son la política sintética del banco de la demo**, escrita desde fuentes públicas. No son asesoría legal. Todos están
en `pendiente_aprobacion` hasta que otra persona los apruebe; quien los escribe no los aprueba.

Este índice lo regenera `scripts/verificar_conocimiento.py`.

## Públicos (el cliente y el asistente)

| Id | Título | Protocolo | Criticidad | Estado |
|---|---|---|---|---|
| [`publico.bloqueo-y-desbloqueo`](publico/bloqueo-y-desbloqueo.md) | Bloqueo temporal y desbloqueo | PR-4 | alta | pendiente_aprobacion |
| [`publico.cambiar-o-recuperar-tu-clave`](publico/cambiar-o-recuperar-tu-clave.md) | Cambiar o recuperar tu clave | PR-1 | alta | pendiente_aprobacion |
| [`publico.como-funciona-un-reclamo`](publico/como-funciona-un-reclamo.md) | Cómo funciona un reclamo | PR-7, PR-9, PR-11 | media | pendiente_aprobacion |
| [`publico.como-te-identificamos`](publico/como-te-identificamos.md) | Cómo te identificamos | PR-2 | alta | pendiente_aprobacion |
| [`publico.consultar-completar-retirar-reclamo`](publico/consultar-completar-retirar-reclamo.md) | Consultar, completar o retirar un reclamo | PR-7 | media | pendiente_aprobacion |
| [`publico.hablar-con-una-persona`](publico/hablar-con-una-persona.md) | Hablar con una persona | Promesas P3 y P4 | media | pendiente_aprobacion |
| [`publico.nunca-te-pedimos-tu-clave`](publico/nunca-te-pedimos-tu-clave.md) | Nunca te pedimos tu clave ni los datos de tu tarjeta | PR-1, PR-3 | alta | pendiente_aprobacion |
| [`publico.otras-gestiones`](publico/otras-gestiones.md) | Otras gestiones: límite, reposición, datos | PR-5 | media | pendiente_aprobacion |
| [`publico.plazos-por-pais`](publico/plazos-por-pais.md) | Plazos por país | PR-7, PR-11 | alta | pendiente_aprobacion |
| [`publico.privacidad-y-uso-de-ia`](publico/privacidad-y-uso-de-ia.md) | Privacidad y uso de IA | Transparencia | media | pendiente_aprobacion |
| [`publico.que-hacer-ante-una-estafa`](publico/que-hacer-ante-una-estafa.md) | Qué hacer ante una estafa | PR-8, PR-1 | alta | pendiente_aprobacion |
| [`publico.que-pasa-con-mi-dinero`](publico/que-pasa-con-mi-dinero.md) | Qué pasa con mi dinero mientras se revisa | PR-7, PR-11 | alta | pendiente_aprobacion |
| [`publico.robo-o-perdida-de-tarjeta`](publico/robo-o-perdida-de-tarjeta.md) | Robo o pérdida de la tarjeta | PR-4, PR-1 | alta | pendiente_aprobacion |
| [`publico.si-llamas-por-otra-persona`](publico/si-llamas-por-otra-persona.md) | Si escribes por otra persona | PR-10 | media | pendiente_aprobacion |
| [`publico.si-no-quedas-conforme`](publico/si-no-quedas-conforme.md) | Si no quedas conforme | PR-12 | media | pendiente_aprobacion |

## Internos (asesores, supervisores y observadores)

| Id | Título | Protocolo | Criticidad | Estado |
|---|---|---|---|---|
| [`interno.autorizacion-de-terceros`](interno/autorizacion-de-terceros.md) | Autorización de terceros | PR-10 | media | pendiente_aprobacion |
| [`interno.clave-o-codigo-entregado`](interno/clave-o-codigo-entregado.md) | Clave o código entregado a un tercero | PR-1, PR-8 | alta | pendiente_aprobacion |
| [`interno.como-transferir-con-nota`](interno/como-transferir-con-nota.md) | Cómo transferir con nota | Promesa P2 | media | pendiente_aprobacion |
| [`interno.criterios-tipo-de-disputa`](interno/criterios-tipo-de-disputa.md) | Criterios de tipo de disputa | PR-7, PR-8, PR-9 | media | pendiente_aprobacion |
| [`interno.desbloqueo-tras-riesgo`](interno/desbloqueo-tras-riesgo.md) | Desbloqueo tras riesgo | PR-4 | alta | pendiente_aprobacion |
| [`interno.estafa-autorizada`](interno/estafa-autorizada.md) | Estafa autorizada: la persona es víctima | PR-8 | alta | pendiente_aprobacion |
| [`interno.investigacion-de-un-reclamo`](interno/investigacion-de-un-reclamo.md) | Investigación de un reclamo | PR-7, PR-11, PR-12 | media | pendiente_aprobacion |
| [`interno.lo-que-el-asesor-no-decide`](interno/lo-que-el-asesor-no-decide.md) | Lo que el asesor no decide en este flujo | PR-5 | media | pendiente_aprobacion |
| [`interno.recomendacion-de-abono`](interno/recomendacion-de-abono.md) | Recomendación de abono | PR-7, PR-11 | alta | pendiente_aprobacion |
| [`interno.robo-o-perdida-bloquear-primero`](interno/robo-o-perdida-bloquear-primero.md) | Robo o pérdida: bloquear primero | PR-4, PR-1 | alta | pendiente_aprobacion |
| [`interno.trato-a-clientes-vulnerables`](interno/trato-a-clientes-vulnerables.md) | Trato a clientes en situación vulnerable | PR-6 | media | pendiente_aprobacion |
| [`interno.verificar-identidad-sin-codigo`](interno/verificar-identidad-sin-codigo.md) | Verificar identidad sin código | PR-2 | alta | pendiente_aprobacion |
