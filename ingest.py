
import glob
import os
import sys

import chromadb
from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction
from langchain_text_splitters import RecursiveCharacterTextSplitter

from characters import load_character, list_characters
from config import CHROMA_DIR, CHUNK_SIZE, CHUNK_OVERLAP, EMBEDDING_MODEL


def _splitter() -> RecursiveCharacterTextSplitter:
    return RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
        separators=["\n\n", "\n", ". ", " ", ""],
        length_function=len,
    )


def ingest_character(char_id: str, client: chromadb.PersistentClient, embedding_fn) -> int:
    char = load_character(char_id)
    print(f"\n→ Персонаж: {char.id}")

    if not char.knowledge_dir or not os.path.isdir(char.knowledge_dir):
        print(f"  Папка знаний не найдена: {char.knowledge_dir!r}. Пропускаю.")
        return 0

    txt_files = sorted(glob.glob(os.path.join(char.knowledge_dir, "*.txt")))
    if not txt_files:
        print(f"  В {char.knowledge_dir}/ нет .txt файлов. Пропускаю.")
        return 0

    try:
        client.delete_collection(char.collection_name)
    except Exception:
        pass
    collection = client.create_collection(
        name=char.collection_name,
        embedding_function=embedding_fn,
        metadata={"hnsw:space": "cosine"},
    )

    splitter = _splitter()
    total = 0
    for filepath in txt_files:
        filename = os.path.basename(filepath)
        category = os.path.splitext(filename)[0]
        with open(filepath, "r", encoding="utf-8") as f:
            text = f.read()
        if not text.strip():
            print(f"  {filename} — пустой, пропускаю")
            continue
        chunks = splitter.split_text(text)
        print(f"  {filename}: {len(chunks)} чанков")
        collection.add(
            documents=chunks,
            ids=[f"{char.id}_{category}_{i}" for i in range(len(chunks))],
            metadatas=[
                {"source": filename, "category": category, "chunk_index": i, "character": char.id}
                for i in range(len(chunks))
            ],
        )
        total += len(chunks)
    print(f"  {total} чанков → коллекция {char.collection_name}")
    return total


def main():
    print(f"Загружаю модель эмбеддингов ({EMBEDDING_MODEL})...")
    embedding_fn = SentenceTransformerEmbeddingFunction(model_name=EMBEDDING_MODEL)
    client = chromadb.PersistentClient(path=CHROMA_DIR)

    if len(sys.argv) > 1:
        targets = [sys.argv[1]]
    else:
        targets = list_characters()
        if not targets:
            print("Не найдено ни одного персонажа.")
            print("Создайте characters/<id>/system_prompt.txt + characters/<id>/knowledge/*.txt")
            return

    grand_total = 0
    for cid in targets:
        try:
            grand_total += ingest_character(cid, client, embedding_fn)
        except Exception as e:
            print(f"  Ошибка для {cid}: {e}")

    print(f"\nГотово. Всего чанков: {grand_total} → {CHROMA_DIR}/")


if __name__ == "__main__":
    main()
