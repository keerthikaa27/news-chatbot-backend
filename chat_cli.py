# chat_cli.py
import os
import sys
import time
import requests
import textwrap
import chromadb

from chromadb.config import Settings

# ---------- Config (change if needed) ----------
JINA_API_KEY = os.getenv("JINA_API_KEY")  # set this in PowerShell before running
CHROMA_DIR = os.getenv("CHROMA_DIR", "./chroma_store")  # change to your chroma path if needed
COLLECTION_NAME = os.getenv("COLLECTION_NAME", "news_articles")
TOP_K = 5

if not JINA_API_KEY:
    print("ERROR: Please set the JINA_API_KEY environment variable before running.")
    print(r'In PowerShell: $env:JINA_API_KEY="your_jina_api_key_here"')
    sys.exit(1)

# ---------- Connect to persisted Chroma ----------
try:
    # use PersistentClient (works when Chroma persisted)
    client = chromadb.PersistentClient(path=CHROMA_DIR)
    collection = client.get_or_create_collection(COLLECTION_NAME)
except Exception as e:
    print("ERROR: Could not open Chroma collection. Check CHROMA_DIR and that Chroma persisted properly.")
    print("CHROMA_DIR=", CHROMA_DIR)
    print("Exception:", e)
    sys.exit(1)

count = collection.count()
if count == 0:
    print(f"WARNING: collection '{COLLECTION_NAME}' appears empty (count=0).")
    print("If you expect data, double-check CHROMA_DIR or where you persisted the collection.")
    # we continue so you can still test, but retrieval will return nothing

# ---------- Jina embedding helper ----------
def jina_embed(texts):
    url = "https://api.jina.ai/v1/embeddings"
    headers = {
        "Authorization": f"Bearer {JINA_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {"input": texts, "model": "jina-embeddings-v2-base-en"}
    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        return [d["embedding"] for d in data["data"]]
    except Exception as e:
        print("Error calling Jina embeddings:", e)
        return [None] * len(texts)

# ---------- Simple CLI loop ----------
print("\n=== RAG chat CLI (retrieval-only demo) ===")
print("Type a question and hit Enter. Type 'exit' or 'quit' to stop.\n")
print(f"Using Chroma path: {CHROMA_DIR}   (collection: {COLLECTION_NAME})")
print(f"Documents in collection: {count}\n")

while True:
    try:
        user_q = input("You: ").strip()
    except (KeyboardInterrupt, EOFError):
        print("\nExiting. Bye!")
        break

    if not user_q:
        continue
    if user_q.lower() in ("exit", "quit"):
        print("Goodbye!")
        break

    t0 = time.time()
    # 1) get embedding for the query
    emb = jina_embed([user_q])[0]
    if emb is None:
        print("Failed to get embedding. Try again or check your JINA_API_KEY.")
        continue

    # 2) query Chroma for top-k
    try:
        results = collection.query(query_embeddings=[emb], n_results=TOP_K)
    except Exception as e:
        print("Error querying Chroma:", e)
        print("If you see a dimension mismatch, verify that the ingestion used the same embedding model.")
        continue

    docs = results.get("documents", [[]])[0]
    metas = results.get("metadatas", [[]])[0]
    dists = results.get("distances", [[]])[0]

    if not docs:
        print("(No relevant documents found.)\n")
        continue

    # 3) display retrieved snippets
    print(f"\nRetrieved top {len(docs)} passages (showing title + snippet):\n")
    for i, (doc, meta, dist) in enumerate(zip(docs, metas, dists), start=1):
        title = meta.get("title", "Untitled") if isinstance(meta, dict) else str(meta)
        snippet = doc.replace("\n", " ").strip()
        snippet = textwrap.shorten(snippet, width=400, placeholder=" ...")
        print(f"{i}. {title}  (distance={dist:.4f})")
        print(f"   {snippet}\n")

    # 4) naive "assistant" — short synthesized answer (placeholder for Gemini)
    #    We'll just combine the top 2 snippets and shorten them for now.
    combined = " ".join(docs[:2])
    naive_answer = textwrap.shorten(combined.replace("\n", " ").strip(), width=500, placeholder="...")
    print("Assistant (naive summary from retrieved snippets):")
    print(naive_answer)
    print("\nSources:", ", ".join([ (m.get("title") if isinstance(m, dict) else str(m)) for m in metas[:TOP_K] ]))
    print(f"(Query+retrieve took {time.time()-t0:.2f}s)\n")
