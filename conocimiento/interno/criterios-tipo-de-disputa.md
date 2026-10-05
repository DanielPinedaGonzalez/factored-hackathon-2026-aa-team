---
id: interno.criterios-tipo-de-disputa
titulo: "Criterios de tipo de disputa"
version: 1
estado: pendiente_aprobacion
audiencia: interno
paises: [MX, CO, AR]
protocolo: PR-7, PR-8, PR-9
criticidad: media
autor: equipo (borrador asistido por IA)
aprobado_por: null
vigente_desde: null
revisar_antes_de: null
fuentes: [chargebackio, skadden2024, stripe]
casos: [A1, C4]
idioma: es (todos los asesores de la plantilla hablan español)
---


El tipo de disputa lo **propone** el asistente con la frase del cliente; el asesor lo **confirma o corrige**. Solo la
habilidad `fraude` confirma `no_autorizada` y `estafa_autorizada`.

| Tipo | Familia de las redes | Cómo se reconoce | Qué no hacer |
|---|---|---|---|
| `no_autorizada` | Fraude (10.x) | El cliente no hizo la compra: tarjeta robada, datos filtrados | Pedirle que "demuestre" que no fue él |
| `error_procesamiento` | Procesamiento (12.x) | Cargo duplicado, monto o moneda distintos, reverso que no llegó | Tratarlo como fraude |
| `consumo` | Consumo (13.x) | La compra existió, pero no llegó, llegó mal o era una suscripción cancelada | Saltarse el paso con el comercio cuando aplica |
| `autorizacion` | Autorización (11.x) | Cobro sin autorización válida del emisor | — |
| `estafa_autorizada` | Fuera de contracargos | El cliente pagó engañado por un tercero | Decir "usted lo autorizó" |
| `reconocida` | — | Era una compra propia o de alguien de su casa | Cerrar sin ofrecer reclamar igual |

## Respaldo

Para el asesor y el jurado; el Redactor no lo recibe.

| Afirmación | Fuente |
|---|---|
| Las redes agrupan las disputas en fraude, autorización, procesamiento y consumo | (Chargeback.io, s. f.; Stripe, s. f.) |
| La estafa de pago autorizado se trata aparte | (Skadden, 2024) |
