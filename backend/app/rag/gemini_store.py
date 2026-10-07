"""Dedicated Gemini storage; original LangChain tables are never written here."""
import psycopg

from app.rag.embeddings import to_sync_database_url

TABLE = "public.langchain_pg_embedding_gemini"


def connect(url):
    conn = psycopg.connect(to_sync_database_url(url).replace("postgresql+psycopg://", "postgresql://", 1), connect_timeout=30)
    conn.execute("SET search_path TO public, extensions")
    return conn


def create_table(conn):
    if conn.execute("SELECT to_regclass(%s)", (TABLE,)).fetchone()[0]:
        if conn.execute("SELECT obj_description(%s::regclass)", (TABLE,)).fetchone()[0] != "lenny-gemini-v1":
            raise ValueError("Unrecognized existing Gemini table; refusing to modify it.")
        return
    conn.execute("""CREATE TABLE public.langchain_pg_embedding_gemini (
        source_id text NOT NULL, source_collection text NOT NULL,
        embedding_model text NOT NULL, dimensions integer NOT NULL,
        document text NOT NULL, cmetadata jsonb, embedding vector NOT NULL,
        PRIMARY KEY(source_collection,embedding_model,dimensions,source_id),
        CHECK(vector_dims(embedding)=dimensions))""")
    conn.execute("COMMENT ON TABLE public.langchain_pg_embedding_gemini IS 'lenny-gemini-v1'")
    conn.execute("ALTER TABLE public.langchain_pg_embedding_gemini ENABLE ROW LEVEL SECURITY")


def search(settings, vector, top_k):
    with connect(settings.database_url) as conn:
        conn.execute("SET TRANSACTION READ ONLY")
        return conn.execute("""SELECT document,cmetadata,1-(embedding <=> %s::vector)
            FROM public.langchain_pg_embedding_gemini
            WHERE source_collection=%s AND embedding_model=%s AND dimensions=%s
            ORDER BY embedding <=> %s::vector LIMIT %s""",
            (str(vector), settings.vector_collection_name, settings.gemini_embedding_model,
             settings.gemini_embedding_dimensions, str(vector), top_k)).fetchall()
