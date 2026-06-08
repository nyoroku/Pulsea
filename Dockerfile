FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["sh", "-c", "case \"${PULSEA_PROCESS:-web}\" in web) python manage.py migrate --noinput && python manage.py ensure_operator && python manage.py collectstatic --noinput && gunicorn config.wsgi:application --bind 0.0.0.0:${PORT:-8000} ;; worker) celery -A config worker --loglevel=INFO --concurrency=${CELERY_WORKER_CONCURRENCY:-2} ;; beat) celery -A config beat --loglevel=INFO --schedule=/tmp/celerybeat-schedule ;; *) echo \"Unknown PULSEA_PROCESS: ${PULSEA_PROCESS}\" >&2; exit 1 ;; esac"]
