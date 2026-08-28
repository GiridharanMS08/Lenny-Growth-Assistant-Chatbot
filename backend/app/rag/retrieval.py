import json
import re
from functools import lru_cache
from pathlib import Path

import faiss
import numpy as np
import yaml
from rank_bm25 import BM25Okapi
from sentence_transformers import CrossEncoder, SentenceTransformer

from app.config import settings
from app.logging_config import backend_logger


# ============================================================
# SEMANTIC CHUNKING
# ============================================================

def semantic_chunk_markdown(text: str, source_title: str = "", max_words: int = 350, min_words: int = 60):
    """
    Chunk Markdown documents by:

    1. Markdown section headers
    2. Paragraph boundaries
    3. Sentence boundaries for very large paragraphs

    Each chunk keeps the document title and section heading
    as contextual information.
    """
    chunks = []

    # Split document when a Markdown heading starts
    sections = re.split(r"(?=^#{1,6}\s+)", text, flags=re.MULTILINE)

    for section in sections:
        section = section.strip()
        if not section:
            continue

        lines = section.splitlines()
        heading = ""

        # Extract the Markdown heading
        if lines and re.match(r"^#{1,6}\s+", lines[0]):
            heading = re.sub(r"^#{1,6}\s+", "", lines[0]).strip()
            content = "\n".join(lines[1:]).strip()
        else:
            content = section.strip()

        if not content:
            continue

        # Split by paragraph boundaries
        paragraphs = re.split(r"\n\s*\n+", content)

        # Clean paragraphs
        cleaned_paragraphs = []
        for paragraph in paragraphs:
            paragraph = re.sub(r"\s+", " ", paragraph).strip()
            if paragraph:
                cleaned_paragraphs.append(paragraph)

        # ----------------------------------------------------
        # Split very large paragraphs by sentence boundaries
        # ----------------------------------------------------
        processed_paragraphs = []
        for paragraph in cleaned_paragraphs:
            if len(paragraph.split()) <= max_words:
                processed_paragraphs.append(paragraph)
                continue

            # Split large paragraph into sentences
            sentences = re.split(r"(?<=[.!?])\s+", paragraph)
            current_sentences = []
            current_word_count = 0

            for sentence in sentences:
                sentence = sentence.strip()
                if not sentence:
                    continue

                sentence_word_count = len(sentence.split())

                # If adding this sentence exceeds the chunk size
                if current_sentences and current_word_count + sentence_word_count > max_words:
                    processed_paragraphs.append(" ".join(current_sentences))
                    current_sentences = []
                    current_word_count = 0

                current_sentences.append(sentence)
                current_word_count += sentence_word_count

            if current_sentences:
                processed_paragraphs.append(" ".join(current_sentences))

        # ----------------------------------------------------
        # Combine paragraphs into semantic chunks
        # ----------------------------------------------------
        current_parts = []
        current_word_count = 0

        for paragraph in processed_paragraphs:
            paragraph_word_count = len(paragraph.split())

            # Create a new chunk only at a semantic boundary
            if current_parts and current_word_count + paragraph_word_count > max_words:
                chunk_body = "\n\n".join(current_parts).strip()
                if len(chunk_body.split()) >= min_words:
                    prefix = ""
                    if source_title:
                        prefix += f"Document: {source_title}\n"
                    if heading:
                        prefix += f"Section: {heading}\n\n"
                    chunks.append(prefix + chunk_body)

                current_parts = []
                current_word_count = 0

            current_parts.append(paragraph)
            current_word_count += paragraph_word_count

        # Save the final chunk in this section
        if current_parts:
            chunk_body = "\n\n".join(current_parts).strip()
            if len(chunk_body.split()) >= min_words:
                prefix = ""
                if source_title:
                    prefix += f"Document: {source_title}\n"
                if heading:
                    prefix += f"Section: {heading}\n\n"
                chunks.append(prefix + chunk_body)

    return chunks


# ============================================================
# RETRIEVER
# ============================================================

class Retriever:
    def __init__(self):
        self.model = None
        self.reranker = None
        self.index = None
        self.chunks = []
        self.bm25 = None
        self._load()

    # ========================================================
    # EMBEDDING MODEL
    # ========================================================
    def _ensure_model(self):
        if self.model is None:
            self.model = SentenceTransformer(settings.embedding_model)
        return self.model

    # ========================================================
    # RERANKER
    # ========================================================
    def _ensure_reranker(self):
        if self.reranker is None:
            self.reranker = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2")
        return self.reranker

    # ========================================================
    # TOKENIZATION FOR BM25
    # ========================================================
    @staticmethod
    @lru_cache(maxsize=4096)
    def _tokenize(text: str):
        return re.findall(r"\b\w+\b", text.lower())

    # ========================================================
    # BUILD BM25
    # ========================================================
    def _build_bm25(self):
        if self.chunks:
            corpus = [self._tokenize(doc["text"]) for doc in self.chunks]
            self.bm25 = BM25Okapi(corpus)
        else:
            self.bm25 = None

    # ========================================================
    # LOAD EXISTING FAISS INDEX
    # ========================================================
    def _load(self):
        p = Path(settings.index_dir)
        faiss_file = p / "index.faiss"
        chunks_file = p / "chunks.json"

        if faiss_file.exists() and chunks_file.exists():
            self.index = faiss.read_index(str(faiss_file))
            self.chunks = json.loads(chunks_file.read_text(encoding="utf-8"))
            self._build_bm25()

    # ========================================================
    # INGEST DOCUMENTS
    # ========================================================
    def ingest(self):
        root = Path(settings.transcript_dir)
        docs = []

        for path in root.rglob("*.md"):
            print(f"Processing: {path.name}")
            text = path.read_text(encoding="utf-8", errors="ignore")
            metadata = {}

            # ------------------------------------------------
            # EXTRACT YAML FRONTMATTER
            # ------------------------------------------------
            if text.startswith("---"):
                parts = text.split("---", 2)
                if len(parts) == 3:
                    try:
                        metadata = yaml.safe_load(parts[1]) or {}
                    except yaml.YAMLError:
                        metadata = {}
                    text = parts[2]

            # ------------------------------------------------
            # SEMANTIC CHUNKING
            # ------------------------------------------------
            title = metadata.get("title", path.stem)
            semantic_chunks = semantic_chunk_markdown(text=text, source_title=title, max_words=350, min_words=60)

            # ------------------------------------------------
            # CREATE DOCUMENT RECORDS
            # ------------------------------------------------
            for chunk_number, chunk in enumerate(semantic_chunks):
                docs.append({
                    "text": chunk,
                    "source": {
                        "guest": metadata.get("guest"),
                        "title": title,
                        "publish_date": metadata.get("publish_date"),
                        "path": str(path),
                        "chunk_number": chunk_number,
                    },
                })

        # ----------------------------------------------------
        # VALIDATE DOCUMENTS
        # ----------------------------------------------------
        if not docs:
            raise RuntimeError(f"No markdown files found in {root}")

        print(f"Created {len(docs)} semantic chunks")

        # ----------------------------------------------------
        # CREATE EMBEDDINGS
        # ----------------------------------------------------
        model = self._ensure_model()
        vectors = model.encode([doc["text"] for doc in docs], normalize_embeddings=True, show_progress_bar=True)
        vectors = np.asarray(vectors, dtype="float32")

        # ----------------------------------------------------
        # CREATE FAISS INDEX
        # ----------------------------------------------------
        index = faiss.IndexFlatIP(vectors.shape[1])
        index.add(vectors)

        # ----------------------------------------------------
        # SAVE INDEX
        # ----------------------------------------------------
        p = Path(settings.index_dir)
        p.mkdir(parents=True, exist_ok=True)
        faiss.write_index(index, str(p / "index.faiss"))

        # Save semantic chunks + metadata
        (p / "chunks.json").write_text(json.dumps(docs, ensure_ascii=False, default=str, indent=2), encoding="utf-8")

        # Update running retriever
        self.index = index
        self.chunks = docs
        self._build_bm25()
        self._search_cached.cache_clear()

        print("FAISS index and chunks saved successfully")
        return len(docs)

    # ========================================================
    # QUERY TYPE GATING
    # ========================================================
    def _is_knowledge_query(self, query: str) -> bool:
        """Avoid expensive retrieval for obvious casual/unrelated chat."""
        q = query.lower().strip()

        if not q:
            return False

        casual_patterns = [
            r"^(hi|hello|hey|thanks|thank you|good morning|good evening)[!. ]*$",
            r"^i (love|like|hate) ",
            r"^(what('?s| is) your name|how are you|who are you)[?!. ]*$",
        ]

        if any(re.match(pattern, q) for pattern in casual_patterns):
            return False

        topic_terms = {
            "product", "growth", "startup", "saas", "leadership",
            "hiring", "team", "strategy", "retention", "activation",
            "conversion", "pricing", "market", "customer", "user",
            "founder", "manager", "management", "roadmap", "experiment",
            "experimentation", "product-market", "pmf", "acquisition",
            "monetization", "sales", "marketing", "career", "lenny",
            "podcast", "ship 30", "ship30"
        }

        tokens = set(self._tokenize(q))
        return bool(tokens & topic_terms) or len(q.split()) >= 4

    # ========================================================
    # HYBRID SEARCH + RERANKING
    # ========================================================
    def search(self, query: str, k: int | None = None):
        return self._search_cached(query.strip(), k)

    @lru_cache(maxsize=256)
    def _search_cached(self, query: str, k: int | None = None):
        if self.index is None or not self.chunks:
            return []

        # Avoid expensive embedding + reranking for casual chat.
        if not self._is_knowledge_query(query):
            return []

        final_k = k or settings.top_k
        started = __import__("time").perf_counter()

        # High recall candidate pool, kept small enough for local CPU use.
        candidate_k = min(max(final_k * 4, 12), len(self.chunks))

        # ----------------------------------------------------
        # 1. VECTOR SEARCH
        # ----------------------------------------------------
        q = self._ensure_model().encode(
            [query],
            normalize_embeddings=True
        )

        vector_scores, vector_ids = self.index.search(
            np.asarray(q, dtype="float32"),
            candidate_k
        )

        vector_results = {
            int(idx): {
                "score": float(score),
                "rank": rank + 1,
            }
            for rank, (score, idx) in enumerate(
                zip(vector_scores[0], vector_ids[0])
            )
            if idx >= 0
        }

        # ----------------------------------------------------
        # 2. BM25 SEARCH
        # ----------------------------------------------------
        bm25_results = {}

        if self.bm25 is not None:
            query_tokens = self._tokenize(query)

            if query_tokens:
                bm25_scores = self.bm25.get_scores(query_tokens)

                top_bm25_ids = np.argsort(bm25_scores)[
                    -candidate_k:
                ][::-1]

                bm25_results = {
                    int(idx): {
                        "score": float(bm25_scores[idx]),
                        "rank": rank + 1,
                    }
                    for rank, idx in enumerate(top_bm25_ids)
                    if bm25_scores[idx] > 0
                }

        # ----------------------------------------------------
        # 3. RRF FUSION
        # ----------------------------------------------------
        # Reciprocal Rank Fusion combines lexical + semantic ranks
        # without needing to normalize incompatible score scales.
        rrf_k = 60
        fused_scores = {}

        for idx, item in vector_results.items():
            fused_scores[idx] = fused_scores.get(idx, 0.0) + (
                1.0 / (rrf_k + item["rank"])
            )

        for idx, item in bm25_results.items():
            fused_scores[idx] = fused_scores.get(idx, 0.0) + (
                1.0 / (rrf_k + item["rank"])
            )

        if not fused_scores:
            return []

        # Keep only the strongest hybrid candidates for reranking.
        candidate_ids = [
            idx
            for idx, _ in sorted(
                fused_scores.items(),
                key=lambda x: x[1],
                reverse=True
            )[:candidate_k]
        ]

        # ----------------------------------------------------
        # 4. CROSS-ENCODER RERANKING
        # ----------------------------------------------------
        reranker = self._ensure_reranker()

        pairs = [
            (query, self.chunks[idx]["text"])
            for idx in candidate_ids
        ]

        rerank_scores = reranker.predict(
            pairs,
            show_progress_bar=False
        )

        ranked = sorted(
            zip(candidate_ids, rerank_scores),
            key=lambda x: float(x[1]),
            reverse=True
        )

        # ----------------------------------------------------
        # 5. RELEVANCE GATE
        # ----------------------------------------------------
        if not ranked:
            return []

        best_score = float(ranked[0][1])

        # Keep configurable; CrossEncoder logits are model-specific.
        threshold = getattr(
            settings,
            "min_rerank_score",
            None
        )

        # Apply the gate only when explicitly configured.
        # Do not assume a universal CrossEncoder score cutoff.
        if threshold is not None and best_score < threshold:
            return []

        # ----------------------------------------------------
        # 6. FINAL RESULTS
        # ----------------------------------------------------
        results = [
            {
                **self.chunks[idx],
                "score": float(score),
                "vector_score": (
                    vector_results.get(idx, {}).get("score")
                ),
                "bm25_score": (
                    bm25_results.get(idx, {}).get("score")
                ),
                "rrf_score": fused_scores.get(idx),
            }
            for idx, score in ranked[:final_k]
        ]

        elapsed_ms = (__import__("time").perf_counter() - started) * 1000
        backend_logger.info(
            "retrieval query_chars=%d hits=%d elapsed_ms=%.1f cache=miss",
            len(query),
            len(results),
            elapsed_ms,
        )
        return results


# ============================================================
# GLOBAL RETRIEVER
# ============================================================

retriever = Retriever()