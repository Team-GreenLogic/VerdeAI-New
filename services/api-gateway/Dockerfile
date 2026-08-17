FROM python:3.12-slim

# Install system deps (WeasyPrint needs pango/harfbuzz/gdk-pixbuf + fonts for PDF rendering)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz0b \
    libgdk-pixbuf-2.0-0 libffi8 shared-mime-info fonts-dejavu \
    && rm -rf /var/lib/apt/lists/*

# Make pip resilient to slow/flaky networks (longer read timeout + more retries)
ENV PIP_DEFAULT_TIMEOUT=120 \
    PIP_RETRIES=10

WORKDIR /app

# Install shared library first (cached layer)
COPY shared/ /app/shared/
RUN pip install --no-cache-dir -e /app/shared/

# Install service
COPY services/api-gateway/ /app/service/
RUN pip install --no-cache-dir -e /app/service/

WORKDIR /app/service

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
