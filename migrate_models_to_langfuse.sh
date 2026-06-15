#!/usr/bin/env bash
# Registers custom model pricing in the local Langfuse instance.
# Run from WSL: bash migrate_models_to_langfuse.sh

set -e

BASE="http://localhost:3000/api/public/models"
AUTH="Authorization: Basic $(echo -n 'pk-lf-local-verdeai:sk-lf-local-verdeai' | base64 -w0)"

register() {
  local name="$1"
  local pattern="$2"
  local input="$3"
  local output="$4"

  echo -n "Registering $name ... "
  RESPONSE=$(curl -s -o /tmp/lf_resp.json -w "%{http_code}" \
    -X POST "$BASE" \
    -H "$AUTH" \
    -H "Content-Type: application/json" \
    -d "{\"modelName\":\"$name\",\"matchPattern\":\"$pattern\",\"unit\":\"TOKENS\",\"inputPrice\":$input,\"outputPrice\":$output}")

  if [ "$RESPONSE" = "200" ] || [ "$RESPONSE" = "201" ]; then
    echo "OK ($RESPONSE)"
  elif [ "$RESPONSE" = "409" ]; then
    echo "already exists (409)"
  else
    echo "FAILED ($RESPONSE)"
    cat /tmp/lf_resp.json
    echo
  fi
}

register \
  "deepseek/deepseek-v4-flash" \
  "(?i)^deepseek/deepseek-v4-flash$" \
  "0.00000038" \
  "0.0000015"

register \
  "meta-llama/llama-3.3-70b-instruct" \
  "(?i)^meta-llama/llama-3.3-70b-instruct$" \
  "0.00000012" \
  "0.0000003"

register \
  "deepseek/deepseek-chat" \
  "(?i)^deepseek/deepseek-chat$" \
  "0.00000014" \
  "0.00000028"

register \
  "mistralai/mistral-small-3.1-24b-instruct" \
  "(?i)^mistralai/mistral-small-3.1-24b-instruct$" \
  "0.0000001" \
  "0.0000003"

echo "Done."
