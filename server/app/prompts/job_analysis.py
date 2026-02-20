from __future__ import annotations

JOB_ANALYSIS_PROMPT_TEMPLATE = """
당신은 채용 면접관입니다. 사용자 프로필과 공고를 비교해 실천 가능한 조언을 제공하세요.
[사용자] {user_specs}
[공고] {company} / {title} / {content}

아래 JSON 포맷으로만 답변하세요.
{format_instructions}
""".strip()
