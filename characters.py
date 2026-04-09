
import json
import os
from dataclasses import dataclass, field

from config import CHARACTERS_DIR, DEFAULT_CHARACTER


@dataclass
class PhotoReaction:
    triggers: list[str]  
    file: str   
    caption: str = ""   


@dataclass
class Character:
    id: str
    system_prompt: str
    knowledge_dir: str 
    collection_name: str 
    photos: list[PhotoReaction] = field(default_factory=list)

    def match_photo(self, text: str) -> PhotoReaction | None:
        """Первая реакция, чьи триггеры нашлись в тексте."""
        low = text.lower()
        for p in self.photos:
            for t in p.triggers:
                if t and t.lower() in low:
                    return p
        return None


def _load_photos(base_dir: str) -> list[PhotoReaction]:
    config_path = os.path.join(base_dir, "photos.json")
    photos_dir = os.path.join(base_dir, "photos")
    if not os.path.exists(config_path):
        return []
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            raw = json.load(f)
    except Exception as e:
        print(f"  {config_path}: не удалось прочитать ({e})")
        return []

    result: list[PhotoReaction] = []
    for item in raw:
        file_rel = item.get("file", "")
        file_path = os.path.join(photos_dir, file_rel)
        if not os.path.exists(file_path):
            print(f"  photos.json: файл не найден {file_path}")
            continue
        triggers = [t for t in item.get("triggers", []) if isinstance(t, str)]
        if not triggers:
            continue
        result.append(PhotoReaction(
            triggers=triggers,
            file=file_path,
            caption=item.get("caption", "") or "",
        ))
    return result


def _legacy_root() -> Character | None:
    """Старая раскладка"""
    if os.path.exists("system_prompt.txt") and os.path.isdir("knowledge"):
        with open("system_prompt.txt", "r", encoding="utf-8") as f:
            prompt = f.read().strip()
        return Character(
            id=DEFAULT_CHARACTER,
            system_prompt=prompt or "Ты — персонаж. Отвечай в его образе.",
            knowledge_dir="knowledge",
            collection_name=f"character_{DEFAULT_CHARACTER}",
            photos=_load_photos("."),
        )
    return None


def _load_from_dir(char_id: str) -> Character | None:
    base = os.path.join(CHARACTERS_DIR, char_id)
    if not os.path.isdir(base):
        return None
    prompt_file = os.path.join(base, "system_prompt.txt")
    knowledge_dir = os.path.join(base, "knowledge")
    if not os.path.exists(prompt_file):
        return None
    with open(prompt_file, "r", encoding="utf-8") as f:
        prompt = f.read().strip()
    return Character(
        id=char_id,
        system_prompt=prompt or "Ты — персонаж. Отвечай в его образе.",
        knowledge_dir=knowledge_dir if os.path.isdir(knowledge_dir) else "",
        collection_name=f"character_{char_id}",
        photos=_load_photos(base),
    )


def list_characters() -> list[str]:
    ids: list[str] = []
    if os.path.isdir(CHARACTERS_DIR):
        for name in sorted(os.listdir(CHARACTERS_DIR)):
            full = os.path.join(CHARACTERS_DIR, name)
            if os.path.isdir(full) and os.path.exists(os.path.join(full, "system_prompt.txt")):
                ids.append(name)
    if not ids and _legacy_root() is not None:
        ids.append(DEFAULT_CHARACTER)
    return ids


def load_character(char_id: str) -> Character:
    char = _load_from_dir(char_id)
    if char is not None:
        return char
    if char_id == DEFAULT_CHARACTER:
        legacy = _legacy_root()
        if legacy is not None:
            return legacy
    raise ValueError(f"Персонаж '{char_id}' не найден. Доступные: {list_characters()}")
