
import asyncio

from rag import CharacterChat

USER_ID = "cli_user"


async def _amain():
    print("Загружаю RAG движок...")
    engine = CharacterChat()
    print(f"База: {engine.total_chunks()} чанков")
    print(f"Персонажи: {engine.available_characters()}")
    print(f"Текущий: {engine.get_user_character(USER_ID)}\n")
    print("=" * 50)
    print("Команды: /debug <текст>, /clear, /character <id>, /quit")
    print("=" * 50 + "\n")

    while True:
        try:
            user_input = input("Ты: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nПока!")
            return

        if not user_input:
            continue
        if user_input == "/quit":
            return
        if user_input == "/clear":
            engine.clear_history(USER_ID)
            print("История очищена.\n")
            continue
        if user_input.startswith("/character"):
            parts = user_input.split(maxsplit=1)
            if len(parts) == 1:
                print(f"Текущий: {engine.get_user_character(USER_ID)}")
                print(f"Доступные: {engine.available_characters()}\n")
            else:
                try:
                    engine.set_user_character(USER_ID, parts[1].strip())
                    print(f"Переключено на {parts[1].strip()}\n")
                except ValueError as e:
                    print(f"Ошибка: {e}\n")
            continue
        if user_input.startswith("/debug"):
            query = user_input[6:].strip() or "тест"
            print(f"\n--- Контекст для «{query}» ---")
            print(engine.debug_context(USER_ID, query))
            print("--- конец ---\n")
            continue

        try:
            response = await engine.reply(USER_ID, user_input)
            print(f"\nПерсонаж: {response}\n")
        except Exception as e:
            print(f"\nОшибка: {e}\n")


def main():
    asyncio.run(_amain())


if __name__ == "__main__":
    main()
