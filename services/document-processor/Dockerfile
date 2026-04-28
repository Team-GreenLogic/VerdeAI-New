FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY shared/ /app/shared/
RUN pip install --no-cache-dir -e /app/shared/

COPY services/document-processor/ /app/service/
RUN pip install --no-cache-dir -e /app/service/

WORKDIR /app/service

CMD ["python", "-m", "app.main"]
