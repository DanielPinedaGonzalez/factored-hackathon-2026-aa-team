---
id: interno.recomendacion-de-abono
titulo: "Recomendación de abono"
version: 1
estado: pendiente_aprobacion
audiencia: interno
paises: [MX, CO, AR]
protocolo: PR-7, PR-11
criticidad: alta
autor: equipo (borrador asistido por IA)
aprobado_por: null
vigente_desde: null
revisar_antes_de: null
fuentes: [condusef_b]
casos: [F6]
datos:
  mx_horas_reporte_debito: politica.mx.abono_provisional_debito.horas_reporte
idioma: es (todos los asesores de la plantilla hablan español)
---


- **El sistema no mueve dinero.** Tú registras la recomendación en el reclamo; el back-office del banco la ejecuta.
- La recomendación lleva la base (regla del país o decisión del caso) y el monto.
- Cuando el back-office la ejecuta, registra **su referencia** en el reclamo. Solo con esa referencia se le comunica al
  cliente que el abono se hizo.
- Nunca le prometas al cliente un abono antes de que exista la referencia.
- En México, un abono provisional puede corresponder en tarjetas de débito reportadas dentro de las
  {mx_horas_reporte_debito} horas siguientes, solo si el banco no exigió dos factores de autenticación (dato que la demo
  no trae): confírmalo con la regla del país antes de recomendarlo.

## Respaldo

Para el asesor y el jurado; el Redactor no lo recibe.

| Afirmación | Fuente |
|---|---|
| México: tarjeta de débito reportada dentro de las 48 horas, abono a más tardar el segundo día hábil si el banco no exigió dos factores; reverso posible si se prueba la autorización | (CONDUSEF, s. f.-b) |
