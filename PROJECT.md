# VerdeAI — Build Specification

**AI-Powered ISO 14001 Compliance Assistant.** Backend microservices on Docker Compose. No UI. Public surface is REST + SSE + WebSocket.

> This document is the build spec. Every tool listed is the chosen tool — no alternatives. Build the services in the phase order at the end. Tests are required for every phase.

---

## 1. Tech Stack

### Runtime

- **Python 3.12** (all services)
- **Docker Compose v2**
- Single repo, multi-service workspace

### Per-layer tool choices

| Layer | Tool | Pinned version |
|---|---|---|
| HTTP framework | FastAPI | `~=0.115` |
| Async server | Uvicorn (with `uvloop`, `httptools`) | `~=0.32` |
| Async Mongo driver | Motor | `~=3.6` |
| Async AMQP client | aio-pika | `~=9.4` |
| Background workers | Dramatiq (RabbitMQ broker) | `~=1.17` |
| Validation / models | Pydantic v2 + pydantic-settings | `~=2.9`, `~=2.6` |
| Auth | **Keycloak 26** (identity provider) + `python-keycloak` (admin API client) + `pyjwt[crypto]` (JWKS validation) | `quay.io/keycloak/keycloak:26.0`, `python-keycloak ~=4.4`, `pyjwt[crypto] ~=2.9` |
| Logging | Loguru | `~=0.7` |
| Observability | OpenTelemetry SDK + Langfuse | `~=1.27`, `~=2.50` |
| Linter / formatter | Ruff | `~=0.7` |
| Type checker | Mypy (strict) | `~=1.13` |
| Tests | pytest + pytest-asyncio + httpx | `~=8.3`, `~=0.24`, `~=0.27` |
| Document parsing | **Docling** | `~=2.10` |
| Chunking | Docling `HybridChunker` | (bundled) |
| Embeddings | **Voyage AI `voyage-3-large`** (1024 dims) | `voyageai ~=0.3` |
| Reranker | **Voyage AI `rerank-2.5`** | (same SDK) |
| BM25 | `bm25s` | `~=0.2` |
| Image hashing | `imagehash` (pHash) | `~=4.3` |
| Content-defined chunking (dedup) | `fastcdc` | `~=1.5` |
| Agent orchestration | **LangGraph** + LangChain Core | `langgraph ~=0.2`, `langchain-core ~=0.3` |
| LLM gateway | **OpenRouter** (official SDK; supports sync + async + streaming) — used for **all** LLM calls (reasoning, contextualisation, vision, query rewrite) | `openrouter ~=0.9` |
| Reasoning model (default) | `deepseek/deepseek-r1-0528` via OpenRouter | — |
| Cheap model (default) | `qwen/qwen3-coder` via OpenRouter | — |
| Vision model (default) | `mistralai/mistral-small-3.1-24b-instruct` via OpenRouter | — |
| Web search (ISO recommendation seeding) | Tavily | `tavily-python ~=0.5` |
| Vector store + operational DB | **MongoDB 8** with Atlas Vector Search | `mongodb/mongodb-atlas-local:8.0` for local |
| Message broker | **RabbitMQ 3.13** (quorum queues) | `rabbitmq:3.13-management` |
| Cache / locks / pubsub | **Redis 7** | `redis:7-alpine` |
| PDF report rendering | WeasyPrint | `~=63` |

### LLM routing (all calls go through OpenRouter)

```
OPENROUTER_BASE_URL     = https://openrouter.ai/api/v1   # implicit in the SDK
PRIMARY_REASONING_MODEL = deepseek/deepseek-r1-0528                  # reasoning / gap analysis
CHEAP_REASONING_MODEL   = qwen/qwen3-coder                           # contextualisation, query rewrite
VISION_MODEL            = mistralai/mistral-small-3.1-24b-instruct   # diagram / image summary (multimodal)
EMBEDDING_MODEL         = voyage-3-large                             # direct Voyage API (OpenRouter does not host embeddings)
RERANKER_MODEL          = rerank-2.5                                 # direct Voyage API
```

Model IDs are env-driven and can be swapped at runtime (any of OpenRouter's 300+ catalogue entries: `anthropic/*`, `openai/*`, `google/*`, `meta-llama/*`, `deepseek/*`, `qwen/*`, `mistralai/*`, etc.) without code changes. The `shared/llm/openrouter_client.py` wrapper is the only place LLM calls happen — the rest of the codebase routes through it.

OpenRouter requests must include `HTTP-Referer` and `X-Title` headers (good citizenship + leaderboard attribution); the SDK accepts these as constructor args. **Prompt caching is provider-dependent** — Anthropic-style `cache_control` works only when the routed model is an Anthropic one. For the default cheap stack (DeepSeek/Qwen/Mistral) no caching applies; the contextualisation pipeline must therefore minimise tokens-per-call rather than rely on cache hits.

### `shared/llm/openrouter_client.py` contract

Single async client used everywhere. Wraps the official `openrouter` SDK (`pip install openrouter`).

```python
from openrouter import AsyncOpenRouter
from verdeai_shared.settings import settings

_client: AsyncOpenRouter | None = None


def _get_client() -> AsyncOpenRouter:
    global _client
    if _client is None:
        _client = AsyncOpenRouter(
            api_key=settings.OPENROUTER_API_KEY,
            http_referer=settings.OPENROUTER_APP_URL,
            x_open_router_title=settings.OPENROUTER_APP_NAME,
        )
    return _client


async def complete(
    *,
    model: str,                          # e.g. settings.PRIMARY_REASONING_MODEL
    messages: list[dict],
    temperature: float = 0.0,
    max_tokens: int = 2048,
    response_format: dict | None = None, # {"type": "json_schema", "json_schema": {...}}
    provider: dict | None = None,        # e.g. {"sort": "price"} or {"zdr": True}
    extra: dict | None = None,           # passthrough for OpenRouter-specific knobs
) -> "ChatResponse":
    client = _get_client()
    res = await client.chat.send(
        messages=messages,
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
        response_format=response_format,
        provider=provider or {"sort": "price"},   # default: cheapest viable provider
        **(extra or {}),
    )
    return res                            # res.choices[0].message.content


async def stream(
    *,
    model: str,
    messages: list[dict],
    temperature: float = 0.0,
    max_tokens: int = 2048,
    provider: dict | None = None,
):
    client = _get_client()
    async for event in await client.chat.send(
        messages=messages,
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
        stream=True,
        provider=provider or {"sort": "price"},
    ):
        yield event                       # event.choices[0].delta.content


async def aclose() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None
```

Rules:

- All callers pass a model ID resolved from `settings` — never hardcoded strings — so the routing table is the single switchboard.
- The default `provider={"sort": "price"}` ensures OpenRouter routes to the cheapest healthy provider for the chosen model. Override per-call when a specific provider is required (e.g. zero-data-retention with `{"zdr": True}`).
- The wrapper is the only place the `openrouter` SDK is imported. Service code only ever sees `complete()` / `stream()`.
- Each service `main.py` registers `aclose()` as a shutdown hook so HTTP connections drain cleanly.

---

## 2. Repository Layout

```
verdeai/
├── README.md
├── docker-compose.yml
├── docker-compose.override.yml          # local-dev overrides (volumes, hot-reload)
├── .env.example
├── .gitignore
├── pyproject.toml                       # workspace root: ruff, mypy, pytest config
├── Makefile                             # up, down, logs, seed-iso, test, lint
│
├── shared/                              # reusable library imported by every service
│   ├── pyproject.toml
│   └── verdeai_shared/
│       ├── __init__.py
│       ├── settings.py                  # pydantic-settings, env loader
│       ├── logging.py                   # loguru + OTel hook
│       ├── auth/
│       │   ├── jwks.py                  # JWKS fetcher with TTL cache
│       │   ├── token.py                 # JWT signature + claims validation (pyjwt)
│       │   ├── principal.py             # Principal model: sub, tenant_id, email, roles
│       │   ├── tenant.py                # contextvar + FastAPI dependency
│       │   └── keycloak_admin.py        # python-keycloak admin client (api-gateway only)
│       ├── messaging/
│       │   ├── connection.py            # aio-pika connection manager
│       │   ├── exchanges.py             # exchange + queue declarations
│       │   ├── publisher.py
│       │   ├── consumer.py              # base async consumer
│       │   └── events.py                # versioned pydantic event payloads
│       ├── db/
│       │   ├── mongo.py                 # motor client factory
│       │   ├── indexes.py               # idempotent index creator
│       │   └── repositories/
│       │       ├── base.py              # injects tenant_id on every query
│       │       ├── documents.py
│       │       ├── chunks.py
│       │       ├── iso_clauses.py
│       │       ├── iso_state.py
│       │       ├── state_store.py
│       │       ├── result_store.py
│       │       ├── recommendation_store.py
│       │       ├── missing_request_store.py
│       │       └── chat_history.py
│       ├── llm/
│       │   ├── openrouter_client.py     # AsyncOpenRouter wrapper — single LLM entry point
│       │   ├── prompts/                 # jinja2 templates
│       │   │   ├── contextualise_chunk.j2
│       │   │   ├── image_summary.j2
│       │   │   ├── state_compare.j2
│       │   │   ├── gap_analyse.j2
│       │   │   ├── recommend.j2
│       │   │   ├── actionability.j2
│       │   │   ├── draft_request.j2
│       │   │   └── chat_system.j2
│       │   └── tracing.py               # langfuse decorator
│       ├── retrieval/
│       │   ├── embedder.py              # voyage-3-large wrapper
│       │   ├── reranker.py              # rerank-2.5 wrapper
│       │   ├── vector_search.py         # $vectorSearch aggregation
│       │   ├── bm25.py                  # bm25s wrapper, per-tenant
│       │   └── hybrid.py                # RRF fusion + rerank pipeline
│       ├── parsing/
│       │   ├── docling_adapter.py
│       │   ├── chunking.py              # HybridChunker + contextual augmentation
│       │   └── dedup.py                 # SHA-256, pHash, FastCDC
│       └── observability/
│           ├── tracing.py
│           └── langfuse.py
│
├── services/
│   ├── api-gateway/
│   ├── document-processor/
│   ├── iso-knowledge/
│   ├── gap-analyzer/
│   ├── recommendation/
│   ├── missing-requirements/
│   └── chat-rag/
│
├── infra/
│   ├── mongodb/
│   │   └── init/
│   │       ├── 01-collections.js
│   │       └── 02-vector-indexes.js
│   ├── rabbitmq/
│   │   ├── definitions.json
│   │   └── rabbitmq.conf
│   └── keycloak/
│       └── realm-export.json            # declarative realm: clients, mappers, roles
│
├── tests/
│   ├── e2e/                             # docker-compose-up + black-box flow
│   ├── integration/
│   └── fixtures/
│       ├── sample_organization_data.json
│       └── sample_pdfs/
│
└── tooling/
    ├── seed_iso.py                      # populate iso_clauses + iso_state_template
    ├── synthetic_corpus.py              # generate fixture tenants
    └── eval/                            # RAGAS harness
```

Each service folder follows the same template:

```
services/<name>/
├── Dockerfile
├── pyproject.toml
└── app/
    ├── __init__.py
    ├── main.py                          # entrypoint (FastAPI app or worker bootstrap)
    ├── config.py                        # service-specific Settings subclass
    └── ...                              # service-specific modules (see §4)
```

---

## 3. Coding Standards

- **Type hints everywhere.** `mypy --strict` must pass.
- **Pydantic v2 models** for all DTOs. No raw dicts crossing service boundaries.
- **Ruff** with rulesets: `E,F,W,I,N,UP,B,SIM,RUF,ASYNC,S,C4`. Line length 100.
- **Async everywhere.** No sync I/O in request paths. Use `motor`, `aio-pika`, `httpx.AsyncClient`.
- **Repository pattern** for all Mongo access. Repositories accept a `tenant_id` and inject it into every query. Handlers never call Mongo directly.
- **Tenant isolation contract:** `verdeai_shared.auth.tenant.get_tenant_id()` is the only source. The value originates from the validated Keycloak JWT's `tenant_id` claim — **never** from a request body, query param, or header. Repositories assert non-null tenant_id at construction.
- **Structured logging** with Loguru. Every log record carries `tenant_id`, `request_id`, `service`.
- **Tracing:** every LLM call wrapped in `@trace` (Langfuse) and every Mongo/HTTP call instrumented via OpenTelemetry.
- **Testing:**
  - Each service ships unit tests under `services/<name>/tests/`.
  - Shared lib has its own tests under `shared/tests/`.
  - Integration tests under `tests/integration/` (real Mongo, real RabbitMQ via `testcontainers`).
  - E2E tests under `tests/e2e/` (docker-compose up).
  - Coverage gate: ≥ 80 % per service.
- **No secrets in code.** All come from `verdeai_shared.settings.Settings`.

---

## 3.1 Keycloak Realm Specification

Keycloak is the identity provider for the entire platform. **No service stores password hashes or signs JWTs.** Every public endpoint validates incoming tokens against Keycloak's JWKS.

### Realm: `verdeai`

Single realm, multi-tenant via a **`tenant_id` user attribute** mapped into every access token as a custom claim. This is lighter than realm-per-tenant and scales cleanly for the POC.

### Clients

| Client ID | Type | Purpose | Grants |
|---|---|---|---|
| `verdeai-frontend` | public | Browser/mobile/CLI clients authenticate against this client. Redirect URIs configured for the API caller. | Authorization Code + PKCE, Refresh Token, Direct Access (for testing) |
| `verdeai-admin` | confidential | Used **only** by the `api-gateway` to call Keycloak's Admin API for atomic tenant + user creation during `/auth/register`. Has the `realm-management.manage-users` and `view-users` service-account roles. | Client Credentials |

### Roles (realm-level)

- `compliance-officer` — default role for end users. Assigned at registration.
- `tenant-admin` — can invite additional users into the same tenant (Phase 2 feature; reserve the role now).

### User attributes & protocol mapper

Every user has a custom attribute `tenant_id` (string, UUID v4). A **User Attribute** protocol mapper on `verdeai-frontend`:

- Mapper name: `tenant-id-mapper`
- Mapper type: `User Attribute`
- User Attribute: `tenant_id`
- Token Claim Name: `tenant_id`
- Claim JSON Type: `String`
- Add to ID token: ✓
- Add to access token: ✓
- Add to userinfo: ✓

Result: every access token contains a top-level `tenant_id` claim. The `email`, `preferred_username`, and `realm_access.roles` claims are present by default and used by `principal.py`.

### Token validation

`shared/auth/token.py` validates incoming bearer tokens:

1. Extract `kid` from JWT header.
2. Fetch the matching public key from `{KEYCLOAK_URL}/realms/verdeai/protocol/openid-connect/certs` (cached for 1 hour; refreshed on signature failure once).
3. Verify signature, `iss` (must equal `{KEYCLOAK_URL}/realms/verdeai`), `aud` (must equal `verdeai-frontend` or `account`), and `exp`.
4. Build a `Principal`:
   ```python
   class Principal(BaseModel):
       sub: str          # Keycloak user UUID
       tenant_id: str    # from custom claim — required, fail if missing
       email: str
       roles: list[str]  # from realm_access.roles
   ```
5. Set `tenant_id` into the request-scoped `ContextVar` consumed by repositories.

Tokens missing `tenant_id` → 403 (the user was created outside the standard registration flow). This is the single chokepoint that prevents tenant cross-contamination.

### Realm bootstrap

`infra/keycloak/realm-export.json` is a declarative realm definition imported on container start (`--import-realm` flag). It defines the realm, both clients, the protocol mapper, the roles, and a single seed admin user (`admin@verdeai.local` / `changeme`) with a freshly generated `tenant_id` so devs can `make up` and immediately get a working stack.

### Service-to-service auth

`api-gateway` calls `chat-rag` over the private Docker network. **It forwards the original end-user JWT** in the `Authorization` header; `chat-rag` runs the same `token.py` validation. No separate service token needed — the user's own token authorises both hops, and tenant scoping is preserved end-to-end.

---



## 4. Service Specifications

### 4.1 `api-gateway`

**Type:** FastAPI HTTP service. Public.

**Module layout:**

```
services/api-gateway/app/
├── main.py
├── config.py
├── routers/
│   ├── auth.py                          # /auth/register only — wraps Keycloak Admin API
│   ├── documents.py
│   ├── analyses.py
│   ├── recommendations.py
│   ├── missing.py
│   ├── chat.py                          # proxies to chat-rag (SSE pass-through, forwards JWT)
│   └── ws.py                            # /ws/jobs/{job_id}
├── dependencies/
│   ├── auth.py                          # validates Keycloak JWT → Principal (sub, tenant_id, email, roles)
│   └── rate_limit.py                    # redis-backed
├── middleware/
│   ├── request_id.py
│   ├── tenant_scope.py
│   └── error_handler.py
├── schemas/                             # request/response pydantic models
└── services/                            # thin clients to the workers via RMQ
    ├── document_publisher.py
    ├── analysis_publisher.py
    └── glassbox_relay.py                # subscribes redis pubsub → ws
```

**Endpoints:** see §8.

**Behaviours:**
- `POST /auth/register` is the **only** auth endpoint the gateway implements. It calls Keycloak Admin API via `python-keycloak` to (a) generate a fresh `tenant_id` UUID, (b) create the user with that attribute, (c) assign `compliance-officer` role, (d) upsert a `users` row in Mongo keyed by Keycloak `sub`. Login, refresh, password reset, and account console all live on Keycloak directly — clients hit `/realms/verdeai/protocol/openid-connect/token` themselves.
- Every other endpoint requires a valid Keycloak access token. The `dependencies/auth.py` dependency validates against JWKS, builds a `Principal`, and writes `tenant_id` to the request-scoped `ContextVar` before any handler runs.
- `POST /documents` validates, writes a `documents` row with `status=queued`, publishes `document.uploaded` to RabbitMQ, returns 202.
- `POST /analyses` writes an `analyses` row, publishes `analysis.requested`, returns 202.
- `WS /ws/jobs/{job_id}` subscribes to `glassbox.{tenant_id}.{job_id}` Redis channel and forwards messages until the terminal event arrives, then closes. WebSocket auth uses a short-lived ticket: client first calls `POST /ws/ticket` with their Bearer token to receive a single-use ticket, then connects with `?ticket=...`. This sidesteps the Bearer-header limitation of WS clients.
- `POST /chat` forwards to `chat-rag` over HTTP **and forwards the user's JWT** in the `Authorization` header so chat-rag re-validates and reuses the same tenant scope.
- `DELETE /documents/{id}` publishes `document.deleted` (workers tombstone chunks + bm25 entries).

---

### 4.2 `document-processor`

**Type:** Dramatiq worker. Private.

**Module layout:**

```
services/document-processor/app/
├── main.py                              # bootstraps dramatiq + actors
├── config.py
├── actors.py                            # @dramatiq.actor entrypoints
├── pipeline/
│   ├── stage1_dedup.py
│   ├── stage2_parse.py
│   ├── stage3_chunk.py
│   ├── stage4_image.py
│   ├── stage5_embed.py
│   └── stage6_index.py
└── progress.py                          # publish glass-box events to redis pubsub
```

**Pipeline (one Dramatiq actor per stage; chained):**

1. **Stage 1 — Dedup gate** (`stage1_dedup.py`)
   - SHA-256 of raw bytes. If `(tenant_id, sha256)` exists in `hash_store`, short-circuit, set `status=deduped`, emit `document.ready` referencing the existing `document_id`.
   - Otherwise compute per-page pHash (8-bit) for image-bearing pages and FastCDC chunk hashes (avg=4 KB, min=2 KB, max=8 KB) on the extracted text. Persist to `hash_store`.
   - When a *modified* version of an existing document is uploaded (matched by filename + tenant), compute the % overlap of FastCDC chunks vs. the previous version. If > 50 %, the next stages process only changed chunks.

2. **Stage 2 — Layout-aware parse** (`stage2_parse.py`)
   - `from docling.document_converter import DocumentConverter`.
   - `DocumentConverter().convert(path).document` → `DoclingDocument`.
   - Persist the canonical JSON (gridfs) for citation back-references; store the GridFS id on the document row.

3. **Stage 3 — Chunking + contextualisation** (`stage3_chunk.py`)
   - `from docling.chunking import HybridChunker`. Target 512 tokens, 64 overlap, never split across table rows.
   - For each chunk, call `complete(model=settings.CHEAP_REASONING_MODEL, ...)` (OpenRouter → Qwen3-Coder by default) with `prompts/contextualise_chunk.j2`.
   - **Token economy** (no prompt caching on the default cheap stack): the prompt sends a *short* document summary (pre-computed once per document, cached in `documents.summary`) plus the chunk being situated — not the whole document on every call. Aim for ≤ 2 K input tokens per call. If the configured model is Anthropic-family, the wrapper opportunistically adds `cache_control` blocks for an additional ~90 % cost cut.
   - Output: 1–2 sentence preamble. Final stored text: `f"CONTEXT: {preamble}\n\n{chunk_text}"`.

4. **Stage 4 — Image / diagram summary** (`stage4_image.py`)
   - For every `PictureItem` in the DoclingDocument, call `complete(model=settings.VISION_MODEL, ...)` (OpenRouter → Mistral Small 3.1 24B by default — multimodal) with `prompts/image_summary.j2` and the image attached as a content block → text summary.
   - Treat each summary as a chunk with `content_type=image_summary`, linked back to the picture's bbox.

5. **Stage 5 — Embedding** (`stage5_embed.py`)
   - `voyageai.Client().embed(texts, model="voyage-3-large", input_type="document")`.
   - Batch up to 128 texts per call. Retry with exponential backoff on `RateLimitError`.

6. **Stage 6 — Index** (`stage6_index.py`)
   - Insert chunks into `chunks` collection.
   - Append to per-tenant BM25 index (rebuilt as a serialised `bm25s.BM25` document per tenant per N updates).

**Progress events:** every stage publishes `glassbox.{tenant_id}.{document_id}` Redis pubsub messages with shape `{"stage": "...", "status": "...", "detail": "..."}`. After Stage 6, also publishes `document.ready` to RabbitMQ.

**Scaling:** `deploy.replicas: 2` in compose, configurable.

---

### 4.3 `iso-knowledge`

**Type:** Dramatiq worker + one-shot CLI. Private.

**Module layout:**

```
services/iso-knowledge/app/
├── main.py
├── config.py
├── actors.py
├── seeds/
│   ├── iso_14001_summaries.md           # paraphrased clauses (copyright-safe)
│   └── org_state_template.json          # = sample_organization_data.json shape
├── agents/
│   ├── clause_extractor.py              # parses summaries → ClauseDoc
│   ├── state_generator.py               # walks template → StateAssertion[]
│   └── recommendation_seeder.py         # Tavily search → cached actions per clause
└── cli.py                               # invoked by tooling/seed_iso.py
```

**Responsibilities:**
- One-shot seed populates `iso_clauses` and `iso_state_template` collections.
- Walks `seeds/org_state_template.json` (= `sample_organization_data.json` shape) and emits one `iso_state_template` row per leaf field, classified into one of the six entry types (§7.1) per the §7.2 mapping.
- Loads the sample JSON itself as the **demo tenant's `org_profile`** so the regression test can run out of the box.
- For each clause, the `recommendation_seeder` queries Tavily for public templates / checklists / case studies and persists 3–5 generic suggestions per clause to `iso_clauses.actionable_seeds[]`.

**Idempotent.** Re-running the seed updates docs by `_id`, never duplicates.

---

### 4.4 `gap-analyzer`

**Type:** Dramatiq worker hosting a LangGraph state machine. Private.

**Module layout:**

```
services/gap-analyzer/app/
├── main.py                              # bootstraps dramatiq + langgraph checkpointer
├── config.py
├── actors.py                            # one actor: run_gap_analysis(analysis_id)
├── graph/
│   ├── state.py                         # GapAnalysisState (TypedDict)
│   ├── workflow.py                      # graph assembly
│   └── nodes/
│       ├── pop_next_clause.py
│       ├── retrieve.py                  # hybrid: vector + BM25 + RRF (top 30)
│       ├── rerank.py                    # voyage rerank-2.5 (top 8)
│       ├── filter_seen.py
│       ├── compare_state.py             # State Comparing Agent
│       └── analyse_gap.py               # Gap Analysis Agent (CoT)
├── persistence.py                       # write state_store + result_store
└── progress.py                          # glass-box emitter
```

**State schema:**

```python
from typing import TypedDict, Literal, Callable

class ClauseRef(TypedDict):
    clause_id: str
    title: str

class Citation(TypedDict):
    document_id: str
    chunk_id: str
    page: int

class GapAnalysisState(TypedDict):
    tenant_id: str
    analysis_id: str
    pending_clauses: list[ClauseRef]
    current_clause: ClauseRef | None
    retrieved_evidence: list[dict]               # chunks
    state_diff: dict
    decision: Literal["Met", "Partially Met", "Not Met", "Insufficient Evidence"]
    confidence: float
    citations: list[Citation]
    results: list[dict]
```

**Graph:**

```
START
  │
  ▼
pop_next_clause ── (none) ──► END
  │
  ▼
retrieve  ── hybrid vector + BM25 + RRF, top 30
  │
  ▼
rerank    ── voyage rerank-2.5, top 8
  │
  ▼
filter_seen ── (zero new) ──► persist "no new evidence" → pop_next_clause
  │
  ▼
compare_state
  │   ── loads all iso_state_template entries for this clause
  │   ── loads org_profile values for those field_paths + linked_reference_paths
  │   ── evaluates the assertion-typed entries (boolean / freshness / count / array_min_items / notes_signal)
  │   ── builds state_diff: {assertion_path: {expected, actual, satisfied, kind}}
  │   ── reference-typed entries are added to context only (not evaluated)
  │
  ▼
analyse_gap
  │   ── prompt receives: clause text + state_diff + reference context + reranked evidence chunks
  │   ── chain-of-thought decision: Met / Partially Met / Not Met / Insufficient Evidence
  │   ── ALL failures must cite either an org_profile field (self-declared) or a chunk_id
  │
  ▼
persist (state_store + result_store) + glass-box emit
  │
  └─► pop_next_clause
```

**Checkpointer:** `MongoDBSaver` from `langgraph.checkpoint.mongodb` against the `langgraph_checkpoints` collection. A worker crash resumes from the last completed clause.

**Triggers:** consumes `analysis.requested`. On completion publishes `analysis.gaps.ready` and `analysis.missing.ready`.

---

### 4.5 `recommendation`

**Type:** Dramatiq worker hosting a LangGraph workflow. Private.

**Module layout:**

```
services/recommendation/app/
├── main.py
├── config.py
├── actors.py
├── graph/
│   ├── state.py
│   ├── workflow.py
│   └── nodes/
│       ├── generate.py                  # uses iso_clauses.actionable_seeds + gap evidence
│       ├── actionability_evaluator.py   # 5-axis score
│       └── prioritise.py                # Quick Win / Major Initiative / Standard
└── persistence.py
```

**Prioritisation rules:**
- `quick_win`: `cost ≤ 2 AND effort_weeks ≤ 2 AND impact ≥ 3`
- `major_initiative`: `impact ≥ 4 AND effort_weeks ≥ 4`
- otherwise `standard`

**Triggers:** consumes `analysis.gaps.ready`. Writes to `recommendation_store`. Publishes `analysis.recommendations.ready`.

---

### 4.6 `missing-requirements`

**Type:** Dramatiq worker. Private.

**Module layout:**

```
services/missing-requirements/app/
├── main.py
├── config.py
├── actors.py
├── identify.py                          # walk iso_state_template, find unsatisfied
└── draft.py                             # produce request text per missing item
```

**Behaviour:** triggered by `analysis.missing.ready`. For each `iso_state_template` assertion with `expected: true` and no supporting evidence in `state_store` for the tenant:
1. Identify the responsible role (from the tenant's `org_profile.leadership.roles[]`, or a default mapping).
2. Call `complete(model=settings.CHEAP_REASONING_MODEL, ...)` with `prompts/draft_request.j2` to write a 3–4 sentence request.
3. Persist to `missing_request_store`.

---

### 4.7 `chat-rag`

**Type:** FastAPI HTTP service with SSE streaming. Private (only `api-gateway` calls it).

**Module layout:**

```
services/chat-rag/app/
├── main.py                              # FastAPI app, /chat endpoint
├── config.py
├── memory.py                            # short-term (last N) + long-term summary
├── retriever.py                         # hybrid + rerank (reuses shared lib)
├── query_rewriter.py                    # cheap-model call for follow-ups
├── responder.py                         # primary-model streaming response
└── prompts/
```

**Per-message flow:**
1. Resolve tenant. Load short-term memory (last 10 turns) + long-term summary from `chat_history` and `chat_memory_summary`.
2. If `len(history) > 0`, run query rewriter via `complete(model=settings.CHEAP_REASONING_MODEL, ...)`.
3. Hybrid retrieve → top 30. Rerank → top 8.
4. Stream answer via `stream(model=settings.PRIMARY_REASONING_MODEL, ...)` over SSE. System prompt enforces citation-or-refuse and is enriched with the tenant's `org_profile` (organisation name, sites, primary activities, roles) so the model has stable identity context across turns.
5. After completion, async-update long-term summary if `len(history) % 10 == 0`.

**Citation contract:** every assertive sentence must end with `[doc:<filename>, p.<page>]`. The responder is given chunk_ids; a post-stream check verifies cited chunk_ids exist in the retrieved set.

---

## 5. Inter-Service Messaging

**Broker:** RabbitMQ with **quorum queues** (durable, replicated).

### Exchanges + queues (`infra/rabbitmq/definitions.json`)

| Exchange | Type | Routing keys | Bound queues |
|---|---|---|---|
| `documents` | topic | `document.uploaded`, `document.ready`, `document.deleted` | `documents.process` (← `document.uploaded`), `documents.invalidate` (← `document.deleted`) |
| `analyses` | topic | `analysis.requested`, `analysis.gaps.ready`, `analysis.missing.ready`, `analysis.recommendations.ready`, `analysis.completed` | `analyses.run` (← `analysis.requested`), `analyses.recommend` (← `analysis.gaps.ready`), `analyses.missing` (← `analysis.missing.ready`) |
| `iso` | topic | `iso.clause.added`, `iso.state.updated` | `iso.cache_bust` |

All queues are quorum queues with `x-delivery-limit: 5` and a DLX (`*.dlx`).

### Event payloads (`shared/messaging/events.py`)

```python
class DocumentUploaded(BaseModel):
    schema_version: int = 1
    tenant_id: str
    document_id: str
    filename: str
    sha256: str
    uploaded_at: datetime

class DocumentReady(BaseModel):
    schema_version: int = 1
    tenant_id: str
    document_id: str
    chunks_indexed: int

class AnalysisRequested(BaseModel):
    schema_version: int = 1
    tenant_id: str
    analysis_id: str
    scope: Literal["full"] | dict  # {"clauses": ["..."]}

class AnalysisGapsReady(BaseModel):
    schema_version: int = 1
    tenant_id: str
    analysis_id: str
    gap_count: int

class AnalysisMissingReady(BaseModel):
    schema_version: int = 1
    tenant_id: str
    analysis_id: str
```

**Idempotency:** every message carries `event_id: UUID` in its AMQP properties. Consumers store processed UUIDs in Redis (`SETNX` with 24 h TTL) and skip duplicates.

**Glass-box channel:** Redis pubsub channel `glassbox.{tenant_id}.{job_id}` (NOT RabbitMQ — needs broadcast-to-many-WS-subscribers semantics).

---

## 6. MongoDB Schemas

### Collections (`infra/mongodb/init/01-collections.js`)

| Collection | Required fields | Compound indexes |
|---|---|---|
| `users` | `_id`, `keycloak_sub` (unique, equals JWT `sub`), `email`, `tenant_id`, `roles`, `created_at`, `last_seen_at` | `{keycloak_sub: 1}` unique, `{tenant_id: 1}` |
| `tenants` | `_id`, `name`, `industry`, `created_at` | — |
| `documents` | `_id`, `tenant_id`, `filename`, `sha256`, `status`, `pages`, `docling_blob_ref`, `summary`, `created_at` | `{tenant_id: 1, sha256: 1}`, `{tenant_id: 1, status: 1}` |
| `chunks` | `_id`, `tenant_id`, `document_id`, `page`, `bbox`, `text`, `context_preamble`, `embedding`, `content_type`, `created_at` | `{tenant_id: 1, document_id: 1}` |
| `bm25_indexes` | `_id`, `tenant_id`, `serialized`, `version` | `{tenant_id: 1}` unique |
| `iso_clauses` | `_id`, `clause_id`, `section`, `title`, `summary_paraphrase`, `required_evidence[]`, `verification_questions[]`, `embedding`, `actionable_seeds[]`, `version` | `{clause_id: 1}` unique |
| `iso_state_template` | `_id`, `clause_id`, `field_path`, `entry_type`, `value_type`, `expected`, `min_items`, `max_age_days`, `comparator`, `threshold`, `evidence_keywords[]`, `criticality`, `linked_reference_paths[]`, `notes_field`, `description` | `{field_path: 1}` unique, `{clause_id: 1}` |
| `org_profile` | `_id`, `tenant_id`, `field_path`, `value`, `value_type`, `source` (`uploaded_form` / `extracted` / `default`), `extracted_from_chunk_id`, `confidence`, `updated_at` | `{tenant_id: 1, field_path: 1}` unique |
| `state_store` | `_id`, `tenant_id`, `clause_id`, `evidence_chunks[]`, `last_decision`, `updated_at` | `{tenant_id: 1, clause_id: 1}` unique |
| `result_store` | `_id`, `analysis_id`, `tenant_id`, `clause_id`, `decision`, `confidence`, `citations[]`, `created_at` | `{analysis_id: 1}`, `{tenant_id: 1, analysis_id: 1, clause_id: 1}` unique |
| `recommendation_store` | `_id`, `analysis_id`, `tenant_id`, `clause_id`, `text`, `priority`, `effort`, `impact`, `created_at` | `{analysis_id: 1, priority: 1}` |
| `missing_request_store` | `_id`, `analysis_id`, `tenant_id`, `clause_id`, `field_path`, `draft_text`, `responsible_role`, `created_at` | `{analysis_id: 1}` |
| `analyses` | `_id`, `tenant_id`, `scope`, `status`, `started_at`, `completed_at` | `{tenant_id: 1, status: 1}` |
| `chat_history` | `_id`, `tenant_id`, `session_id`, `role`, `content`, `citations[]`, `created_at` | `{tenant_id: 1, session_id: 1, created_at: 1}` |
| `chat_memory_summary` | `_id`, `tenant_id`, `session_id`, `summary`, `updated_at` | `{tenant_id: 1, session_id: 1}` unique |
| `hash_store` | `_id`, `tenant_id`, `sha256`, `phashes[]`, `fastcdc_chunks[]`, `document_id`, `created_at` | `{tenant_id: 1, sha256: 1}` unique |
| `langgraph_checkpoints` | (managed by LangGraph) | — |

### Vector Search index (`02-vector-indexes.js`)

```javascript
db.chunks.createSearchIndex({
  name: "chunks_vector_idx",
  type: "vectorSearch",
  definition: {
    fields: [
      { type: "vector", path: "embedding", numDimensions: 1024, similarity: "cosine" },
      { type: "filter", path: "tenant_id" },
      { type: "filter", path: "document_id" },
      { type: "filter", path: "content_type" }
    ]
  }
});

db.iso_clauses.createSearchIndex({
  name: "iso_clauses_vector_idx",
  type: "vectorSearch",
  definition: {
    fields: [
      { type: "vector", path: "embedding", numDimensions: 1024, similarity: "cosine" }
    ]
  }
});
```

The `tenant_id` filter is part of the vector index — every `$vectorSearch` aggregation includes a `filter` clause. Repository layer enforces this; missing tenant_id raises before the query is dispatched.

---

## 7. ISO State Template — Full Mapping

The seeder walks `sample_organization_data.json` and produces `iso_state_template` entries. Two collections result:

- **`iso_state_template`** — the *schema*: every field path in the canonical org JSON, classified by `entry_type`. Used by the gap analyser to know what to look for and how to interpret it.
- **`org_profile`** (per tenant) — the *values*: the actual answers for *this* organisation, populated by the user (form fill or imported JSON) and/or extracted by the document-processor from uploaded files.

The sample JSON itself is loaded as the **demo tenant's `org_profile`**, so running the analyser against the demo tenant should reproduce exactly the gaps it advertises.

### 7.1 Six entry types

| `entry_type` | Purpose | Drives Met/Not Met? | Loaded into prompt context? |
|---|---|---|---|
| `boolean_assertion` | Field must be `true`. Classic compliance flag. | **Yes** | Yes |
| `freshness` | Date field must be within `max_age_days`. | **Yes** | Yes (date + age) |
| `count_threshold` | Integer compared via `comparator` against `threshold`. | **Yes** | Yes |
| `array_min_items` | Array must contain ≥ `min_items` entries; the entries themselves are stored as context. | **Yes** | Yes (whole array) |
| `reference` | Scalar context value (string / number / bool / date). Not an assertion, but enriches the agent's prompt. | No | **Yes** |
| `notes_signal` | Free-text field whose **non-empty** value is a self-acknowledged gap (e.g. "VOC emissions not currently monitored"). | **Yes** (inverse — non-empty = gap) | Yes |

### 7.2 Complete mapping (every field in `sample_organization_data.json`)

> `crit` = criticality (H/M/L). `clause` may be empty for organisation-profile fields that are pure context.

#### Organisation profile — pure context, no clause binding

| `field_path` | `entry_type` | `value_type` | Notes |
|---|---|---|---|
| `organization.name` | `reference` | string | Identity context for chat + reports |
| `organization.industry` | `reference` | string | Drives recommendation tone |
| `organization.size` | `reference` | string | — |
| `organization.location` | `reference` | string | — |
| `organization.sites[]` | `array_reference` | array<string> | Used to ground audit scope |
| `organization.primary_activities[]` | `array_reference` | array<string> | Important for clause 4.3 (scope) and 6.1.2 (aspects) |

#### `environmental_policy` — ISO clause 5.2

| `field_path` | `entry_type` | clause | crit | Detail |
|---|---|---|---|---|
| `environmental_policy.exists` | `boolean_assertion` | 5.2 | H | `expected=true` |
| `environmental_policy.document_name` | `reference` | 5.2 | — | Filename hint for retrieval |
| `environmental_policy.last_reviewed` | `freshness` | 5.2 | M | `max_age_days=730` (≤ 2 years) |
| `environmental_policy.approved_by` | `reference` | 5.1 | — | Top-management signal — agent looks for this name/title in the policy text |
| `environmental_policy.communicated_to_employees` | `boolean_assertion` | 7.4.2 | M | `expected=true` |
| `environmental_policy.publicly_available` | `boolean_assertion` | 7.4.3 | L | `expected=true` |
| `environmental_policy.commitments[]` | `array_min_items` | 5.2 | H | `min_items=3`; ISO 14001 mandates *at least* compliance + protection of environment + continual improvement. Array values are loaded as context for the agent to verify the policy actually states each commitment. |
| `environmental_policy.missing_elements[]` | `notes_signal` | 5.2 | H | Non-empty array = self-declared gap |

#### `context_and_scope` — clauses 4.1–4.3

| `field_path` | `entry_type` | clause | crit | Detail |
|---|---|---|---|---|
| `context_and_scope.ems_scope_defined` | `boolean_assertion` | 4.3 | H | `expected=true` |
| `context_and_scope.scope_description` | `reference` | 4.3 | — | Loaded into agent context to verify alignment with `organization.primary_activities` |
| `context_and_scope.interested_parties_identified` | `boolean_assertion` | 4.2 | H | `expected=true` |
| `context_and_scope.interested_parties[]` | `array_min_items` | 4.2 | H | `min_items=1`; entries `{party, requirements}` loaded as context |
| `context_and_scope.internal_external_issues_documented` | `boolean_assertion` | 4.1 | H | `expected=true` |
| `context_and_scope.notes` | `notes_signal` | 4.1 | H | Non-empty → flag |

#### `leadership` — clauses 5.1, 5.3, 9.3

| `field_path` | `entry_type` | clause | crit | Detail |
|---|---|---|---|---|
| `leadership.top_management_commitment_demonstrated` | `boolean_assertion` | 5.1 | H | `expected=true` |
| `leadership.environmental_roles_defined` | `boolean_assertion` | 5.3 | H | `expected=true` |
| `leadership.roles[]` | `array_min_items` | 5.3 | H | `min_items=1`; `{role, name, responsibilities}` — drives the *responsible_role* tagging in `missing-requirements` |
| `leadership.management_review_conducted` | `boolean_assertion` | 9.3 | H | `expected=true` |
| `leadership.last_management_review` | `freshness` | 9.3 | H | `max_age_days=365` |
| `leadership.review_frequency` | `reference` | 9.3 | — | Cross-check string ("Annual") against actual gap between reviews |

#### `planning` — clauses 6.1, 6.2, 9.1.2

| `field_path` | `entry_type` | clause | crit | Detail |
|---|---|---|---|---|
| `planning.environmental_aspects_identified` | `boolean_assertion` | 6.1.2 | H | `expected=true` |
| `planning.significant_aspects[]` | `array_min_items` | 6.1.2 | H | `min_items=1`; `{aspect, impact, significance}`. Each entry is checked against operational evidence in user docs. |
| `planning.legal_requirements_register` | `boolean_assertion` | 6.1.3 | H | `expected=true` |
| `planning.legal_register_last_updated` | `freshness` | 6.1.3 | H | `max_age_days=365` |
| `planning.compliance_evaluation_conducted` | `boolean_assertion` | 9.1.2 | H | `expected=true` |
| `planning.last_compliance_evaluation` | `freshness` | 9.1.2 | H | `max_age_days=365` |
| `planning.objectives_and_targets[]` | `array_min_items` | 6.2 | H | `min_items=1`; `{objective, target, progress}` — loaded as context to verify objectives are SMART and progress is documented |
| `planning.action_plans_for_objectives` | `boolean_assertion` | 6.2.2 | H | `expected=true` |
| `planning.risks_and_opportunities_assessed` | `boolean_assertion` | 6.1.1 | H | `expected=true` |
| `planning.notes` | `notes_signal` | 6.1.1 | H | Non-empty → flag |

#### `support` — clauses 7.1–7.5

| `field_path` | `entry_type` | clause | crit | Detail |
|---|---|---|---|---|
| `support.resources_allocated` | `boolean_assertion` | 7.1 | M | `expected=true` |
| `support.competence.training_program_exists` | `boolean_assertion` | 7.2 | H | `expected=true` |
| `support.competence.training_records_maintained` | `boolean_assertion` | 7.2 | H | `expected=true` |
| `support.competence.environmental_awareness_training` | `boolean_assertion` | 7.3 | H | `expected=true` |
| `support.competence.last_awareness_training` | `freshness` | 7.3 | M | `max_age_days=365` |
| `support.competence.role_specific_training[]` | `array_min_items` | 7.2 | M | `min_items=1`; cross-check against `leadership.roles[]` |
| `support.communication.internal_communication_process` | `boolean_assertion` | 7.4.2 | M | `expected=true` |
| `support.communication.external_communication_process` | `boolean_assertion` | 7.4.3 | M | `expected=true` |
| `support.communication.notes` | `notes_signal` | 7.4 | M | Non-empty → flag |
| `support.documented_information.document_control_procedure` | `boolean_assertion` | 7.5 | H | `expected=true` |
| `support.documented_information.records_retention_defined` | `boolean_assertion` | 7.5.3 | M | `expected=true` |
| `support.documented_information.documents_version_controlled` | `boolean_assertion` | 7.5.2 | M | `expected=true` |

#### `operations` — clauses 8.1, 8.2

| `field_path` | `entry_type` | clause | crit | Detail |
|---|---|---|---|---|
| `operations.operational_controls[]` | `array_min_items` | 8.1 | H | `min_items=1`; `{process, control, documented}` — each entry with `documented=false` becomes a partial gap |
| `operations.emergency_preparedness.emergency_procedures_exist` | `boolean_assertion` | 8.2 | H | `expected=true` |
| `operations.emergency_preparedness.procedures_cover[]` | `array_min_items` | 8.2 | H | `min_items=1`; entries loaded as context |
| `operations.emergency_preparedness.emergency_drills_conducted` | `boolean_assertion` | 8.2 | H | `expected=true` |
| `operations.emergency_preparedness.last_drill` | `freshness` | 8.2 | H | `max_age_days=365` |
| `operations.emergency_preparedness.drill_frequency` | `reference` | 8.2 | — | String like "Annual" |
| `operations.emergency_preparedness.gaps[]` | `notes_signal` | 8.2 | H | Non-empty array = self-declared scenario gaps (e.g. "No procedure for gas leak") |
| `operations.outsourced_processes_controlled` | `boolean_assertion` | 8.1 | H | `expected=true` |
| `operations.notes` | `notes_signal` | 8.1 | H | Non-empty → flag |

#### `performance_evaluation` — clauses 9.1, 9.2, 9.3

| `field_path` | `entry_type` | clause | crit | Detail |
|---|---|---|---|---|
| `performance_evaluation.monitoring_and_measurement.parameters_monitored[]` | `array_min_items` | 9.1.1 | H | `min_items=1`; `{parameter, frequency, method}` — loaded as context |
| `performance_evaluation.monitoring_and_measurement.equipment_calibrated` | `boolean_assertion` | 9.1.1 | M | `expected=true` |
| `performance_evaluation.monitoring_and_measurement.emissions_monitored` | `boolean_assertion` | 9.1.1 | H | `expected=true` |
| `performance_evaluation.monitoring_and_measurement.notes` | `notes_signal` | 9.1.1 | H | Non-empty → flag |
| `performance_evaluation.internal_audit.audit_program_exists` | `boolean_assertion` | 9.2 | H | `expected=true` |
| `performance_evaluation.internal_audit.audits_conducted` | `boolean_assertion` | 9.2 | H | `expected=true` |
| `performance_evaluation.internal_audit.last_audit_date` | `freshness` | 9.2 | H | `max_age_days=365` |
| `performance_evaluation.internal_audit.audit_frequency` | `reference` | 9.2 | — | — |
| `performance_evaluation.internal_audit.auditor_competence_defined` | `boolean_assertion` | 9.2 | M | `expected=true` |
| `performance_evaluation.internal_audit.nonconformities_from_last_audit` | `reference` | 9.2 | — | Integer — loaded as context |
| `performance_evaluation.internal_audit.nonconformities_closed` | `count_threshold` | 9.2 | M | Comparator: `nonconformities_closed >= 0.8 × nonconformities_from_last_audit`. The seeder stores `comparator="ratio_gte"`, `threshold=0.8`, `linked_reference_paths=["...nonconformities_from_last_audit"]`. |
| `performance_evaluation.management_review.conducted_regularly` | `boolean_assertion` | 9.3 | H | `expected=true` |
| `performance_evaluation.management_review.inputs_include[]` | `array_min_items` | 9.3 | H | `min_items=3`; ISO 14001 §9.3.2 lists the required inputs — array values loaded as context for completeness check |
| `performance_evaluation.management_review.outputs_documented` | `boolean_assertion` | 9.3 | H | `expected=true` |
| `performance_evaluation.management_review.actions_tracked` | `boolean_assertion` | 9.3 | H | `expected=true` |

#### `improvement` — clause 10

| `field_path` | `entry_type` | clause | crit | Detail |
|---|---|---|---|---|
| `improvement.nonconformity_procedure` | `boolean_assertion` | 10.2 | H | `expected=true` |
| `improvement.corrective_action_process` | `boolean_assertion` | 10.2 | H | `expected=true` |
| `improvement.open_corrective_actions` | `count_threshold` | 10.2 | M | `comparator="lte"`, `threshold=10`. Above threshold → backlog signal. Always loaded as context. |
| `improvement.continual_improvement_demonstrated` | `boolean_assertion` | 10.3 | M | `expected=true` |
| `improvement.improvement_examples[]` | `array_min_items` | 10.3 | M | `min_items=1`; loaded as context |

#### `certifications` — context only

| `field_path` | `entry_type` | clause | crit | Detail |
|---|---|---|---|---|
| `certifications.iso_14001_certified` | `reference` | — | — | Existing certification status (input, not output) |
| `certifications.other_certifications[]` | `array_reference` | — | — | Cross-leverage opportunities for chat |
| `certifications.certification_body` | `reference` | — | — | — |
| `certifications.notes` | `reference` | — | — | Plain context |

#### `documents_provided[]` — evidence inventory

| `field_path` | `entry_type` | clause | crit | Detail |
|---|---|---|---|---|
| `documents_provided[]` | `array_reference` | — | — | `{document, filename, date}`. Used by the document-processor to seed expected filenames; used by `missing-requirements` to detect *expected-but-not-uploaded* documents. |

### 7.3 How each entry type is consumed

| Stage | Reads | Behaviour |
|---|---|---|
| `gap-analyzer.compare_state` | All entries for the current clause + the tenant's `org_profile` values | Loads the values as JSON into the prompt, asks the model to verify them against retrieved evidence. Boolean / freshness / count / array_min_items entries produce a `state_diff` row. References enrich context only. |
| `gap-analyzer.analyse_gap` | `state_diff` + retrieved chunks | Emits `Met / Partially Met / Not Met / Insufficient Evidence` per assertion. |
| `recommendation.generate` | `iso_clauses.actionable_seeds[]` + the failing assertions + the relevant references | Reference values are injected into the recommendation prompt so suggestions cite the right people, dates, and existing commitments. |
| `missing-requirements.identify` | Failing `boolean_assertion` / `freshness` / `array_min_items` entries; `documents_provided[]` array | Produces a per-assertion request, tagged with the responsible role pulled from `org_profile.leadership.roles[]`. |
| `chat-rag.responder` | The full `org_profile` for the tenant (always-on context) | System prompt has stable identity grounding; chat answers reference the right org and roles. |

### 7.4 ISO State Template Pydantic schema

```python
from typing import Literal
from pydantic import BaseModel, Field

EntryType = Literal[
    "boolean_assertion", "freshness", "count_threshold",
    "array_min_items", "reference", "notes_signal",
]
ValueType = Literal["boolean", "string", "integer", "float", "date", "array", "object"]
Comparator = Literal["lte", "gte", "eq", "lt", "gt", "ratio_gte"]

class ISOStateEntry(BaseModel):
    field_path: str                       # JSON dotted path in the canonical org schema
    clause_id: str | None                 # may be None for pure-profile fields
    entry_type: EntryType
    value_type: ValueType
    expected: bool | None = None          # for boolean_assertion
    min_items: int | None = None          # for array_min_items
    max_age_days: int | None = None       # for freshness
    comparator: Comparator | None = None  # for count_threshold
    threshold: float | None = None        # for count_threshold
    evidence_keywords: list[str] = Field(default_factory=list)
    criticality: Literal["high", "medium", "low"] | None = None
    linked_reference_paths: list[str] = Field(default_factory=list)
    notes_field: str | None = None
    description: str = ""
```

### 7.5 Regression fixture

`tests/fixtures/sample_organization_data.json` is loaded as the demo tenant's `org_profile`. The e2e test `test_full_analysis_against_sample.py` asserts the analyser flags **exactly** these gaps and only these:

- `context_and_scope.internal_external_issues_documented` → Not Met (clause 4.1) + `context_and_scope.notes` is a notes_signal hit
- `planning.risks_and_opportunities_assessed` → Not Met (clause 6.1.1) + `planning.notes` notes_signal hit
- `support.communication.external_communication_process` → Not Met (clause 7.4.3) + `support.communication.notes` notes_signal hit
- `operations.operational_controls[]` → Partially Met (clause 8.1; the *Energy management* entry has `documented=false`)
- `operations.emergency_preparedness.gaps[]` → notes_signal hit (clause 8.2; gas-leak procedure missing)
- `operations.outsourced_processes_controlled` → Not Met (clause 8.1) + `operations.notes` notes_signal hit
- `performance_evaluation.monitoring_and_measurement.emissions_monitored` → Not Met (clause 9.1.1) + `monitoring.notes` notes_signal hit
- `performance_evaluation.internal_audit.nonconformities_closed` → Partially Met (count_threshold: 2/3 = 0.67 < 0.8)
- `improvement.open_corrective_actions=4` → reference (within threshold, not a gap, but loaded as context)
- `certifications.iso_14001_certified=false` → reference only (the *target* state, not a present gap)

---

## 8. API Contracts

All endpoints require `Authorization: Bearer <keycloak-access-token>` except `/auth/register` and `/health`.

### Auth

`POST /auth/register` is the only auth endpoint the gateway exposes. It wraps Keycloak's Admin API to atomically create both a tenant identity and the user.

```http
POST /auth/register
Content-Type: application/json
{
  "email": "officer@acme.com",
  "password": "SuperSecret!23",
  "first_name": "Jane",
  "last_name": "Doe",
  "organisation_name": "ACME Manufacturing"
}
→ 201 {
  "user_id": "users-mongo-id",
  "keycloak_sub": "f1b9e8a4-...",
  "tenant_id": "8c3f2e1a-..."
}
```

**Login, refresh, password reset, and account self-service all happen against Keycloak directly.** Clients are expected to drive the OIDC flow themselves:

```http
# Login (public client, Resource Owner Password Credentials — for testing/CLI)
POST {KEYCLOAK_URL}/realms/verdeai/protocol/openid-connect/token
Content-Type: application/x-www-form-urlencoded

grant_type=password
&client_id=verdeai-frontend
&username=officer@acme.com
&password=SuperSecret!23
&scope=openid profile email

→ 200 { "access_token": "...", "refresh_token": "...", "expires_in": 300, ... }

# Refresh
POST {KEYCLOAK_URL}/realms/verdeai/protocol/openid-connect/token
grant_type=refresh_token
&client_id=verdeai-frontend
&refresh_token=...

→ 200 { "access_token": "...", ... }

# Logout
POST {KEYCLOAK_URL}/realms/verdeai/protocol/openid-connect/logout
&client_id=verdeai-frontend
&refresh_token=...
```

Production deployments use Authorization Code + PKCE; the password grant above is for testing only and is disabled in `realm-export.json` for non-dev environments.

The access token returned by Keycloak contains the `tenant_id` claim injected by the protocol mapper. The gateway validates this token against Keycloak's JWKS (`/realms/verdeai/protocol/openid-connect/certs`) on every request.

### Documents

```http
POST /documents
Content-Type: multipart/form-data
file: <binary>
→ 202 { "document_id": "doc_...", "status": "queued", "websocket_url": "/ws/jobs/doc_..." }

GET /documents?status=ready
→ 200 { "items": [ { "document_id": "...", "filename": "...", "status": "...", "pages": 50, "uploaded_at": "..." } ] }

GET /documents/{id}
→ 200 { ...full record... }

DELETE /documents/{id}
→ 202 { "status": "deletion_queued" }
```

### Analyses

```http
POST /analyses
{ "scope": "full" }                        # or { "scope": { "clauses": ["4.1","6.1.1"] } }
→ 202 { "analysis_id": "ana_...", "status": "running", "websocket_url": "/ws/jobs/ana_..." }

GET /analyses
→ 200 { "items": [ { "analysis_id": "...", "status": "...", "started_at": "...", "completed_at": "..." } ] }

GET /analyses/{id}
→ 200 {
  "analysis_id": "...", "status": "running|completed|failed",
  "progress": { "total_clauses": 32, "completed": 12 },
  "started_at": "...", "completed_at": "..."
}

GET /analyses/{id}/gaps
→ 200 {
  "summary": { "Met": 18, "Partially Met": 7, "Not Met": 4, "Insufficient Evidence": 3 },
  "gaps": [ {
    "clause_id": "6.1.1",
    "title": "Risk and opportunity assessment",
    "decision": "Not Met",
    "confidence": 0.91,
    "evidence_summary": "...",
    "citations": [ { "document_id": "...", "filename": "...", "page": 4, "chunk_id": "..." } ],
    "missing_evidence": [ "formal risk register", "documented methodology" ]
  } ]
}

GET /analyses/{id}/recommendations
→ 200 {
  "quick_wins":        [ { "clause_id": "...", "text": "...", "effort": 1, "impact": 4 } ],
  "major_initiatives": [ { "clause_id": "...", "text": "...", "effort": 5, "impact": 5 } ],
  "standard":          [ ... ]
}

GET /analyses/{id}/missing
→ 200 { "items": [ {
  "clause_id": "...", "field_path": "planning.risks_and_opportunities_assessed",
  "responsible_role": "Environmental Manager",
  "draft_text": "To complete clause 6.1.1..."
} ] }

GET /analyses/{id}/report.pdf      → PDF binary
GET /analyses/{id}/report.json     → full JSON dump
```

### Chat

```http
POST /chat
Accept: text/event-stream
{ "session_id": "sess_...", "message": "Do we have a hazardous waste policy?" }
→ 200 SSE stream:
   data: {"type":"delta","content":"We have ..."}
   data: {"type":"delta","content":" a documented ..."}
   data: {"type":"citations","items":[{"document_id":"...","filename":"env_policy_v2.3.pdf","page":4,"chunk_id":"..."}]}
   data: {"type":"done"}
```

### WebSocket — Glass-Box

```
WS /ws/jobs/{job_id}
→ on message: { "stage": "embedding", "status": "running", "detail": "embedding 200/400 chunks" }
→ on terminal: { "stage": "complete", "status": "done" } then close
```

### Health

```http
GET /health      → 200 { "status": "ok" }
GET /readiness   → 200 if Mongo + RabbitMQ + Redis reachable
```

---

## 9. `docker-compose.yml`

```yaml
version: "3.9"

services:
  api-gateway:
    build: { context: ., dockerfile: services/api-gateway/Dockerfile }
    env_file: [.env]
    ports: ["8000:8000"]
    depends_on:
      mongodb:  { condition: service_healthy }
      rabbitmq: { condition: service_healthy }
      redis:    { condition: service_healthy }
      keycloak: { condition: service_healthy }

  document-processor:
    build: { context: ., dockerfile: services/document-processor/Dockerfile }
    env_file: [.env]
    depends_on:
      mongodb:  { condition: service_healthy }
      rabbitmq: { condition: service_healthy }
      redis:    { condition: service_healthy }
    deploy: { replicas: 2 }

  iso-knowledge:
    build: { context: ., dockerfile: services/iso-knowledge/Dockerfile }
    env_file: [.env]
    depends_on:
      mongodb:  { condition: service_healthy }
      rabbitmq: { condition: service_healthy }

  gap-analyzer:
    build: { context: ., dockerfile: services/gap-analyzer/Dockerfile }
    env_file: [.env]
    depends_on:
      mongodb:  { condition: service_healthy }
      rabbitmq: { condition: service_healthy }
      redis:    { condition: service_healthy }
    deploy: { replicas: 2 }

  recommendation:
    build: { context: ., dockerfile: services/recommendation/Dockerfile }
    env_file: [.env]
    depends_on:
      mongodb:  { condition: service_healthy }
      rabbitmq: { condition: service_healthy }

  missing-requirements:
    build: { context: ., dockerfile: services/missing-requirements/Dockerfile }
    env_file: [.env]
    depends_on:
      mongodb:  { condition: service_healthy }
      rabbitmq: { condition: service_healthy }

  chat-rag:
    build: { context: ., dockerfile: services/chat-rag/Dockerfile }
    env_file: [.env]
    ports: ["8001:8001"]
    depends_on:
      mongodb:  { condition: service_healthy }
      redis:    { condition: service_healthy }
      keycloak: { condition: service_healthy }

  mongodb:
    image: mongodb/mongodb-atlas-local:8.0
    ports: ["27017:27017"]
    volumes:
      - mongo-data:/data/db
      - ./infra/mongodb/init:/docker-entrypoint-initdb.d:ro
    healthcheck:
      test: ["CMD", "mongosh", "--quiet", "--eval", "db.adminCommand('ping')"]
      interval: 10s
      retries: 5

  rabbitmq:
    image: rabbitmq:3.13-management
    ports: ["5672:5672", "15672:15672"]
    volumes:
      - rmq-data:/var/lib/rabbitmq
      - ./infra/rabbitmq/definitions.json:/etc/rabbitmq/definitions.json:ro
      - ./infra/rabbitmq/rabbitmq.conf:/etc/rabbitmq/rabbitmq.conf:ro
    healthcheck:
      test: ["CMD", "rabbitmq-diagnostics", "ping"]
      interval: 10s
      retries: 5

  redis:
    image: redis:7-alpine
    ports: ["6379:6379"]
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      retries: 5

  keycloak:
    image: quay.io/keycloak/keycloak:26.0
    command: ["start-dev", "--import-realm"]
    environment:
      KC_BOOTSTRAP_ADMIN_USERNAME: ${KEYCLOAK_ADMIN_USER:-admin}
      KC_BOOTSTRAP_ADMIN_PASSWORD: ${KEYCLOAK_ADMIN_PASSWORD:-admin}
      KC_HEALTH_ENABLED: "true"
      KC_HOSTNAME: localhost
      KC_HOSTNAME_STRICT: "false"
      KC_HTTP_ENABLED: "true"
      KC_PROXY_HEADERS: "xforwarded"
    ports:
      - "8080:8080"      # admin console + token endpoint
      - "9000:9000"      # health/management
    volumes:
      - ./infra/keycloak/realm-export.json:/opt/keycloak/data/import/realm.json:ro
      - keycloak-data:/opt/keycloak/data
    healthcheck:
      test: ["CMD-SHELL", "exec 3<>/dev/tcp/127.0.0.1/9000 || exit 1"]
      interval: 10s
      timeout: 5s
      retries: 15
      start_period: 30s

volumes:
  mongo-data:
  rmq-data:
  keycloak-data:
```

`docker-compose.override.yml` adds bind-mounted source for hot-reload during development.

> **Production note:** Keycloak runs in `start-dev` (H2 file-backed DB) for local convenience. For staging/production, switch to `start` mode with a managed Postgres backing store (`KC_DB=postgres`, `KC_DB_URL=...`), put Keycloak behind the same TLS-terminating reverse proxy as the API, and disable the password grant in the realm export.

---

## 10. `.env.example`

```bash
# --- Core ---
ENVIRONMENT=development
LOG_LEVEL=INFO
SERVICE_NAME=                              # set per service

# --- Keycloak ---
KEYCLOAK_URL=http://keycloak:8080                           # internal cluster URL
KEYCLOAK_PUBLIC_URL=http://localhost:8080                   # what end-user clients see (token endpoint, redirects)
KEYCLOAK_REALM=verdeai
KEYCLOAK_FRONTEND_CLIENT_ID=verdeai-frontend                # public client
KEYCLOAK_ADMIN_CLIENT_ID=verdeai-admin                      # confidential client used by api-gateway
KEYCLOAK_ADMIN_CLIENT_SECRET=                               # set after first realm import
KEYCLOAK_ADMIN_USER=admin                                   # bootstrap admin (Keycloak's own admin, not realm user)
KEYCLOAK_ADMIN_PASSWORD=admin
KEYCLOAK_JWKS_CACHE_TTL_SECONDS=3600
KEYCLOAK_TOKEN_LEEWAY_SECONDS=10                            # clock-skew tolerance for exp/nbf checks

# --- MongoDB ---
MONGO_URI=mongodb://mongodb:27017/?directConnection=true
MONGO_DB=verdeai
VECTOR_INDEX_NAME=chunks_vector_idx
ISO_VECTOR_INDEX_NAME=iso_clauses_vector_idx

# --- RabbitMQ ---
RABBITMQ_URL=amqp://guest:guest@rabbitmq:5672/

# --- Redis ---
REDIS_URL=redis://redis:6379/0

# --- OpenRouter (single LLM gateway for all completion calls) ---
OPENROUTER_API_KEY=
OPENROUTER_APP_URL=https://verdeai.local
OPENROUTER_APP_NAME=VerdeAI
PRIMARY_REASONING_MODEL=deepseek/deepseek-r1-0528
CHEAP_REASONING_MODEL=qwen/qwen3-coder
VISION_MODEL=mistralai/mistral-small-3.1-24b-instruct
LLM_MAX_RETRIES=3

# --- Voyage AI (direct API — embeddings + reranking) ---
VOYAGE_API_KEY=
VOYAGE_EMBEDDING_MODEL=voyage-3-large
VOYAGE_RERANKER_MODEL=rerank-2.5
EMBEDDING_DIMENSIONS=1024

# --- Tavily (web search for ISO seeding) ---
TAVILY_API_KEY=

# --- Observability ---
LANGFUSE_PUBLIC_KEY=
LANGFUSE_SECRET_KEY=
LANGFUSE_HOST=https://cloud.langfuse.com
OTEL_EXPORTER_OTLP_ENDPOINT=
OTEL_SERVICE_NAME=

# --- Service URLs (intra-cluster) ---
CHAT_RAG_URL=http://chat-rag:8001

# --- Tuning ---
EMBED_BATCH_SIZE=128
RETRIEVAL_TOP_K=30
RERANK_TOP_K=8
CHUNK_TARGET_TOKENS=512
CHUNK_OVERLAP_TOKENS=64
```

---

## 11. Build Phases

Build in order. Each phase ships independently. Acceptance criteria are mandatory.

### Phase 0 — Bootstrap

**Tasks:**
1. Create the repo skeleton from §2.
2. Implement `shared/verdeai_shared/{settings,logging,db,messaging,auth}` minimally.
   - `auth/jwks.py` — fetches and caches Keycloak JWKS (TTL from `KEYCLOAK_JWKS_CACHE_TTL_SECONDS`); refreshes once on `kid` miss.
   - `auth/token.py` — validates bearer tokens (signature + `iss` + `aud` + `exp`); returns `Principal`.
   - `auth/principal.py` — Pydantic model.
   - `auth/tenant.py` — context var + `get_current_principal()` FastAPI dependency that also writes `tenant_id` into the request-scoped contextvar.
   - `auth/keycloak_admin.py` — `python-keycloak` admin client (used by `api-gateway` only).
3. Implement `infra/keycloak/realm-export.json` per §3.1: realm `verdeai`, two clients, protocol mapper for `tenant_id`, two roles, one seed user.
4. Implement `api-gateway` with `/auth/register`, `/health`, `/readiness`. Registration calls Keycloak Admin API to create the user with a fresh `tenant_id` UUID, then upserts a `users` row.
5. Compose with mongodb, rabbitmq, redis, **keycloak**. Init scripts + realm import run automatically.
6. Smoke test: `make test-auth` script that registers a user, fetches a token from Keycloak, hits a protected gateway endpoint, asserts 200.

**Acceptance:**
- `make up` brings the stack up; `/health` and `/readiness` return 200 for the gateway.
- Keycloak admin console reachable at `http://localhost:8080`; the `verdeai` realm is present with both clients and the `tenant-id-mapper` mapper.
- `POST /auth/register` creates a user in Keycloak with a `tenant_id` attribute and a corresponding row in Mongo `users`.
- Authenticating against `{KEYCLOAK_URL}/realms/verdeai/protocol/openid-connect/token` (password grant) returns an access token whose decoded body contains a top-level `tenant_id` claim.
- Hitting any protected gateway endpoint with that token returns 200; without a token returns 401; with a tampered token returns 401; with a token whose `tenant_id` claim is missing returns 403.
- `mypy --strict` and `ruff check` pass.

---

### Phase 1 — Document upload + dedup

**Tasks:**
1. `api-gateway`: `POST/GET/DELETE /documents` endpoints.
2. `document-processor`: implement Stage 1 only (SHA-256 + pHash + FastCDC dedup).
3. `hash_store` and `documents` collections.
4. WebSocket `/ws/jobs/{job_id}` and Redis pubsub glass-box channel.
5. Glass-box emits `dedup.start`, `dedup.done`.

**Acceptance:**
- Uploading the same file twice returns `status=deduped` on the second attempt without re-running the pipeline.
- WebSocket emits at least one progress message per upload.

---

### Phase 2 — Docling parsing

**Tasks:**
1. Stage 2 of `document-processor`: Docling integration; persist `DoclingDocument` JSON in GridFS.
2. Update `documents` row with `docling_blob_ref`, `pages`.

**Acceptance:**
- A 50-page PDF parses end-to-end in < 60 s in CI.
- A fixture-based regression test asserts that 10 representative PDFs produce stable structural hashes between runs.

---

### Phase 3 — Chunking, contextualisation, embedding, indexing

**Tasks:**
1. Stages 3–6 of `document-processor`.
2. `chunks` collection + `chunks_vector_idx` vector search index.
3. `bm25_indexes` collection with per-tenant serialised BM25.
4. `shared/retrieval/{embedder,bm25,vector_search,hybrid}.py`.
5. Per-document summary cached in `documents.summary` (one Qwen3-Coder call per document) so the per-chunk contextualisation prompt stays under 2 K input tokens.
6. Optional Anthropic prompt-caching code path enabled in `openrouter_client.py` — activates automatically if the configured model is `anthropic/*`, no-op otherwise.

**Acceptance:**
- For a tenant with one ingested document, hybrid retrieval returns plausible top-10 for both keyword and semantic queries.
- Average per-chunk contextualisation token usage ≤ 2 K input + 80 output, verified through Langfuse traces.
- Total ingest cost for a 50-page PDF ≤ $0.05 on the default DeepSeek/Qwen/Mistral stack (verified against the OpenRouter usage dashboard).

---

### Phase 4 — ISO knowledge seeding

**Tasks:**
1. `iso-knowledge` service.
2. `seeds/iso_14001_summaries.md` — paraphrased summaries for ~32 clauses.
3. `seeds/org_state_template.json` — copy of `sample_organization_data.json`.
4. `tooling/seed_iso.py` populates:
   - `iso_clauses` (with embeddings) — one row per ISO clause.
   - `iso_state_template` — every field in the JSON, classified per §7.2 into the six entry types.
   - `org_profile` for the demo tenant — every leaf value imported from the sample JSON, tagged `source="default"`.
5. Tavily-based actionable seed enrichment; cached per clause.

**Acceptance:**
- `make seed-iso` produces ≥ 30 `iso_clauses` rows, the full `iso_state_template` row set covering every leaf field in the sample JSON, and a populated `org_profile` for the demo tenant.
- Each entry-type count is sane: ≥ 35 `boolean_assertion`, ≥ 8 `freshness`, ≥ 2 `count_threshold`, ≥ 12 `array_min_items`, ≥ 10 `reference`, ≥ 8 `notes_signal`.
- Each clause has ≥ 3 `actionable_seeds[]` entries.
- The Pydantic round-trip test passes: every row deserialises into `ISOStateEntry` cleanly.

---

### Phase 5 — Gap-analyser MVP (single clause)

**Tasks:**
1. `gap-analyzer` service with LangGraph + MongoDB checkpointer.
2. Implement all graph nodes (§4.4) but only the `pop_next_clause` loop body for one clause at a time on demand.
3. `state_store` and `result_store` collections.
4. Glass-box emits per node.

**Acceptance:**
- `POST /analyses` with `scope: { clauses: ["6.1.1"] }` against a synthetic tenant yields a `Met / Not Met` result with at least one citation pointing to a real chunk.
- Killing the worker mid-run resumes from the last completed node on restart.

---

### Phase 6 — Full gap-analyser + glass-box

**Tasks:**
1. Loop the LangGraph over all 32 clauses for `scope=full`.
2. Glass-box stream emits at every node transition.
3. Concurrency: gap-analyzer scales to N replicas; analyses are partitionable per-tenant.

**Acceptance:**
- A full analysis on a 5-document tenant completes in < 3 minutes.
- The WebSocket emits ≥ 1 status message per clause.
- The known-gap regression test against `sample_organization_data.json` produces exactly the gap set listed in §7.5 — no false positives, no false negatives.

---

### Phase 7 — Recommendation + missing-requirements

**Tasks:**
1. `recommendation` service with the 3-node graph.
2. `missing-requirements` service.
3. `recommendation_store`, `missing_request_store` collections.
4. `GET /analyses/{id}/recommendations` and `/missing` endpoints in `api-gateway`.

**Acceptance:**
- After a full analysis, every `Not Met` clause has ≥ 1 recommendation.
- Recommendations are correctly classified `quick_win` / `major_initiative` / `standard` per the §4.5 rules.
- Each missing requirement carries a sensible `responsible_role`.

---

### Phase 8 — Chat RAG

**Tasks:**
1. `chat-rag` FastAPI service with SSE.
2. Hybrid retrieve + rerank + Sonnet streaming.
3. Memory: short-term + long-term summary.
4. Citation enforcement and post-stream verification.
5. `api-gateway` proxies SSE chunks.

**Acceptance:**
- First-token latency < 3 s, end-to-end < 10 s for typical queries.
- Every assertive sentence has a citation; chat refuses if grounding is missing.
- Follow-up questions correctly resolve pronouns ("does it cover hazardous waste?").

---

### Phase 9 — Reports + hardening

**Tasks:**
1. PDF report generator with WeasyPrint (`/analyses/{id}/report.pdf`).
2. JSON export (`/analyses/{id}/report.json`).
3. RAGAS-based eval harness under `tooling/eval/`.
4. Load test harness under `tooling/load_test.py`.
5. Chaos test: `docker kill rabbitmq` mid-analysis must resume cleanly.
6. `Right to be forgotten`: `DELETE /documents/{id}` removes chunks, hash entries, BM25 entries, and tombstones the document.

**Acceptance:**
- PDF renders with executive summary + per-clause table + recommendations.
- RAGAS scores: `faithfulness ≥ 0.85`, `answer_relevance ≥ 0.80`, `context_precision ≥ 0.75` on the synthetic test set.
- Chaos test passes — the analysis completes after broker restart.
- Coverage ≥ 80 % per service.

---

## 12. Makefile (target list)

```
make up               # docker compose up -d --build
make down             # docker compose down
make logs s=<svc>     # follow logs for one service
make seed-iso         # run tooling/seed_iso.py
make test             # pytest across all services
make test-e2e         # bring up compose, run tests/e2e
make lint             # ruff check + mypy --strict
make fmt              # ruff format
make clean            # remove volumes
```