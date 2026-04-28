// Vector Search indexes are created programmatically at service startup
// via verdeai_shared/db/indexes.py using Motor's create_search_index().
//
// They cannot be reliably created here because:
//   1. createSearchIndex() is async in mongodb-atlas-local (builds in background)
//   2. The Atlas search engine may not be ready during initdb.d execution
//
// Indexes created at runtime: chunks_vector_idx, iso_clauses_vector_idx
print("verdeai: vector indexes will be created at service startup.");
