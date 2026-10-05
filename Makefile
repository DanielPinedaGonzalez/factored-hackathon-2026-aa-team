# Desarrollo local (docs/DESPLIEGUE.md §2). Python del entorno virtual del proyecto.
PY := .venv/bin/python

base:            ## Postgres 16 propio en el puerto 5433
	docker compose up -d db

migrar:          ## aplica las migraciones pendientes
	$(PY) scripts/migrar.py

datos:           ## bronce → plata → selección con semilla → carga del subconjunto y de los artículos
	$(PY) -m pipeline.plata
	$(PY) -m pipeline.seleccion
	$(PY) -m pipeline.dinero_en_juego
	$(PY) -m pipeline.oro
	$(PY) scripts/perfiles_demo.py      # los rasgos de cada cliente de demostración, de los datos cargados
	$(PY) scripts/cargar_conocimiento.py

m1:              ## calibración y umbral certificado de M1
	$(PY) -m ml.m1_ltt
	$(PY) -m ml.metricas_m1
	$(PY) -m ml.deriva

PRUEBAS_ADMIN := postgresql://aa_admin:aa_admin_local@127.0.0.1:5433/aa_team_pruebas

base-pruebas:    ## (re)crea la base de las pruebas como copia de la de la demo (con la API detenida: la copia pide la base sin conexiones)
	docker exec aa-team-db dropdb -U aa_admin --if-exists aa_team_pruebas
	docker exec aa-team-db createdb -U aa_admin -T aa_team aa_team_pruebas

test:            ## la suite completa en su propia base (nunca en la de la demo); antes, sus migraciones pendientes
	DATABASE_URL_ADMIN=$(PRUEBAS_ADMIN) $(PY) scripts/migrar.py
	$(PY) -m pytest -q

api:             ## API y las tres interfaces en http://127.0.0.1:8020/app/, con las llaves de .env (modelo real por defecto)
	set -a; . ./.env; set +a; LIMITE_IP_MINUTO=$${LIMITE_IP_MINUTO:-300} MODELO_MODO=$${MODELO_MODO:-groq} CONOCIMIENTO_INCLUIR_PENDIENTES=1 .venv/bin/uvicorn servicio.api.app:app --host 127.0.0.1 --port 8020

evaluar:         ## casos canónicos de desarrollo con el modelo real, espaciados por el guardián de cupo
	$(PY) -m evaluacion.corredor --conjunto desarrollo --modelo groq

.PHONY: base base-pruebas migrar datos m1 test api evaluar
