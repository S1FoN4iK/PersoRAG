
import logging
from typing import AsyncIterator

import chromadb
from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction
import litellm

import storage
from characters import Character, load_character, list_characters
from config import (
    CHROMA_DIR, EMBEDDING_MODEL, MODEL, MAX_TOKENS, TOP_K, RELEVANCE_THRESHOLD,
    LLM_BASE_URL, LLM_API_KEY, DEFAULT_CHARACTER,
)

logger = logging.getLogger(__name__)


class CharacterChat:
    def __init__(self):
        self._embedding_fn = SentenceTransformerEmbeddingFunction(model_name=EMBEDDING_MODEL)
        self._client = chromadb.PersistentClient(path=CHROMA_DIR)
        self._characters: dict[str, Character] = {}
        self._collections: dict[str, chromadb.Collection] = {}

        ids = list_characters()
        if not ids:
            raise RuntimeError(
                "Не найдено ни одного персонажа. Создайте characters/<id>/system_prompt.txt "
                "и characters/<id>/knowledge/, затем запусти ingest.py."
            )
        for cid in ids:
            self._characters[cid] = load_character(cid)
            try:
                self._collections[cid] = self._client.get_collection(
                    name=self._characters[cid].collection_name,
                    embedding_function=self._embedding_fn,
                )
            except Exception:
                logger.warning(
                    f"Коллекция для персонажа '{cid}' не найдена в Chroma. "
                    f"Запустите `python ingest.py {cid}` (или без аргумента для всех)."
                )

        logger.info(f"Загружено персонажей: {list(self._characters.keys())}")

    # ── публичный API ────────────────────────────────────

    def available_characters(self) -> list[str]:
        return list(self._characters.keys())

    def get_user_character(self, user_id: str) -> str:
        cid = storage.get_user_character(user_id, DEFAULT_CHARACTER)
        if cid not in self._characters:
            cid = next(iter(self._characters))
            storage.set_user_character(user_id, cid)
        return cid

    def character(self, character_id: str) -> Character:
        return self._characters[character_id]

    def set_user_character(self, user_id: str, character_id: str) -> None:
        if character_id not in self._characters:
            raise ValueError(f"Нет такого персонажа: {character_id}")
        storage.set_user_character(user_id, character_id)
        storage.clear_history(user_id, character_id) 

    def clear_history(self, user_id: str) -> None:
        cid = self.get_user_character(user_id)
        storage.clear_history(user_id, cid)

    def total_chunks(self) -> int:
        return sum(c.count() for c in self._collections.values())

    def debug_context(self, user_id: str, query: str) -> str:
        cid = self.get_user_character(user_id)
        return self._retrieve(cid, query) or "(ничего не найдено)"

    async def reply(self, user_id: str, message: str) -> str:
        """Неблокирующая генерация, возвращает полный ответ."""
        messages, cid = self._prepare(user_id, message)
        response = await litellm.acompletion(
            model=MODEL,
            messages=messages,
            max_tokens=MAX_TOKENS,
            api_base=LLM_BASE_URL or None,
            api_key=LLM_API_KEY or None,
        )
        text = response.choices[0].message.content or ""
        storage.add_message(user_id, cid, "user", message)
        storage.add_message(user_id, cid, "assistant", text)
        usage = getattr(response, "usage", None)
        if usage:
            logger.info(
                f"Токены: prompt={usage.prompt_tokens} "
                f"completion={usage.completion_tokens} total={usage.total_tokens}"
            )
        return text

    async def reply_stream(self, user_id: str, message: str) -> AsyncIterator[str]:
        """Стрим дельт. В конце сохраняет полный ответ в историю."""
        messages, cid = self._prepare(user_id, message)
        stream = await litellm.acompletion(
            model=MODEL,
            messages=messages,
            max_tokens=MAX_TOKENS,
            stream=True,
            api_base=LLM_BASE_URL or None,
            api_key=LLM_API_KEY or None,
        )
        full = []
        async for chunk in stream:
            try:
                delta = chunk.choices[0].delta.content or ""
            except (AttributeError, IndexError):
                delta = ""
            if delta:
                full.append(delta)
                yield delta
        text = "".join(full)
        storage.add_message(user_id, cid, "user", message)
        storage.add_message(user_id, cid, "assistant", text)

    # ── внутреннее ───────────────────────────────────────

    def _prepare(self, user_id: str, message: str) -> tuple[list[dict], str]:
        cid = self.get_user_character(user_id)
        context = self._retrieve(cid, message)
        system = self._build_system_prompt(self._characters[cid].system_prompt, context)
        chunk_count = len(context.split("\n\n---\n\n")) if context else 0
        logger.info(f"[{cid}] RAG: {chunk_count} чанков")

        history = storage.get_history(user_id, cid)
        return (
            [{"role": "system", "content": system}]
            + history
            + [{"role": "user", "content": message}],
            cid,
        )

    def _retrieve(self, character_id: str, query: str) -> str:
        collection = self._collections.get(character_id)
        if collection is None:
            return ""
        results = collection.query(
            query_texts=[query],
            n_results=TOP_K,
            include=["documents", "metadatas", "distances"],
        )
        if not results["documents"] or not results["documents"][0]:
            return ""
        chunks = []
        for doc, meta, dist in zip(
            results["documents"][0],
            results["metadatas"][0],
            results["distances"][0],
        ):
            if dist > RELEVANCE_THRESHOLD:
                continue
            source = (meta or {}).get("category", "unknown")
            chunks.append(f"[{source}] {doc}")
        return "\n\n---\n\n".join(chunks)

    @staticmethod
    def _build_system_prompt(base: str, context: str) -> str:
        if not context:
            return base
        return (
            f"{base}\n\n"
            "<character_knowledge>\n"
            "Ниже — фрагменты из базы знаний персонажа. Используй эту информацию "
            "для точного и последовательного отыгрыша. Не выдумывай факты, которых "
            "нет в базе знаний. Если информации недостаточно — импровизируй в рамках "
            "установленного характера.\n\n"
            f"{context}\n"
            "</character_knowledge>"
        )
