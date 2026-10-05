# API (FastAPI) para Render: 512 MB, 0,1 CPU. Sin llaves ni datos del organizador en la imagen.
FROM python:3.12-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && pip uninstall -y pytest pyarrow duckdb scikit-learn || true
COPY contratos contratos
COPY servicio servicio
COPY politica politica
COPY config config
COPY prompts prompts
COPY conocimiento conocimiento
COPY artefactos artefactos
COPY evaluacion/identidades_demo.json evaluacion/ground_truth_cases.yaml evaluacion/
# las corridas grabadas llevan fragmentos de registros del organizador y no se publican: la carpeta queda vacía y /corridas devuelve []
RUN mkdir -p evaluacion/corridas
COPY apps apps
EXPOSE 8000
CMD ["sh", "-c", "uvicorn servicio.api.app:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1 --proxy-headers --forwarded-allow-ips='*'"]
