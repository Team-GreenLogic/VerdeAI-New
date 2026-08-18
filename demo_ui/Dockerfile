# demo_ui/Dockerfile — Development image with Vite hot-reload
FROM node:20-alpine

WORKDIR /app

# Install dependencies first (layer cache)
COPY package.json package-lock.json* ./
RUN npm install

# Copy source (overridden by bind-mount in docker-compose.override.yml)
COPY . .

EXPOSE 5173

# Vite must bind to 0.0.0.0 inside Docker so the host can reach it
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]
