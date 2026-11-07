# engine/llm.py
"""Опционально: OpenAI-совместимый API. Если нет ключа — блок скрыт (return None)."""
import os, json


def opinion(summary: dict, blocks_top30: list, checks: list) -> str | None:
    key = os.getenv("LLM_API_KEY")
    if not key: return None
    try:
        from openai import OpenAI
        client = OpenAI(api_key=key, base_url=os.getenv("LLM_BASE_URL"))
        payload = {"summary": summary, "blocks": blocks_top30[:30], "checks": checks}
        r = client.chat.completions.create(
            model=os.getenv("LLM_MODEL", "gpt-4o-mini"),
            messages=[{"role": "system", "content": "Ты аналитик СПР. Кратко: на что обратить внимание."},
                      {"role": "user", "content": json.dumps(payload, ensure_ascii=False)[:12000]}],
        )
        return r.choices[0].message.content
    except Exception:
        return None
