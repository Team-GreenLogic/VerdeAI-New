FROM python:3.12-slim

WORKDIR /app

COPY shared/ /app/shared/
RUN pip install --no-cache-dir -e /app/shared/

COPY services/gap-analyzer/ /app/service/
RUN pip install --no-cache-dir -e /app/service/

WORKDIR /app/service

CMD ["python", "-m", "app.main"]
