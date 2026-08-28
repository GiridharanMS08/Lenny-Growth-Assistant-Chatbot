# Lenny-Growth-Assistant-Chatbot
I built a local RAG-based assistant that lets users ask questions and retrieve relevant evidence from the transcript corpus

Lenny Growth Assistant is a local AI-powered RAG application that helps users answer product, growth, startup, and leadership questions using Lenny’s Podcast transcripts.

It combines FAISS semantic search, BM25 keyword search, RRF, and Cross-Encoder reranking to retrieve relevant evidence, then uses local Ollama LLM inference to generate grounded answers with source citations. It also supports HTML artifact generation, PostgreSQL conversation persistence, and developer diagnostics for retrieval and performance monitoring.
