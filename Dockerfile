FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1
ENV STATE_DB=/data/state.db

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt gunicorn

COPY . .

RUN useradd --create-home appuser \
    && mkdir -p /data \
    && chown -R appuser:appuser /app /data
USER appuser

CMD ["gunicorn", "--bind", "0.0.0.0:8080", "server:app"]
