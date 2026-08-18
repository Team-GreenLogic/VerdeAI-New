// MongoDB init script: create collections with schema validation and indexes
// Runs automatically via docker-entrypoint-initdb.d

const db = db.getSiblingDB("verdeai");

// Helper to create collection if it doesn't exist
function ensureCollection(name) {
  const cols = db.getCollectionNames();
  if (!cols.includes(name)) {
    db.createCollection(name);
    print("Created collection: " + name);
  }
}

// Collections
const collections = [
  "users",
  "tenants",
  "documents",
  "chunks",
  "bm25_indexes",
  "iso_clauses",
  "iso_state_template",
  "org_profile",
  "state_store",
  "result_store",
  "recommendation_store",
  "missing_request_store",
  "analyses",
  "chat_history",
  "chat_memory_summary",
  "hash_store",
  "langgraph_checkpoints",
];

collections.forEach(ensureCollection);

// Indexes
// users
db.users.createIndex({ keycloak_sub: 1 }, { unique: true, background: true });
db.users.createIndex({ tenant_id: 1 }, { background: true });

// documents
db.documents.createIndex({ tenant_id: 1, sha256: 1 }, { background: true });
db.documents.createIndex({ tenant_id: 1, status: 1 }, { background: true });

// chunks
db.chunks.createIndex({ tenant_id: 1, document_id: 1 }, { background: true });
db.chunks.createIndex({ tenant_id: 1, created_at: 1 }, { background: true });
db.chunks.createIndex({ tenant_id: 1, superseded: 1, superseded_at: 1 }, { background: true });

// bm25_indexes
db.bm25_indexes.createIndex({ tenant_id: 1 }, { unique: true, background: true });

// iso_clauses
db.iso_clauses.createIndex({ clause_id: 1 }, { unique: true, background: true });

// iso_state_template
db.iso_state_template.createIndex({ field_path: 1 }, { unique: true, background: true });
db.iso_state_template.createIndex({ clause_id: 1 }, { background: true });

// org_profile
db.org_profile.createIndex({ tenant_id: 1, field_path: 1 }, { unique: true, background: true });

// state_store
db.state_store.createIndex({ tenant_id: 1, clause_id: 1 }, { unique: true, background: true });

// result_store
db.result_store.createIndex({ analysis_id: 1 }, { background: true });
db.result_store.createIndex(
  { tenant_id: 1, analysis_id: 1, clause_id: 1 },
  { unique: true, background: true }
);

// recommendation_store
db.recommendation_store.createIndex({ analysis_id: 1, priority: 1 }, { background: true });

// missing_request_store
db.missing_request_store.createIndex({ analysis_id: 1 }, { background: true });

// analyses
db.analyses.createIndex({ tenant_id: 1, status: 1 }, { background: true });

// chat_history
db.chat_history.createIndex(
  { tenant_id: 1, session_id: 1, created_at: 1 },
  { background: true }
);

// chat_memory_summary
db.chat_memory_summary.createIndex(
  { tenant_id: 1, session_id: 1 },
  { unique: true, background: true }
);

// hash_store
db.hash_store.createIndex({ tenant_id: 1, sha256: 1 }, { unique: true, background: true });

print("verdeai: all collections and indexes created.");
