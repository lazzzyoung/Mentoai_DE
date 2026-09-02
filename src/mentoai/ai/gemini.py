from typing import Any

from pydantic import BaseModel

from mentoai.config import get_settings

_client: Any | None = None


async def get_client() -> Any:
    global _client
    if _client is None:
        from google import genai

        _client = genai.Client(api_key=get_settings().google_api_key)
    return _client


async def generate_structured[T: BaseModel](prompt: str, schema: type[T]) -> T:
    """Gemini 구조화 출력(response_schema)으로 Pydantic 객체를 직접 받는다."""
    client = await get_client()
    response = await client.aio.models.generate_content(
        model=get_settings().gemini_model,
        contents=prompt,
        config={
            "response_mime_type": "application/json",
            "response_schema": schema,
        },
    )
    parsed = response.parsed
    if parsed is None:
        raise RuntimeError(f"Gemini 응답 파싱 실패: {response.text!r}")
    return parsed
