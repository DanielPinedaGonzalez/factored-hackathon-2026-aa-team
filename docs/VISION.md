# VISIÓN — qué es, para quién y qué problema del banco resuelve

**Diseño de arquitectura:** Daniel Pineda González  
**Qué responde:** qué es el sistema, para quién y qué problema del banco resuelve. Los demás planos la desarrollan.

## Qué es

Un **sistema de atención para un banco**, en español y portugués, que recibe al cliente que no reconoce un movimiento
de su cuenta y lleva el caso de punta a punta:
- lo autentica;
- encuentra el movimiento en sus datos reales, aunque lo describa con sus palabras;
- le muestra los hechos para que decida;
- abre el reclamo o bloquea el producto solo con su confirmación, y verifica que quedó hecho;
- y cuando el caso necesita una persona, lo entrega al asesor adecuado con todo lo verificado, sin que el cliente
  repita nada.

No es un chatbot que conversa: es un **proceso de atención** con una parte asistida por IA (la IA entiende y redacta;
el código decide y ejecuta) y una parte humana (asesores, supervisores), conectadas por el mismo caso.

## Para quién

| Quién | Qué es para esa persona |
|---|---|
| **El banco** (lo opera y responde por él) | Un canal que atiende el motivo de queja más caro sin perder control: cada acción queda con su regla, su evidencia y su autor |
| **El cliente** (Basic, Plus, Premium, Student) | Poder reclamar con sus palabras, a cualquier hora, sin laberinto y sin repetir su historia (`EXPERIENCIA_CLIENTE.md`) |
| **El asesor** (el cliente interno) | Recibir casos de su especialidad y su idioma, completos, con la guía del caso, la base de conocimiento y una respuesta sugerida a mano, y no volver a preguntar lo ya dicho |
| **El supervisor** | Ver la cola, los tiempos comprometidos y los casos en riesgo antes de que venzan, y reasignar |
| **Cumplimiento y auditoría** | Poder reconstruir cualquier decisión desde reglas y registros, no desde lo que "pensó" el modelo |

Roles y permisos exactos: `ROLES_Y_ACCESOS.md`.

## Qué problema del banco resuelve (con evidencia)

- **Es la queja número uno de la banca.** En Colombia, en 2025, el 39,8% de las quejas contra bancos fue por
  transacción no reconocida (`EXPERIENCIA_CLIENTE.md` [El Colombiano, 2026]).
- **Es el motivo peor resuelto en los datos del reto:** las quejas se resuelven el 44% de las veces, con 63% de
  seguimiento y 431 s por llamada, frente al 92% de las transaccionales (`01_DIAGNOSTICO.md` §2.2).
- **En los datos, la prioridad no cambia el tiempo de respuesta** y un tercio de las quejas no tiene asesor asignado
  (`01_DIAGNOSTICO.md` §2.6). Puede ser un efecto del generador sintético, así que no se afirma que el banco enrute
  mal: se dice que los datos no muestran ningún enrutamiento por habilidad. El diseño hace que la prioridad, la
  especialidad y el idioma decidan de verdad quién atiende y cuándo (`PROCESOS.md` §P2).

## Cómo se ve cuando funciona

1. El cliente escribe como habla y en minutos tiene su **número de caso real** y su plazo.
2. Si el caso lo puede cerrar el sistema de forma segura, lo cierra; si no, **no lo intenta**.
3. El asesor recibe el caso **listo para decidir**: solicitud, hechos verificados, acciones hechas y preguntas
   abiertas.
4. Nadie queda en silencio: el cliente sabe siempre qué sigue, quién lo tiene y cuándo.

La referencia de industria es la de los bancos digitales que publican cómo operan. Nubank, por ejemplo, enruta por
habilidades de sus asesores ("insignias"), reparte unos 60.000 casos al día en cerca de 200 colas y les da a sus
asesores una sola pantalla con los datos y las acciones del cliente (Nubank, s. f.-a, s. f.-b).

## Qué no hace

- No resuelve el fondo del reclamo ni mueve dinero: abonos y reembolsos los decide una persona.
- No reemplaza al centro de contacto: lo alimenta con casos completos y bien enrutados.
- No decide fraude ni trata al cliente como sospechoso.
- No es asesoría legal: la política por país es sintética fuera de lo verificado (`ARQUITECTURA.md` §8.3).

## Cómo se mide

Resolución automática segura, calidad de las escaladas, resultados inseguros con denominador, latencia y costo, por
idioma y por segmento (`02_PLAN.md` §4). Cualquier ahorro para el banco se presenta como **proyección**, separada de
lo medido; nunca como mejora observada en producción.

## Referencias

Completas, en formato APA 7, en `BIBLIOGRAFIA.md`.
