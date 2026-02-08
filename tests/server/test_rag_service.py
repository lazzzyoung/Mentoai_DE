import importlib
import sys
from pathlib import Path

from langchain_core.documents import Document


def _load_rag_service_module():
    root_dir = Path(__file__).resolve().parents[2]
    if str(root_dir) not in sys.path:
        sys.path.insert(0, str(root_dir))
    return importlib.import_module("server.app.services.rag_service")


def test_build_user_query_text_includes_career_optionally() -> None:
    module = _load_rag_service_module()
    service = module.RAGService.__new__(module.RAGService)
    user_info = {
        "username": "tester",
        "desired_job": "Data Engineer",
        "career_years": 2,
        "skills": ["Python", "Spark"],
    }

    base_query = service._build_user_query_text(user_info)
    with_career_query = service._build_user_query_text(user_info, include_career=True)

    assert "희망직무: Data Engineer" in base_query
    assert "보유기술: Python, Spark" in base_query
    assert "경력:" not in base_query
    assert "경력: 2년" in with_career_query


def test_normalize_doc_id_handles_valid_and_invalid_metadata() -> None:
    module = _load_rag_service_module()
    service = module.RAGService.__new__(module.RAGService)

    valid_doc = Document(page_content="doc", metadata={"id": "101"})
    fallback_doc = Document(page_content="doc", metadata={"_id": "202"})
    invalid_doc = Document(page_content="doc", metadata={"id": "abc"})
    empty_doc = Document(page_content="doc", metadata={})

    assert service._normalize_doc_id(valid_doc) == 101
    assert service._normalize_doc_id(fallback_doc) == 202
    assert service._normalize_doc_id(invalid_doc) is None
    assert service._normalize_doc_id(empty_doc) is None


def test_format_docs_limits_content_length() -> None:
    module = _load_rag_service_module()
    docs = [
        Document(
            page_content="abcdefghij",
            metadata={"company": "A Corp", "position": "Backend Engineer"},
        )
    ]

    formatted = module.RAGService._format_docs(docs, content_limit=4)

    assert "기업: A Corp" in formatted
    assert "제목: Backend Engineer" in formatted
    assert "내용: abcd" in formatted
