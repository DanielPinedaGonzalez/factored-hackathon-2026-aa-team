# DESPLIEGUE — cómo corre, cómo se sube, cómo se verifica y cómo se revierte

**Diseño de arquitectura:** Daniel Pineda González  
**Qué responde:** cómo corre, cómo se sube, cómo se verifica y cómo se revierte. Es la vista de despliegue de
`ARQUITECTURA.md` §7.

## 1. Dónde corre cada cosa

| Pieza | Desarrollo (tu máquina) | Producción (gratis) |
|---|---|---|
| Base | Contenedor `postgres:16` con la versión menor ≥ 16.15 fijada | Neon (0,5 GB, se suspende a los 5 min) |
| API (FastAPI) | `make api` (uvicorn local, carga las llaves de `.env`) | Render, servicio web Docker (512 MB, 0,1 CPU, se duerme a los 15 min) |
| Chat, vista en vivo, app de operación | la API los sirve en `/app` (`make api`) | Render, un sitio estático con tres rutas (no consume horas, no se duerme) |
| Pipeline de datos y modelos | Local, DuckDB | No se despliega: produce artefactos versionados (umbral, calibradores, subconjunto de demo) |
| Código | Repositorio local | GitHub, privado hasta la entrega |
| Integración | — | GitHub Actions (2.000 min/mes gratis en privado) |

GitHub Pages no se usa: en el plan gratuito solo publica desde repositorios públicos.

## 2. Desarrollo local

- `make base` levanta Postgres 16 en un contenedor propio (puerto 5433); `make api` levanta la API, que también sirve
  las interfaces en `/app`.
- `make migrar` aplica las migraciones pendientes; `make datos` construye plata desde bronce, elige con semilla el
  subconjunto de la demo y de los casos y lo carga; `make test` corre la suite en su propia base, `aa_team_pruebas`
  (`make base-pruebas` la crea como copia de la de la demo). Las pruebas preparan y limpian tablas enteras: en la base
  de la demo borrarían los casos en vivo, y un candado en `tests/conftest.py` impide que apunten a ella.
- **Memoria (3 GB):** Postgres y la API caben. Nunca dos construcciones pesadas a la vez; las transformaciones
  grandes, en DuckDB fuera de Docker.
- El modelo de lenguaje en desarrollo es, por defecto, el **puente de archivos**: el asistente de desarrollo hace
  de modelo, sin gastar cupo. Las llaves reales se usan solo para las pruebas que dependen del modelo.

## 3. Migraciones (fuente única: `migraciones/`)

- Archivos SQL numerados (`001_esquemas_y_roles.sql`, `002_servicio.sql`, …), aplicados en orden por
  `scripts/migrar.py`, que registra cada una con su checksum en `operacion.migraciones_aplicadas`. Una migración
  ya aplicada que cambió de contenido **aborta** el proceso.
- **Solo aditivas:**
  - se agrega una columna o tabla;
  - el código nuevo la usa;
  - lo viejo se retira en una migración posterior.

  Así, mientras corre una migración, el código anterior sigue funcionando.
- Roles, RLS (`ENABLE` + `FORCE`), `REVOKE DELETE` y funciones de transición de estado viven en migraciones, nunca
  a mano.
- Dos usuarios: el de **migraciones** (dueño del esquema; solo lo usa GitHub Actions o tu máquina) y el de
  **ejecución** (`NOSUPERUSER NOBYPASSRLS`, lo usa la API).

> **Clave del rol de ejecución.** La migración 001 crea `app_api` con la clave de desarrollo. En una base que no es local, `scripts/migrar.py` se niega a
> migrar sin `APP_API_PASSWORD` y, con ella, la fija al terminar. Es la misma clave que va en `DATABASE_URL` de la API (Render) y el secreto `APP_API_PASSWORD`
> de GitHub; una clave larga y aleatoria (`python -c "import secrets; print(secrets.token_urlsafe(32))"`).

> **Interruptor del despliegue.** `.github/workflows/pruebas.yml` corre en cada cambio (llaves, pruebas, auditoría de dependencias). El despliegue
> (`despliegue.yml`) solo corre si el repositorio tiene la variable `DESPLEGAR = true` o se lanza a mano (Actions → despliegue → Run workflow):
> así el primer `push`, antes de poner los secretos, no deja una ejecución fallida a la vista.
> Para activarlo: `gh variable set DESPLEGAR --body true`.

## 4. Subir a producción: un solo camino

`git push origin main`. GitHub Actions hace todo, en este orden, y se detiene en el primer fallo:

1. **Pruebas:**
   - `make test`;
   - candados: texto al cliente en `.py`, listas de palabras, el número del umbral escrito a mano;
   - escaneo de llaves.
2. **Punto de restauración:** crea en Neon una rama con la fecha y el commit (Neon guarda además 6 horas de
   historia para restaurar a cualquier instante). El plan gratuito admite 10 ramas por proyecto: se conservan las
   5 más recientes y la más vieja se borra antes de crear la nueva.
3. **Migraciones:** `scripts/migrar.py` contra Neon con el usuario de migraciones, **antes** de desplegar el código.
   Si fallan, producción sigue con el código anterior intacto.
4. **Desplegar la API:** llama el *deploy hook* de Render (el despliegue automático de Render, «On Commit», se activó el 5-oct para iterar rápido durante las pruebas: la API se despliega sola con cada push a `main`; en el camino con pruebas del flujo, estaba apagado para que
   nada suba sin pasar por 1-3). Render construye la imagen Docker.
5. **Verificar que corre el código nuevo** (el equivalente de comparar huellas dentro de los contenedores):
   - `GET /version` debe devolver el mismo commit que se subió (Render lo expone en `RENDER_GIT_COMMIT`);
   - `GET /health` debe mostrar base conectada, versión de PostgreSQL ≥ 16.15 (`INV-RLS`), rol sin BYPASSRLS,
     artefactos cargados con su hash y versión de política.

   Si no coincide en el tiempo límite, el paso falla y avisa.
6. **Desplegar las interfaces:** el sitio estático se construye en Render con la URL de la API de producción.
7. **Prueba de humo determinista** (sin gastar cupo del modelo):
   - autenticar una identidad de demo;
   - listar sus movimientos;
   - confirmar que otra identidad **no** los ve (RLS en producción).

**Después de cada despliegue, a mano:**
- una conversación real en el chat, vista en la vista en vivo;
- revisar el registro de turnos de los minutos siguientes. Un fallo silencioso puede pasar la prueba feliz.

**Mantenimiento semanal** (`.github/workflows/mantenimiento.yml`, los lunes y a pedido):
- vigilancia de las fuentes de la bibliografía (`scripts/vigilar_fuentes.py`, `GOBERNANZA_DATOS_IA.md` §11.6): sus
  huellas se guardan en el repositorio y, si una fuente cambió, ese commit pasa por el camino de arriba y la API deja de
  servir los artículos de criticidad alta que la citan hasta su revisión;
- purga por retención contra Neon con el usuario de migraciones (`scripts/purgar_retencion.py`, `MODELO_DATOS.md` §5).

## 5. Revertir

- **Código:** "Rollback" al despliegue anterior en el panel de Render, o `git revert` + push (vuelve a pasar por
  todo el camino).
- **Base:** como las migraciones son aditivas, el código anterior funciona con el esquema nuevo. Si un dato se dañó:
  restaurar desde la rama del punto 2, o a un instante de las últimas 6 horas.

## 6. Secretos

| Dónde | Qué |
|---|---|
| `.env` local (fuera de git) | Llaves de modelos, URLs de las bases locales |
| GitHub Actions → *Secrets* | URL de Neon con el usuario de migraciones, deploy hook de Render, clave de la API de Neon para crear ramas |
| Render → *Environment* | URL de Neon con el usuario de ejecución, llaves de modelos, secreto de firma de tokens, código de acceso a la demo, tope de gasto |

Ninguna llave en el código, en el Dockerfile ni en los logs. El gancho de pre-commit y el escaneo de Actions lo
bloquean.

## 7. Límites gratuitos y qué hacer

| Límite | Consecuencia | Qué se hace |
|---|---|---|
| Render se duerme a los 15 min | Primera visita ~1 min | Declarado en el README; ping externo solo durante la calificación, como comodidad |
| Render 750 h/mes por cuenta | Un solo servicio web 24/7 las consume | Una sola API; las interfaces como un sitio estático |
| Neon 0,5 GB | Subconjunto de demo | Se mide `pg_database_size` tras migrar; si pasa el 70%, no se despliega |
| Neon, 1 snapshot manual gratis y 10 ramas por proyecto | Sin rotación, el despliegue n.º 10 falla | Ramas como puntos de restauración, rotadas (se conservan 5) |
| Actions 2.000 min/mes en privado | Suficiente para ~100+ despliegues | Al hacerse público, sin límite |
| Cupo gratuito de los modelos | La demo puede quedarse sin modelo | Guardián de cupo que espacia las llamadas; un cliente espera hasta 15 s a que se libere una llave (`ESPERA_SATURADO_S`) antes de pasar a una persona (CONTRATOS A12, A11). Las llaves de la demo salen de `config/llaves.yaml` (papel `sistema`); un valor de relleno de menos de 20 caracteres no cuenta como llave |

## Referencias

Completas, en formato APA 7, en `BIBLIOGRAFIA.md`.


## Detrás del proxy de Render: la IP de cada visitante

Render entrega las peticiones por un proxy. Para que los límites por IP (`LIMITE_IP_MINUTO`, `max_desafios_por_ip`) cuenten a **cada visitante** y no a todos como uno solo, la API arranca con
`--proxy-headers --forwarded-allow-ips='*'` (Dockerfile): uvicorn toma la IP real de `X-Forwarded-For`. Es seguro mientras la API solo se alcance a través del proxy de la plataforma, que fija esa cabecera.
En la demo pública `LIMITE_IP_MINUTO` es 120 (`render.yaml`); en local, 300 (`make api`).
