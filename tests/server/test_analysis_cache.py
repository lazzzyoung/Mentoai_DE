import asyncio

from server.app.services import rag_v3_service


async def _reset_analysis_state() -> None:
    await rag_v3_service.close_resources()


def test_analyze_job_detail_uses_cache(monkeypatch) -> None:
    asyncio.run(_reset_analysis_state())

    calls = {"count": 0}

    async def fake_fetch_user_info(_user_id: int):
        return {
            "username": "테스트",
            "desired_job": "데이터 엔지니어",
            "career_years": 3,
            "skills": ["Python", "SQL"],
        }

    async def fake_fetch_job_detail(_job_id: int):
        return {
            "job_id": 11,
            "company": "MentoAI",
            "title": "Data Engineer",
            "full_text": "경력 3년 이상, Python, SQL",
            "skills_text": "Python, SQL",
        }

    async def fake_get_llm():
        return object()

    async def fake_run_llm_analysis(_llm, _query_text: str, _job: dict):
        calls["count"] += 1
        return {
            "job_title": "Data Engineer",
            "company_name": "MentoAI",
            "current_score": 73,
            "max_score": 100,
            "analysis_summary": "요약",
            "required_tech_stack": ["Python", "SQL"],
            "action_plan": [
                {
                    "category": "프로젝트",
                    "item_name": "테스트",
                    "description": "테스트",
                    "expected_score_up": 5,
                }
            ],
            "interview_tip": "팁",
        }

    monkeypatch.setattr(rag_v3_service, "fetch_user_info", fake_fetch_user_info)
    monkeypatch.setattr(rag_v3_service.job_repository, "fetch_job_detail", fake_fetch_job_detail)
    monkeypatch.setattr(rag_v3_service, "_get_llm", fake_get_llm)
    monkeypatch.setattr(rag_v3_service, "_run_llm_analysis", fake_run_llm_analysis)

    first = asyncio.run(rag_v3_service.analyze_job_detail(11, 1))
    second = asyncio.run(rag_v3_service.analyze_job_detail(11, 1))

    assert calls["count"] == 1
    assert first == second


def test_analyze_job_detail_deduplicates_inflight(monkeypatch) -> None:
    asyncio.run(_reset_analysis_state())

    calls = {"count": 0}

    async def fake_fetch_user_info(_user_id: int):
        return {
            "username": "테스트",
            "desired_job": "데이터 엔지니어",
            "career_years": 3,
            "skills": ["Python", "SQL"],
        }

    async def fake_fetch_job_detail(_job_id: int):
        return {
            "job_id": 22,
            "company": "MentoAI",
            "title": "Data Engineer",
            "full_text": "경력 3년 이상, Python, SQL",
            "skills_text": "Python, SQL",
        }

    async def fake_get_llm():
        return object()

    async def fake_run_llm_analysis(_llm, _query_text: str, _job: dict):
        calls["count"] += 1
        await asyncio.sleep(0.05)
        return {
            "job_title": "Data Engineer",
            "company_name": "MentoAI",
            "current_score": 73,
            "max_score": 100,
            "analysis_summary": "요약",
            "required_tech_stack": ["Python", "SQL"],
            "action_plan": [
                {
                    "category": "프로젝트",
                    "item_name": "테스트",
                    "description": "테스트",
                    "expected_score_up": 5,
                }
            ],
            "interview_tip": "팁",
        }

    monkeypatch.setattr(rag_v3_service, "fetch_user_info", fake_fetch_user_info)
    monkeypatch.setattr(rag_v3_service.job_repository, "fetch_job_detail", fake_fetch_job_detail)
    monkeypatch.setattr(rag_v3_service, "_get_llm", fake_get_llm)
    monkeypatch.setattr(rag_v3_service, "_run_llm_analysis", fake_run_llm_analysis)

    async def _run_two() -> tuple[dict, dict]:
        return await asyncio.gather(
            rag_v3_service.analyze_job_detail(22, 1),
            rag_v3_service.analyze_job_detail(22, 1),
        )

    first, second = asyncio.run(_run_two())

    assert calls["count"] == 1
    assert first == second


def test_analyze_job_detail_refreshes_when_user_profile_changes(monkeypatch) -> None:
    asyncio.run(_reset_analysis_state())

    calls = {"count": 0}
    state = {"career_years": 2}

    async def fake_fetch_user_info(_user_id: int):
        return {
            "username": "테스트",
            "desired_job": "데이터 엔지니어",
            "career_years": state["career_years"],
            "skills": ["Python", "SQL"],
        }

    async def fake_fetch_job_detail(_job_id: int):
        return {
            "job_id": 33,
            "company": "MentoAI",
            "title": "Data Engineer",
            "full_text": "경력 3년 이상, Python, SQL",
            "skills_text": "Python, SQL",
        }

    async def fake_get_llm():
        return object()

    async def fake_run_llm_analysis(_llm, query_text: str, _job: dict):
        calls["count"] += 1
        return {
            "job_title": "Data Engineer",
            "company_name": "MentoAI",
            "current_score": 70 if "2년" in query_text else 80,
            "max_score": 100,
            "analysis_summary": "요약",
            "required_tech_stack": ["Python", "SQL"],
            "action_plan": [
                {
                    "category": "프로젝트",
                    "item_name": "테스트",
                    "description": "테스트",
                    "expected_score_up": 5,
                }
            ],
            "interview_tip": "팁",
        }

    monkeypatch.setattr(rag_v3_service, "fetch_user_info", fake_fetch_user_info)
    monkeypatch.setattr(rag_v3_service.job_repository, "fetch_job_detail", fake_fetch_job_detail)
    monkeypatch.setattr(rag_v3_service, "_get_llm", fake_get_llm)
    monkeypatch.setattr(rag_v3_service, "_run_llm_analysis", fake_run_llm_analysis)

    first = asyncio.run(rag_v3_service.analyze_job_detail(33, 1))
    state["career_years"] = 8
    second = asyncio.run(rag_v3_service.analyze_job_detail(33, 1))

    assert calls["count"] == 2
    assert first["current_score"] != second["current_score"]


def test_analyze_cache_eviction_works(monkeypatch) -> None:
    asyncio.run(_reset_analysis_state())

    calls = {"count": 0}
    monkeypatch.setattr(rag_v3_service, "ANALYSIS_CACHE_MAX_ENTRIES", 2)
    monkeypatch.setattr(rag_v3_service, "ANALYSIS_CACHE_TTL_SECONDS", 9999)

    async def fake_fetch_user_info(_user_id: int):
        return {
            "username": "테스트",
            "desired_job": "데이터 엔지니어",
            "career_years": 3,
            "skills": ["Python", "SQL"],
        }

    async def fake_fetch_job_detail(job_id: int):
        return {
            "job_id": job_id,
            "company": "MentoAI",
            "title": f"Data Engineer {job_id}",
            "full_text": f"경력 3년 이상, Python, SQL ({job_id})",
            "skills_text": "Python, SQL",
        }

    async def fake_get_llm():
        return object()

    async def fake_run_llm_analysis(_llm, _query_text: str, job: dict):
        calls["count"] += 1
        return {
            "job_title": job["title"],
            "company_name": job["company"],
            "current_score": 70,
            "max_score": 100,
            "analysis_summary": "요약",
            "required_tech_stack": ["Python", "SQL"],
            "action_plan": [
                {
                    "category": "프로젝트",
                    "item_name": "테스트",
                    "description": "테스트",
                    "expected_score_up": 5,
                }
            ],
            "interview_tip": "팁",
        }

    monkeypatch.setattr(rag_v3_service, "fetch_user_info", fake_fetch_user_info)
    monkeypatch.setattr(rag_v3_service.job_repository, "fetch_job_detail", fake_fetch_job_detail)
    monkeypatch.setattr(rag_v3_service, "_get_llm", fake_get_llm)
    monkeypatch.setattr(rag_v3_service, "_run_llm_analysis", fake_run_llm_analysis)

    asyncio.run(rag_v3_service.analyze_job_detail(1, 1))
    asyncio.run(rag_v3_service.analyze_job_detail(2, 1))
    asyncio.run(rag_v3_service.analyze_job_detail(3, 1))
    asyncio.run(rag_v3_service.analyze_job_detail(2, 1))  # cached
    asyncio.run(rag_v3_service.analyze_job_detail(1, 1))  # evicted then recomputed

    assert calls["count"] == 4
