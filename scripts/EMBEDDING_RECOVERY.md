# Embedding recovery

The previous Gemini migration reused globally unique LangChain row IDs. That could
overwrite local vectors without moving rows to the Gemini collection. Collection
counts alone cannot detect this damage.

The migration now writes only to the dedicated physical table
`public.langchain_pg_embedding_gemini`, using INSERT ONLY SQL.
ID conflicts never update existing vectors. Exact stored documents and metadata are copied without splitting.
Completed rows are skipped on rerun. Each API batch is committed separately
so a later quota error does not lose earlier progress. Existing populated targets
are scoped by model, dimensions, and source collection.

From the project root, inspect (no API requests or writes):

```powershell
python scripts/repair_ollama_embeddings.py
python scripts/migrate_gemini_embeddings.py
```

Repair the non-unit local vectors identified during this incident:

```powershell
python scripts/repair_ollama_embeddings.py --apply
```

The repair saves original rows under `data/embedding-repair-backups/` before
writing. It embeds the exact stored text with the configured Ollama embedding
model and updates only the vector, checking that the row has not changed.
No rows, collections, or tables are deleted. No transcript files are read.
Rerunning skips vectors already repaired to unit length.

Non-unit length identifies suspected damage in this incident, but cannot prove
that every unit vector came from Ollama. For complete regeneration of all local
vectors use `--apply --all` (much slower on CPU). Keep the original embedding model
and backup files until verification is complete.

After local repair, populate the separate Gemini table:

```powershell
python scripts/migrate_gemini_embeddings.py --apply
```

This uses Gemini API quota. If quota is exhausted, rerun after quota resets;
already saved chunks are skipped. Local vectors are preserved. Successful
migration alone is not an end-to-end cloud answer test: check cloud retrieval
and generation separately before relying on cloud mode.
