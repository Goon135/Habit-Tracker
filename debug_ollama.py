"""Диагностика: пробуем разные варианты запроса к Ollama,
чтобы понять, на каком именно Ollama даёт 503."""
import asyncio
import traceback
from ollama import AsyncClient

client = AsyncClient(host="http://localhost:11434")
MODEL = "llama3.1:8b"


async def test(name, **kwargs):
    print(f"\n=== {name} ===")
    try:
        response = await client.chat(model=MODEL, **kwargs)
        print(f"OK: {response.message.content[:80]!r}")
        if response.message.tool_calls:
            print(f"   tool_calls: {response.message.tool_calls}")
    except Exception as e:
        print(f"FAIL: {type(e).__name__}: {e!r}")
        for attr in ("status_code", "error", "body"):
            if hasattr(e, attr):
                print(f"   exc.{attr} = {getattr(e, attr)!r}")


async def main():
    # Тест 1: минимальный запрос — как curl
    await test(
        "минимум",
        messages=[{"role": "user", "content": "скажи привет"}],
    )

    # Тест 2: + system prompt (как у coach)
    await test(
        "система+юзер",
        messages=[
            {"role": "system", "content": "Ты — коуч."},
            {"role": "user", "content": "скажи привет"},
        ],
    )

    # Тест 3: + options (как у coach)
    await test(
        "options",
        messages=[{"role": "user", "content": "скажи привет"}],
        options={"temperature": 0.7, "num_predict": 512},
    )

    # Тест 4: tools (как у extractor) — главное подозрение
    tool = {
        "type": "function",
        "function": {
            "name": "save_habits",
            "description": "Сохранить привычки.",
            "parameters": {
                "type": "object",
                "properties": {
                    "habits": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "name": {"type": "string"},
                            },
                            "required": ["name"],
                        },
                    },
                },
                "required": ["habits"],
            },
        },
    }
    await test(
        "tools (упрощённая схема)",
        messages=[{"role": "user", "content": "хочу бегать по утрам"}],
        tools=[tool],
    )

    # Тест 5: tools + options + system (полный набор как у extractor)
    await test(
        "tools+options+system",
        messages=[
            {"role": "system", "content": "Ты парсер. Вызывай save_habits."},
            {"role": "user", "content": "хочу бегать по утрам"},
        ],
        tools=[tool],
        options={"temperature": 0.0},
    )


if __name__ == "__main__":
    asyncio.run(main())