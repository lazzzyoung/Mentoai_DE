import logging
from datetime import UTC, datetime

import numpy as np

from mentoai.ai.embeddings import embed_documents, model_key
from mentoai.config import get_settings
from mentoai.db.pool import executemany, fetch

logger = logging.getLogger(__name__)

# 신규(bad), 공고 갱신(updated_at), 모델 전환(model 불일치) 모두 자동 재임베딩
PENDING_SQL = """
SELECT j.id, j.full_text
FROM silver.jobs j
LEFT JOIN silver.job_embeddings e ON e.job_id = j.id
WHERE e.job_id IS NULL
   OR e.embedded_at < j.updated_at
   OR e.model <> $1
"""

UPSERT_SQL = """
INSERT INTO silver.job_embeddings (job_id, embedding, model, embedded_at)
VALUES ($1, $2, $3, $4)
ON CONFLICT (job_id) DO UPDATE SET
    embedding = EXCLUDED.embedding,
    model = EXCLUDED.model,
    embedded_at = now()
"""


async def run() -> int:
    settings = get_settings()
    rows = await fetch(PENDING_SQL, model_key())
    if not rows:
        logger.info("gold: 임베딩 대상 없음")
        return 0

    vectors = await embed_documents([r["full_text"] for r in rows])
    dim = int(np.asarray(vectors[0]).shape[0])
    if dim != settings.embedding_dim:
        raise RuntimeError(
            f"임베딩 차원 불일치: 모델 {dim}차원 / 컬럼 {settings.embedding_dim}차원. "
            "`mentoai switch-embedding` 으로 전환하세요."
        )

    now = datetime.now(UTC)
    await executemany(
        UPSERT_SQL,
        [
            (r["id"], v, model_key(), now)
            for r, v in zip(rows, vectors, strict=True)
        ],
    )
    logger.info("gold upsert: %d건", len(rows))
    return len(rows)
