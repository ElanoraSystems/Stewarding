FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /srv

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN chmod +x docker-entrypoint.sh \
    && useradd --system --uid 10001 app \
    && mkdir -p /data/uploads \
    && chown -R app /data /srv

USER app
ENV STW_UPLOAD_DIR=/data/uploads
EXPOSE 8000
ENTRYPOINT ["./docker-entrypoint.sh"]
