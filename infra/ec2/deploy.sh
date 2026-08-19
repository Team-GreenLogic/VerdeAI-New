#!/bin/bash
# Production deploy for VerdeAI on EC2 (release environment).
# Invoked by the wrapper at /opt/verdeai/deploy.sh after the repo has been
# synced to origin/release and .env has been refreshed from SSM.
set -euo pipefail

cd /opt/verdeai

COMPOSE_FILES="-f docker-compose.yml -f docker-compose.release.yml"

docker compose $COMPOSE_FILES build
docker compose $COMPOSE_FILES up -d --remove-orphans

# RabbitMQ imports its definitions from a bind-mounted file, so a plain
# `up -d` does not recreate it when only that file changes. Restart it if
# it is not running (e.g. it crashed on a bad definitions file).
if [ "$(docker inspect -f '{{.State.Running}}' verdeai-rabbitmq-1 2>/dev/null || echo false)" != "true" ]; then
  echo "rabbitmq not running - restarting"
  docker compose $COMPOSE_FILES restart rabbitmq
fi

docker image prune -f

