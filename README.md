Newsify - Backend

This is the backend for a RAG-powered news chatbot. It implements a REST API to handle news queries, session history, and resets, integrating a Retrieval-Augmented Generation (RAG) pipeline with 12k+ news articles.

Tech Stack

Node.js/Express: REST API for chat, history, and session management.
Python: Handles news ingestion (embed_store.py) and query processing (chat_query.py).
ChromaDB: Vector store for 12k+ news article embeddings.
Jina Embeddings: Free-tier jina-embeddings-v2-base-en for text embeddings.
Google Gemini: gemini-1.5-flash for answer generation.
Redis: In-memory storage for session history with TTL.

Features

RAG Pipeline: Ingests 12k+ news articles from a test.csv file, embeds with Jina, stores in ChromaDB, retrieves top-5 passages, and generates answers with Gemini.

REST API:
POST /chat: Processes queries, returns Gemini responses.
GET /history/:sessionId: Fetches session chat history from Redis.
DELETE /history/:sessionId: Clears session history.


Session Management: Stores per-session history in Redis with 3600s TTL.
Caching: Cache warming pre-queries popular terms for faster responses.
Error Handling: Retries for Gemini 503 errors, fallbacks for empty retrievals.

Setup Instructions

Clone Repository:git clone <backend-repo-url>
cd <backend-repo>


Install Node Dependencies:npm install express cors redis body-parser axios dotenv


Install Python Dependencies:pip install chromadb news-please requests


Set Environment Variables:Create .env:GEMINI_API_KEY=your_gemini_api_key
JINA_API_KEY=your_jina_api_key
CHROMA_DIR=../chroma_store


Run Redis:Start Redis locally (redis-server) or configure redis.createClient() for your setup.
Ingest News:python embed_store.py

Runs on http://localhost:5000.

Project Structure
index.js           # Express API, Redis integration, cache warming
chat_query.py      # RAG pipeline: Chroma retrieval, Gemini calls
embed_store.py     # News ingestion and embedding
.env.example       # Template for environment variables

How It Works

RAG Pipeline: embed_store.py scrapes news from test.csv file, embeds articles with Jina, and stores in ChromaDB (../chroma_store). chat_query.py retrieves top-5 passages for queries and calls Gemini for answers, with fallbacks for empty retrievals.
API Flow: index.js handles /chat (spawns chat_query.py), /history/:sessionId (fetches Redis history), and /history/:sessionId DELETE (clears session). Session IDs are UUIDs from frontend.
Caching: Redis stores chat history (session:uuid) with 3600s TTL. Cache warming pre-queries popular terms on startup.
Error Handling: Retries Gemini 503 errors (3 attempts, exponential backoff), logs to stderr, returns clean responses.

Caching & Performance

Redis TTL: Chat history is stored in Redis with a 3600-second (1-hour) TTL per session (session:uuid), ensuring automatic cleanup of inactive sessions.
Cache Warming: On startup, index.js pre-queries popular terms ("latest news on india", "india economy", "modi policies") to warm ChromaDB and Gemini caches, reducing latency for common queries. Warmup session is cleared to avoid Redis clutter.
Optimization: Efficient Python subprocess calls, minimal Redis operations, and ChromaDB persistence ensure low latency for 12k+ article corpus.


