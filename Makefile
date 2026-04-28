.PHONY: up down logs seed-iso test test-e2e lint fmt clean test-auth

up:
	docker compose up -d --build

down:
	docker compose down

logs:
	docker compose logs -f $(s)

seed-iso:
	docker compose run --rm iso-knowledge python -m app.cli seed

test:
	pytest --tb=short -q

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
