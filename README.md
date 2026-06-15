# VerdeAI

**AI-Powered ISO 14001 Environmental Compliance Assistant**

![Python](https://img.shields.io/badge/Python-3.12-blue?logo=python)
![Docker](https://img.shields.io/badge/Docker-Compose-2496ED?logo=docker)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688?logo=fastapi)
![React](https://img.shields.io/badge/React-18-61DAFB?logo=react)
![LangGraph](https://img.shields.io/badge/LangGraph-0.2-orange)

VerdeAI is a multi-tenant SaaS platform that automates ISO 14001 Environmental Management System compliance gap analysis. Upload your organisation's policy documents, run an AI-powered gap analysis against ISO 14001 clauses, receive prioritised recommendations, and chat with an AI assistant that has full context of your compliance posture.

---

## Features

- **Document ingestion** — Upload PDFs/DOCX; 6-stage pipeline (parse → chunk → contextualise → embed → index) with real-time progress
- **Gap analysis** — LangGraph state machine iterates all ISO 14001 clauses, retrieves relevant evidence, and evaluates compliance with structured reasoning
- **Recommendations** — Auto-generated prioritised action items for each identified gap
- **Missing requirements** — Flags missing organisational data fields needed for a complete assessment
- **Conversational RAG** — Chat interface with hybrid vector + BM25 retrieval and streaming responses, aware of your gap analysis results
- **Multi-tenancy** — All data isolated per tenant via Keycloak JWT claims; no cross-tenant data leakage
- **Observability** — Full LLM trace capture via self-hosted Langfuse with cost tracking

---

## Architecture

```
                         ┌─────────────────────────────────────────┐
                         │           External Clients               │
                         │   Browser (demo_ui :5173)               │
                         └────────────┬───────────────┬────────────┘
                                      │ REST/WS        │ SSE
                           ┌──────────▼──────┐  ┌─────▼──────────┐
                           │  api-gateway    │  │   chat-rag     │
                           │  FastAPI :8000  │  │  FastAPI :8001 │
                           └──────┬──────────┘  └────────────────┘
                                  │ RabbitMQ events
              ┌───────────────────┼──────────────────────────┐
              │                   │                          │
   ┌──────────▼────────┐  ┌───────▼──────────┐  ┌──────────▼──────────┐
   │ document-processor│  │  gap-analyzer    │  │  iso-knowledge      │
   │ (×2 replicas)     │  │  (×2 replicas)   │  │  CLI + consumer     │
   │ 6-stage pipeline  │  │  LangGraph SM    │  │  ISO seed data      │
   └───────────────────┘  └──────┬───────────┘  └─────────────────────┘
                                  │ analyses.gaps.ready
                    ┌─────────────┴──────────────┐
           ┌────────▼─────────┐     ┌────────────▼──────────┐
           │  recommendation  │     │  missing-requirements  │
           │  (×1)            │     │  (×1)                  │
           └──────────────────┘     └───────────────────────┘

   ┌──────────────┐  ┌──────────────┐  ┌──────────┐  ┌────────────────┐
   │  MongoDB :27017│  │ RabbitMQ:5672│  │Redis:6379│  │ Keycloak :8080 │
   │  Atlas Local  │  │  + mgmt:15672│  │          │  │                │
   └──────────────┘  └──────────────┘  └──────────┘  └────────────────┘

   ┌────────────────────────────────────────────┐
   │  Langfuse :3000 (self-hosted observability)│
   │  + langfuse-db (postgres)                  │
   └────────────────────────────────────────────┘
```

### Services

| Service | Type | Description |
|---------|------|-------------|
| `api-gateway` | FastAPI HTTP | Auth, document uploads, analysis orchestration, WebSocket job progress relay |
| `chat-rag` | FastAPI SSE | Conversational RAG with hybrid vector+BM25 search and streaming |
| `document-processor` | RabbitMQ worker ×2 | 6-stage document pipeline: dedup → parse (LlamaParse) → chunk → image summary → embed (Voyage AI) → index |
| `gap-analyzer` | RabbitMQ worker ×2 | LangGraph state machine — iterates ISO 14001 clauses, retrieves evidence, evaluates compliance |
| `recommendation` | RabbitMQ worker | Generates prioritised recommendations for identified gaps |
| `missing-requirements` | RabbitMQ worker | Drafts information-request messages for missing state fields |
| `iso-knowledge` | RabbitMQ worker + CLI | Seeds ISO 14001 clause data and org state templates |

---

## Tech Stack

| Layer | Tool |
|-------|------|
| Language | Python 3.12 |
| HTTP framework | FastAPI 0.115 |
| Async server | Uvicorn + uvloop |
| Database | MongoDB 8 (Atlas Local) + Motor async driver |
| Message broker | RabbitMQ 3.13 (quorum queues) + aio-pika |
| Cache / pubsub | Redis 7 |
| Identity | Keycloak 26 (JWT + JWKS validation) |
| Agent orchestration | LangGraph 0.2 + LangChain Core |
| LLM gateway | OpenRouter (via OpenAI SDK) |
| Embeddings | Voyage AI `voyage-4-lite` (1024 dims) |
| Reranker | Voyage AI `rerank-2.5` |
| Document parsing | LlamaParse (agentic tier) |
| Validation | Pydantic v2 + pydantic-settings |
| Logging | Loguru (structured, per-service) |
| Observability | Langfuse (self-hosted) + OpenTelemetry |
| Frontend | React 18 + Vite + Tailwind CSS + React Router 6 |
| Linter / formatter | Ruff |
| Type checker | Mypy (strict) |
| Tests | pytest + pytest-asyncio + httpx |

---

## Prerequisites

- **Docker Desktop** (Windows/macOS) or **Docker Engine + Compose v2** (Linux)
- **WSL2** (Windows only — required for Docker and make commands)
- **Git**
- **Node.js 18+** and **npm** (for the demo UI only)
- **make** (available in WSL2/Linux/macOS)

---

## Quick Start

### 1. Clone the repository

```bash
git clone <repo-url>
cd VerdeAI
```

### 2. Configure environment variables

The `.env` file is already present. Fill in the required API keys:

```bash
# Minimum required keys
OPENROUTER_API_KEY=sk-or-v1-...     # https://openrouter.ai
VOYAGE_API_KEY=pa-...               # https://www.voyageai.com
LLAMA_CLOUD_API_KEY=llx-...         # https://cloud.llamaindex.ai
```

### 3. Start all services

```bash
make up
```

This builds all Docker images and starts all services. First build takes 3–5 minutes. Infrastructure services (MongoDB, RabbitMQ, Redis, Keycloak) must pass their healthchecks before app services start.

> **Wait ~60–90 seconds** for Keycloak to finish its first-boot realm import.

### 4. Set the Keycloak admin client secret (one-time)

1. Open `http://localhost:8080` → log in with `admin` / `admin`
2. Switch to the **verdeai** realm
3. Go to **Clients** → `verdeai-admin` → **Credentials** → copy the secret
4. Set it in `.env`:
   ```
   KEYCLOAK_ADMIN_CLIENT_SECRET=<copied-secret>
   ```
5. Restart app services:
   ```bash
   make rebuild
   ```

### 5. Seed ISO 14001 clause data

```bash
make seed-iso
```

This populates the `iso_clauses` and `iso_state_template` collections. Required before running any gap analysis.

### 6. Start the demo UI

```bash
cd demo_ui
npm install
npm run dev
```

Open `http://localhost:5173` in your browser.

### 7. Register and log in

Use the UI to register a new user account. The Keycloak realm is pre-configured for self-registration.

---

## Service Endpoints

| Service | URL | Purpose |
|---------|-----|---------|
| API Gateway | `http://localhost:8000` | REST API + WebSocket |
| API Docs (Swagger) | `http://localhost:8000/docs` | Interactive API documentation |
| Chat RAG | `http://localhost:8001` | SSE streaming chat |
| Demo UI | `http://localhost:5173` | React frontend (dev server) |
| Keycloak Admin | `http://localhost:8080` | Identity provider admin console |
| RabbitMQ Management | `http://localhost:15672` | Queue/exchange browser (`guest`/`guest`) |
| Langfuse Dashboard | `http://localhost:3000` | LLM observability (see Observability section) |
| MongoDB | `mongodb://localhost:27017` | Direct connection for debugging |
| Redis | `redis://localhost:6379` | Direct connection for debugging |

---

## Make Commands

```bash
make up           # Build images and start all services in detached mode
make down         # Gracefully stop all services (volumes preserved)
make rebuild      # Rebuild and restart only app services (keeps DB/cache running)
make logs s=<svc> # Stream logs for a service, e.g. s=api-gateway, s=gap-analyzer
make seed-iso     # Seed ISO 14001 clause data into MongoDB
make test         # Run unit + integration tests (pytest --tb=short -q)
make test-e2e     # Run full end-to-end test suite
make test-auth    # Register a test user and fetch a Keycloak JWT for manual API testing
make lint         # Ruff lint check + Mypy strict type check
make fmt          # Ruff format (auto-fix)
make clean        # Remove all containers AND volumes (destructive — data loss!)
```

> **Avoid `make clean`** unless you want to wipe all data (MongoDB, Keycloak, RabbitMQ, Langfuse).
> Use `make down` (stop) or `make rebuild` (hot-swap app code) instead.

---

## Environment Configuration

All config is loaded from `.env` → `verdeai_shared.settings.Settings` (pydantic-settings). Never hardcode secrets.

### Core

```env
ENVIRONMENT=development
LOG_LEVEL=INFO
```

### Keycloak

```env
KEYCLOAK_URL=http://keycloak:8080           # Internal (container-to-container)
KEYCLOAK_PUBLIC_URL=http://localhost:8080   # External (browser-facing)
KEYCLOAK_REALM=verdeai
KEYCLOAK_FRONTEND_CLIENT_ID=verdeai-frontend
KEYCLOAK_ADMIN_CLIENT_ID=verdeai-admin
KEYCLOAK_ADMIN_CLIENT_SECRET=              # Set after first realm import
```

### Database

```env
MONGO_URI=mongodb://mongodb:27017/?directConnection=true
MONGO_DB=verdeai
RABBITMQ_URL=amqp://verdeai:verdeai@rabbitmq:5672/
REDIS_URL=redis://redis:6379/0
```

### LLM (OpenRouter)

```env
OPENROUTER_API_KEY=sk-or-v1-...
PRIMARY_REASONING_MODEL=deepseek/deepseek-v4-flash    # Gap analysis, recommendations
CHEAP_REASONING_MODEL=meta-llama/llama-3.3-70b-instruct  # Chunking, contextualisation
VISION_MODEL=mistralai/mistral-small-3.1-24b-instruct    # Image summaries
```

### Embeddings (Voyage AI)

```env
VOYAGE_API_KEY=pa-...
VOYAGE_EMBEDDING_MODEL=voyage-4-lite
VOYAGE_RERANKER_MODEL=rerank-2.5
EMBEDDING_DIMENSIONS=1024
```

### Document Parsing (LlamaParse)

```env
LLAMA_CLOUD_API_KEY=llx-...
LLAMA_PARSE_TIER=agentic
```

### Observability (Langfuse — self-hosted)

```env
LANGFUSE_PUBLIC_KEY=pk-lf-local-verdeai
LANGFUSE_SECRET_KEY=sk-lf-local-verdeai
LANGFUSE_BASE_URL=http://langfuse:3000
```

### Retrieval Tuning

```env
EMBED_BATCH_SIZE=128
RETRIEVAL_TOP_K=30    # Candidates before reranking
RERANK_TOP_K=8        # Final chunks passed to LLM
CHUNK_TARGET_TOKENS=512
CHUNK_OVERLAP_TOKENS=64
```

---

## Seeding ISO 14001 Data

ISO 14001 clause definitions and state templates must be seeded once before running gap analyses:

```bash
make seed-iso
```

This runs the `iso-knowledge` service CLI, which inserts clause data (titles, requirements, sub-clauses) and state template fields (org profile fields for each clause) into MongoDB.

The seed is idempotent — running it multiple times is safe.

---

## Frontend (demo_ui)

### Setup

```bash
cd demo_ui
npm install
```

### Commands

```bash
npm run dev      # Dev server at http://localhost:5173 (hot-reload)
npm run build    # Production build to dist/
npm run preview  # Serve the production build locally
```

### Environment Variables (`demo_ui/.env`)

```env
VITE_API_URL=http://localhost:8000
VITE_CHAT_URL=http://localhost:8001
VITE_KC_URL=http://localhost:8080
VITE_KC_REALM=verdeai
VITE_KC_CLIENT_ID=verdeai-frontend
```

### Key Patterns

- **Auth** — JWT stored in `localStorage`. `apiFetch()` (in `src/api/client.js`) injects the Bearer token automatically; on 401 clears storage and redirects to `/login`.
- **Chat streaming** — Uses `fetch()` + `ReadableStream` to consume SSE. Parses `token`, `citations`, `error`, `done` event types.
- **Job progress** — WebSocket at `/ws/jobs/{jobId}` via a single-use ticket from `POST /ws/ticket`. Auto-retries up to 3 times on disconnect.

---

## Observability (Langfuse)

All LLM calls are automatically traced via `langfuse.openai` (transparent drop-in for the OpenAI SDK). Named traces include:

| Trace Name | Pipeline |
|------------|----------|
| `analyse_clause:<clause_id>` | Gap analysis per clause |
| `state_compare` | State vs evidence comparison (within clause) |
| `gap_analyse` | Gap decision generation (within clause) |
| `recommendation` | Recommendation generation |
| `draft_request` | Missing information request drafting |
| `chat` | Conversational RAG response |
| `chunk_summary` | Document summary generation |
| `contextualise_chunk` | Chunk contextualisation |
| `image_summary` | Image/diagram summarisation |

### Accessing the Dashboard

1. Open `http://localhost:3000`
2. Log in: `admin@verdeai.local` / `admin123`
3. Select the **verdeai** project

### Registering Model Pricing (one-time)

Langfuse doesn't know the OpenRouter model prices by default. Run the migration script once after Langfuse is up:

```bash
bash migrate_models_to_langfuse.sh
```

This registers pricing for all 4 models so cost columns show non-zero values.

| Model | Input $/M tokens | Output $/M tokens |
|-------|-----------------|------------------|
| `deepseek/deepseek-v4-flash` | $0.38 | $1.50 |
| `meta-llama/llama-3.3-70b-instruct` | $0.12 | $0.30 |
| `deepseek/deepseek-chat` | $0.14 | $0.28 |
| `mistralai/mistral-small-3.1-24b-instruct` | $0.10 | $0.30 |

---

## Development Workflow

### Hot-reload (app services only)

A `docker-compose.override.yml` bind-mounts service source directories and enables Uvicorn `--reload`. Changes to Python files in `services/` and `shared/` are picked up automatically without rebuilding.

### Rebuild a single service

```bash
docker compose up -d --build gap-analyzer
```

Or use `make rebuild` to rebuild all app services while keeping MongoDB, RabbitMQ, Redis, and Keycloak running.

### Stream logs

```bash
make logs s=gap-analyzer
make logs s=api-gateway
make logs s=document-processor
```

### Get a test JWT

```bash
make test-auth
```

This registers a test user (`test@verdeai.local` / `TestPass!23`) and prints the access token for use with `Authorization: Bearer <token>` in API calls.

### MongoDB caution

MongoDB Atlas Local uses WiredTiger — **always use `make down` (graceful stop) not `docker compose down`** to avoid unclean shutdown. If MongoDB fails to start after an unclean stop, remove the `mongo-data` volume:

```bash
docker compose down -v   # WARNING: deletes all data
make up
make seed-iso
```

---

## Testing

### Unit + Integration tests

```bash
make test
# or directly:
pytest --tb=short -q
```

Tests are collected from:
- `shared/tests/`
- `services/*/tests/`
- `tests/integration/` (uses testcontainers — real MongoDB + RabbitMQ)

### End-to-end tests

```bash
make test-e2e
```

Spins up the full Docker Compose stack, runs black-box tests, then stops.

### Single test file

```bash
pytest services/chat-rag/tests/test_pipeline.py -v
```

### Coverage target

≥ 80% coverage per service.

---

## Code Quality

```bash
make lint    # Ruff lint (E, F, W, I, N, UP, B, SIM, ASYNC, S) + Mypy strict
make fmt     # Ruff format (auto-fixes style)
```

Configuration lives in the root `pyproject.toml`:
- Line length: 100
- Target: Python 3.12
- Mypy strict mode — all public functions must be typed

---

## Project Structure

```
VerdeAI/
├── services/
│   ├── api-gateway/          # FastAPI HTTP gateway (port 8000)
│   ├── chat-rag/             # SSE chat service (port 8001)
│   ├── document-processor/   # 6-stage document pipeline (×2 replicas)
│   ├── gap-analyzer/         # LangGraph gap analysis engine (×2 replicas)
│   ├── iso-knowledge/        # ISO clause seeding CLI + worker
│   ├── missing-requirements/ # Missing data request drafter
│   └── recommendation/       # Recommendation generator
│
├── shared/
│   └── verdeai_shared/       # Library imported by all services
│       ├── auth/             # Keycloak JWT validation + tenant ContextVar
│       ├── db/               # Motor connection + 12 repositories (auto-inject tenant_id)
│       ├── llm/              # OpenRouter async client + 12 Jinja2 prompt templates
│       ├── messaging/        # aio-pika consumers, publishers, event models
│       ├── retrieval/        # Voyage AI embeddings, reranker, hybrid search
│       ├── parsing/          # LlamaParse adapter, HybridChunker, dedup
│       ├── pipeline/         # Shared recommendation + missing-request pipelines
│       └── observability/    # Langfuse init, OpenTelemetry tracing
│
├── demo_ui/                  # React 18 + Vite SPA (port 5173 dev)
│   └── src/
│       ├── api/              # apiFetch, auth, documents, analyses, chat
│       ├── context/          # AuthContext
│       ├── hooks/            # useJobProgress (WebSocket)
│       ├── components/       # Layout, Sidebar, Badge, Spinner
│       └── pages/            # Login, Dashboard, Documents, Analysis, Chat
│
├── infra/
│   ├── keycloak/             # realm-export.json (realm, clients, roles)
│   ├── mongodb/init/         # 01-collections.js, 02-vector-indexes.js
│   └── rabbitmq/             # definitions.json, rabbitmq.conf
│
├── tests/
│   ├── e2e/                  # Full stack black-box tests
│   └── integration/          # Testcontainers-based integration tests
│
├── docker-compose.yml        # Service definitions
├── docker-compose.override.yml  # Dev hot-reload overrides
├── Makefile                  # All build and dev commands
├── pyproject.toml            # Ruff, Mypy, Pytest config
├── .env                      # Secrets and configuration
├── migrate_models_to_langfuse.sh  # One-time Langfuse model pricing setup
└── PROJECT.md                # Full build specification (authoritative)
```

---

## Key Architectural Decisions

- **Single LLM gateway** — All LLM calls go through `verdeai_shared.llm.openrouter_client`. Never call LLM APIs directly from service code.
- **Tenant isolation** — `tenant_id` comes exclusively from the validated Keycloak JWT via a ContextVar. Never accept it from request bodies or headers.
- **Crash-resumable gap analysis** — LangGraph results are persisted to `result_store` after each clause. Restarted analyses skip already-completed clauses.
- **Async-only I/O** — Motor (MongoDB), aio-pika (RabbitMQ), httpx (HTTP), redis-py async. No blocking I/O on the event loop.
- **Type safety** — `mypy --strict` must pass. All public functions require type annotations. Pydantic v2 for all DTOs.
