-- Separate from LangChain/Ollama tables: BGE vectors are exactly 384 dimensions.
-- Supabase may have the vector extension in the extensions schema.
set search_path = public, extensions;
create extension if not exists vector;

create table if not exists public.transcript_chunks_cloud (
  id uuid primary key,
  content text not null,
  metadata jsonb not null default '{}'::jsonb,
  embedding vector(384) not null,
  updated_at timestamptz not null default now()
);

create index if not exists transcript_chunks_cloud_embedding_hnsw
  on public.transcript_chunks_cloud using hnsw (embedding vector_cosine_ops);

alter table public.transcript_chunks_cloud enable row level security;

create or replace function public.match_transcript_chunks(
  query_embedding vector(384),
  match_count integer default 5,
  min_similarity real default 0.30
)
returns table (id uuid, content text, metadata jsonb, similarity real)
language sql
stable
set search_path = public, extensions
as $$
  select c.id, c.content, c.metadata,
         (1 - (c.embedding <=> query_embedding))::real as similarity
  from public.transcript_chunks_cloud c
  where 1 - (c.embedding <=> query_embedding) >= min_similarity
  order by c.embedding <=> query_embedding
  limit least(greatest(match_count, 1), 20);
$$;

-- The Railway backend uses the service-role key; never expose that key to the frontend.
grant usage on schema public to service_role;
grant select, insert, update on public.transcript_chunks_cloud to service_role;
revoke all on public.transcript_chunks_cloud from anon, authenticated;
revoke execute on function public.match_transcript_chunks(vector(384), integer, real) from public, anon, authenticated;
grant execute on function public.match_transcript_chunks(vector(384), integer, real) to service_role;

notify pgrst, 'reload schema';
