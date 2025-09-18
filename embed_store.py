import csv
import time
import requests
import chromadb
import pickle
import os
from chromadb.config import Settings
from tqdm import tqdm

JINA_API_KEY = os.getenv("JINA_API_KEY")
CSV_FILE = os.getenv("CSV_FILE", "train.csv")
COLLECTION_NAME = os.getenv("COLLECTION_NAME", "news_articles")
BATCH_SIZE = int(os.getenv("BATCH_SIZE", 16))
START_ROW = int(os.getenv("START_ROW", 0))
MAX_RETRIES = 3
TIMEOUT = 30

# Chroma
client = chromadb.PersistentClient(path=os.getenv("CHROMA_DIR", "./chroma_store"))
collection = client.get_or_create_collection(name=COLLECTION_NAME)

# Jina embeddings
def get_embeddings(texts):
    url = "https://api.jina.ai/v1/embeddings"
    headers = {
        "Authorization": f"Bearer {JINA_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "input": texts,
        "model": "jina-embeddings-v2-base-en"
    }

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = requests.post(url, headers=headers, json=payload, timeout=TIMEOUT)
            response.raise_for_status()
            data = response.json()
            return [d["embedding"] for d in data["data"]]
        except requests.exceptions.Timeout:
            print(f"Timeout on attempt {attempt}/{MAX_RETRIES}, retrying...")
        except requests.exceptions.RequestException as e:
            print(f"Request failed ({attempt}/{MAX_RETRIES}): {e}")
        time.sleep(2 * attempt)
    raise RuntimeError("Failed to fetch embeddings after retries.")
with open(CSV_FILE, newline='', encoding="utf-8") as csvfile:
    reader = list(csv.DictReader(csvfile))
    reader = reader[START_ROW:]
    with tqdm(total=len(reader), desc=f"Processing rows (starting at {START_ROW})", unit="row") as pbar:
        for start in range(0, len(reader), BATCH_SIZE):
            batch = reader[start:start + BATCH_SIZE]

            ids = [str(i + start + START_ROW) for i in range(len(batch))]
            titles = [row.get("Title", "Untitled") for row in batch]
            descriptions = [row.get("Description", "") for row in batch]
            metadatas = [{"title": t, "class_index": row.get("Class Index")} for t, row in zip(titles, batch)]

            valid_idx = [i for i, desc in enumerate(descriptions) if desc.strip()]
            if not valid_idx:
                pbar.update(len(batch))
                continue

            texts = [descriptions[i] for i in valid_idx]
            batch_ids = [ids[i] for i in valid_idx]
            batch_metadatas = [metadatas[i] for i in valid_idx]

          
            embeddings = get_embeddings(texts)

     
            collection.add(
                ids=batch_ids,
                embeddings=embeddings,
                documents=texts,
                metadatas=batch_metadatas
            )
            with open("embeddings.pkl", "ab") as f:
                pickle.dump({
                    "ids": batch_ids,
                    "embeddings": embeddings,
                    "documents": texts,
                    "metadatas": batch_metadatas
                }, f)
            pbar.update(len(batch))

print(f"\nFinished! Total items in collection '{COLLECTION_NAME}': {collection.count()}")
