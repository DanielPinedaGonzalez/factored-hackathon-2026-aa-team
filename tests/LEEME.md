# Catálogo de pruebas

Una sola suite (`pytest tests`, 281 pruebas el 5-oct-2026), organizada **por componente, espejo de `servicio/`**, más tres familias transversales. Cada requisito del reto se traza a su prueba en `docs/00_MAPA_SISTEMA.md` (T1 a T34).

| Carpeta | Qué comprueba |
|---|---|
| `orquestador/` | El grafo de la conversación de punta a punta (nodos N0 a N14), con el modelo simulado: caminos, límites honestos, últimos movimientos, score alto |
| `interprete/` | Que la salida del Intérprete se lee y se valida contra el catálogo cerrado (el lector tolera descuidos de formato, no inventa) |
| `redactor/` | El Redactor y su verificador: marcadores, cifras, idioma, acciones |
| `resolutor/` | Encontrar el cargo real: fechas, montos, candidatos |
| `politica/` | Las cuatro verificaciones y las reglas por país; incluye la prueba exhaustiva de 98.304 combinaciones |
| `riesgo/`, `ml/` | La señal M1: calibración, umbral certificado, deriva |
| `enrutador/`, `traspaso/` | Asignación por habilidad, idioma y prioridad; el paquete del traspaso |
| `api/`, `canal/` | Los endpoints, la identidad y los canales (web sin sesión y app) |
| `seguridad/` | Inyección, secretos, aislamiento por cliente (RLS), eventos de seguridad |
| `llm/`, `recursos/` | El pool de llaves, el cupo, el guardián, el presupuesto de tokens |
| `conocimiento/`, `registro/`, `pipeline/`, `contratos/`, `evaluacion/` | Artículos, trazas y cabina, datos, contratos y las métricas de la evaluación |
| **`candados/`** | **Reglas del proyecto hechas pruebas:** sin texto al cliente ni listas de palabras en `.py`, el umbral sin escribir a mano, la interfaz traducida, el chat sin errores de JavaScript, la película y las diapositivas |

## Marcadores y cómo correr
- `-m "not db"`: sin base de datos (lógica pura, candados). Las demás necesitan Postgres local: `docker start aa-team-db` (usan la base `aa_team_pruebas`, nunca la de la demo).
- `-m llm_real`: llama a un proveedor real; **nunca** en la suite normal (gasta cupo).
- `make test` corre todo en su propia base. En GitHub corre `pruebas.yml` (sin base de la demo ni datos del organizador).

## Lo que no está aquí
La **evaluación de 62 casos con el modelo real** no es parte de `pytest`: la corre `evaluacion/` (verdad de referencia, línea base, intervalos) y se reporta en `docs/REPORTE_EVALUACION.md`. Las pruebas de aquí comprueban el código con un modelo simulado; la evaluación mide cómo se porta el sistema con el modelo real.

## Cómo agregar una prueba
En la carpeta del componente que cambia. Un fallo reportado en la demo se reproduce primero (privado: `privado/HALLAZGOS_PRUEBAS.md`) y se fija con una prueba que cubra **la causa y sus variantes**, no solo el texto que falló.
