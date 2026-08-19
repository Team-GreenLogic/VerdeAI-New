.PHONY: up down logs seed-iso gen-slots test test-e2e lint fmt clean test-auth

up:
	docker compose up -d --build

down:
	docker compose stop

# Rebuild only app services — leaves MongoDB/RabbitMQ/Redis/Keycloak running
rebuild:
	docker compose up -d --build api-gateway document-processor gap-analyzer recommendation missing-requirements chat-rag iso-knowledge langfuse

logs:
	docker compose logs -f $(s)

seed-iso:
	docker compose run --rm iso-knowledge python -m app.cli seed

# Generate slot-filling schemas for a version's clauses. Run --dry-run first (v=<version-id>)
# and read the extraction questions — a weak schema degrades every analysis that follows.
gen-slots:
	docker compose run --rm iso-knowledge python -m app.generate_slot_schemas --version-id $(or $(v),iso-14001-benchmark) $(ARGS)

# Shared + root suites run on the host; each service suite runs from its own directory inside
# its container, because services define colliding top-level `app` packages and their
# dependencies only exist in the image. Billed LLM tests are opt-in (RUN_LLM_TESTS=1).
test:
	pytest --tb=short -q shared/tests tests
	docker compose run --rm -T -w /app/service gap-analyzer sh -c "pip install -q pytest pytest-asyncio; python -m pytest tests --tb=short -q -p no:cacheprovider"
	docker compose run --rm -T -w /app/service api-gateway sh -c "pip install -q pytest pytest-asyncio; python -m pytest tests --tb=short -q -p no:cacheprovider"

test-e2e:
	docker compose up -d --build
	pytest tests/e2e/ --tb=short -q
	docker compose down

test-auth:
	@echo "Registering test user..."
	curl -s -X POST http://localhost:8000/auth/register \
	  -H "Content-Type: application/json" \
	  -d '{"email":"test@verdeai.local","password":"TestPass!23","first_name":"Test","last_name":"User","organisation_name":"Test Org"}' \
	  | python -m json.tool
	@echo "\nFetching token from Keycloak..."
	curl -s -X POST http://localhost:8080/realms/verdeai/protocol/openid-connect/token \
	  -d "grant_type=password&client_id=verdeai-frontend&username=test@verdeai.local&password=TestPass!23&scope=openid profile email" \
	  | python -m json.tool

lint:
	ruff check .
	mypy --strict shared/verdeai_shared services/api-gateway/app

fmt:
	ruff format .

clean:
	docker compose down -v
	docker system prune -f
