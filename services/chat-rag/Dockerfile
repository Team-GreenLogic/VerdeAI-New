FROM python:3.12-slim

WORKDIR /app

COPY shared/ /app/shared/
RUN pip install --no-cache-dir -e /app/shared/

COPY services/chat-rag/ /app/service/
RUN pip install --no-cache-dir -e /app/service/

WORKDIR /app/service

EXPOSE 8001

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8001"]
