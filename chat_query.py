import sys
import os
import chromadb
from chromadb.config import Settings
import requests
import time
import traceback

CHROMA_DIR = os.getenv("CHROMA_DIR", "chroma_store")
COLLECTION_NAME = "news_articles"
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
MAX_RETRIES = 3
RETRY_DELAY = 5  # Start with 5s, exponential backoff

if GEMINI_API_KEY is None:
    sys.stderr.write("Error: GEMINI_API_KEY not set\n")
    sys.exit(1)

#Chroma Connection
client = chromadb.Client(Settings(persist_directory=CHROMA_DIR))
collection = client.get_or_create_collection(name=COLLECTION_NAME)

# --- Retrieve docs from Chroma ---
def retrieve_docs(query, n_results=5):
    try:
        results = collection.query(query_texts=[query], n_results=n_results, include=["documents", "metadatas"])
        if results and results['documents'] and len(results['documents'][0]) > 0:
            return [
                {"text": doc, "metadata": meta}
                for doc, meta in zip(results['documents'][0], results['metadatas'][0])
            ]
    except Exception as e:
        sys.stderr.write(f"Chroma error: {e}\n")
    return []

#Gemini API 
def call_gemini(query, retrieved_docs):
    # Construct prompt
    prompt_text = (
        "You are a news assistant. Answer the query using the provided news snippets. "
        "Cite relevant details from the snippets (e.g., 'Snippet 1 reported...'). "
        "If snippets are insufficient or unrelated, supplement with a concise summary based on your knowledge up to September 2025. "
        "Keep the answer engaging, factual, and under 200 words.\n\n"
    )
    if retrieved_docs:
        prompt_text += "News Snippets:\n"
        for i, doc in enumerate(retrieved_docs, 1):
            prompt_text += f"Snippet {i} ({doc['metadata'].get('title', 'Untitled')}): {doc['text']}\n"
    else:
        prompt_text += f"No relevant snippets found for '{query}'. Provide a general summary of recent developments.\n"
    prompt_text += f"\nQuery: {query}\nAnswer:"

    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"
    headers = {"Content-Type": "application/json"}
    payload = {
        "contents": [{"parts": [{"text": prompt_text}]}]
    }

    delay = RETRY_DELAY
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = requests.post(url, headers=headers, json=payload, timeout=60)
            response.raise_for_status()
            data = response.json()
            if "candidates" in data and data["candidates"]:
                return data["candidates"][0]["content"]["parts"][0]["text"].strip()
            else:
                sys.stderr.write(f"Unexpected Gemini response: {data}\n")
                return "No valid response from Gemini."
        except requests.exceptions.HTTPError as e:
            if response.status_code == 503:
                sys.stderr.write(f"Attempt {attempt}/{MAX_RETRIES}: 503 overload, retrying in {delay}s...\n")
                if attempt < MAX_RETRIES:
                    time.sleep(delay)
                    delay *= 2
                    continue
            sys.stderr.write(f"Gemini HTTP error: {e}\nResponse: {response.text}\n")
            return f"Error: Service temporarily unavailable. Try again soon."
        except Exception as e:
            sys.stderr.write(f"Gemini request failed: {traceback.format_exc()}\n")
            return "Error connecting to Gemini."

#Main CLI
if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(1)
    query = sys.argv[1]
    docs = retrieve_docs(query)
    answer = call_gemini(query, docs)
    print(answer)