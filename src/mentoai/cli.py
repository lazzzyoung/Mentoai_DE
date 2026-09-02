from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING

import typer

if TYPE_CHECKING:
    from mentoai import ops

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

app = typer.Typer(help="MentoAI 파이프라인 CLI", no_args_is_help=True)
jobs_app = typer.Typer(help="공고 데이터 관리", no_args_is_help=True)
users_app = typer.Typer(help="인재 관리", no_args_is_help=True)
app.add_typer(jobs_app, name="jobs")
app.add_typer(users_app, name="users")

SAMPLE_USERS = [
    ("지원", "데이터 엔지니어", 2, ["Python", "SQL", "Airflow", "Spark"]),
    ("하늘", "데이터 분석가", 1, ["Python", "SQL", "Tableau"]),
    ("도윤", "백엔드 개발자", 3, ["Java", "Spring", "AWS", "Docker"]),
]


async def seed_users() -> None:
    from mentoai.db.pool import execute

    for username, desired_job, career_years, skills in SAMPLE_USERS:
        await execute(
            "INSERT INTO users (username) VALUES ($1) ON CONFLICT (username) DO NOTHING",
            username,
        )
        await execute(
            """
            INSERT INTO user_specs (user_id, desired_job, career_years, skills)
            SELECT id, $2, $3, $4 FROM users WHERE username = $1
            ON CONFLICT (user_id) DO UPDATE SET
                desired_job = EXCLUDED.desired_job,
                career_years = EXCLUDED.career_years,
                skills = EXCLUDED.skills
            """,
            username,
            desired_job,
            career_years,
            skills,
        )


# ---------- 파이프라인 ----------


@app.command()
def migrate() -> None:
    """migrations/*.sql 을 DB에 적용한다."""
    from mentoai.db.migrate import apply_migrations

    applied = asyncio.run(apply_migrations())
    if applied:
        typer.echo(f"적용된 마이그레이션: {', '.join(applied)}")
    else:
        typer.echo("적용할 마이그레이션 없음 (최신 상태)")


@app.command()
def seed() -> None:
    """샘플 사용자/스펙을 적재한다 (멱등)."""
    asyncio.run(seed_users())
    typer.echo(f"시드 완료: 사용자 {len(SAMPLE_USERS)}명")


@app.command()
def scrape() -> None:
    """Bronze: 공고 수집 → bronze.raw_postings upsert."""
    from mentoai.pipeline import bronze

    count = asyncio.run(bronze.run())
    typer.echo(f"bronze 수집: {count}건")


@app.command()
def transform() -> None:
    """Silver: bronze → 통합 스키마 정제 → silver.jobs upsert."""
    from mentoai.pipeline import silver

    count = asyncio.run(silver.run())
    typer.echo(f"silver 적재: {count}건")


@app.command()
def embed(force: bool = typer.Option(False, "--force", help="기존 임베딩 전량 삭제 후 재계산")) -> None:
    """Gold: 정제 공고 임베딩 → silver.job_embeddings upsert."""
    from mentoai import ops
    from mentoai.pipeline import gold

    count = asyncio.run(ops.rebuild_embeddings() if force else gold.run())
    typer.echo(f"gold 임베딩: {count}건" + (" (전량 재계산)" if force else ""))


@app.command()
def pipeline() -> None:
    """bronze → silver → gold 전체 파이프라인 실행."""
    from mentoai.pipeline.runner import run_pipeline

    result = asyncio.run(run_pipeline())
    typer.echo(json.dumps(result, ensure_ascii=False))


# ---------- 현황 ----------


@app.command()
def status() -> None:
    """DB 현황·모델·스케줄·최근 실행 요약."""
    from mentoai import ops

    result = asyncio.run(ops.get_status())
    schedule = result["schedule"]
    next_run = schedule.get("next_run") or "-"
    typer.echo(f"임베딩: {result['embedding_model']} ({result['embedding_dim']}차원)")
    typer.echo(f"LLM: {result['gemini_model']}")
    typer.echo(
        f"데이터: 브론즈 {result['bronze']}건 / 공고 {result['jobs']}건 / "
        f"임베딩 {result['embeddings']}건 / 인재 {result['users']}명 / 캐시 {result['cached_analyses']}건"
    )
    sizes = result.get("sizes") or {}
    if sizes:
        typer.echo(
            f"용량: bronze {sizes.get('bronze_size')} ㅣ jobs {sizes.get('jobs_size')} ㅣ "
            f"embeddings {sizes.get('embeddings_size')}"
        )
    typer.echo(
        f"스케줄: {'켜짐' if schedule['enabled'] else '꺼짐'} ({schedule['cron']}) → 다음 {next_run}"
    )
    if result.get("running"):
        typer.echo(f"실행 중 작업: {', '.join(result['running'])}")
    last = result.get("last_run")
    if last:
        typer.echo(f"최근 파이프라인: #{last['id']} {last['status']} (수집 {last['scraped']})")


# ---------- 모델 관리 ----------


@app.command("models")
def models_cmd() -> None:
    """사용 가능한 임베딩 모델 목록과 현재 선택을 표시한다."""
    from fastembed import TextEmbedding

    from mentoai.ops import embedding_models

    info = embedding_models()
    typer.echo(f"현재 선택: {info['current']}\n")
    typer.echo("fastembed 지원 모델 (다국어/한국어 가능 표시):")
    for m in TextEmbedding.list_supported_models():
        desc = m["description"].lower()
        note = "  [다국어]" if "multilingual" in desc or "korean" in desc else ""
        typer.echo(f"  {m['model']:58s} dim={m['dim']:5d} {m['size_in_GB']:.2f}GB{note}")
    typer.echo("\nAPI 옵션: EMBEDDING_PROVIDER=gemini (gemini-embedding-001)")


@app.command("switch-embedding")
def switch_embedding_cmd(
    provider: str = typer.Option(..., help="fastembed | gemini"),
    model: str | None = typer.Option(None, help="모델명 (생략 시 기본값)"),
    dim: int | None = typer.Option(None, help="차원 (생략 시 모델에서 자동 해석)"),
    env_file: Path = typer.Option(Path(".env"), help="갱신할 .env 경로"),
    yes: bool = typer.Option(False, "--yes", help="확인 프롬프트 생략"),
) -> None:
    """임베딩 모델 전환: .env 갱신 + 테이블 재생성 + 전량 재임베딩."""
    from mentoai.embed_switch import resolve_target, switch_embedding

    target = resolve_target(provider, model, dim)
    typer.echo(f"전환 대상: provider={target.provider}, model={target.model}, dim={target.dim}")
    typer.echo("기존 임베딩은 모두 재계산되고 .env는 .env.bak으로 백업됩니다.")
    if not yes and not typer.confirm("계속할까요?"):
        raise typer.Abort()

    result = asyncio.run(switch_embedding(provider, model, dim, env_file))
    typer.echo(
        f"전환 완료: {result['provider']}:{result['model']} ({result['dim']}차원), "
        f"재임베딩 {result['re_embedded']}건"
    )


# ---------- 공고 관리 ----------


@jobs_app.command("list")
def jobs_list(
    query: str = typer.Option("", "--query", "-q", help="회사명·포지션 검색"),
    limit: int = typer.Option(30, "--limit", "-n", help="조회 건수"),
) -> None:
    """공고 목록 조회."""
    from mentoai import ops

    rows = asyncio.run(ops.list_jobs(query, limit))
    if not rows:
        typer.echo("조회 결과 없음")
        return
    for j in rows:
        typer.echo(f"  {j['id']:>4}  [{j['source']}] {j['company'] or '-'} ㅣ {j['position'] or '-'}")


@jobs_app.command("rm")
def jobs_rm(job_id: int) -> None:
    """공고 삭제 (bronze 원본·임베딩·캐시 함께)."""
    from mentoai import ops

    try:
        job = asyncio.run(ops.delete_job(job_id))
    except KeyError as error:
        detail = error.args[0] if error.args else "공고 없음"
        typer.echo(f"삭제 실패: {detail}")
        raise typer.Exit(1) from error
    typer.echo(f"삭제 완료: #{job_id} {job['company']} {job['position']}")


# ---------- 인재 관리 ----------


@users_app.command("list")
def users_list() -> None:
    """인재 목록 조회."""
    from mentoai.ai.users import list_users

    rows = asyncio.run(list_users())
    for u in rows:
        typer.echo(f"  {u['id']:>3}  {u['username']} ㅣ {u['desired_job']} ㅣ 경력 {u['career_years']}년")


@users_app.command("set")
def users_set(
    username: str = typer.Argument(..., help="사용자명"),
    job: str = typer.Option(..., "--job", help="희망 직무"),
    years: int = typer.Option(0, "--years", min=0, max=40, help="경력(년)"),
    skills: str = typer.Option("", "--skills", help="보유 스킬 (콤마 구분)"),
) -> None:
    """인재 등록/수정 (없으면 생성, 있으면 스펙 갱신)."""
    from mentoai import ops

    payload = ops.UserPayload(
        username=username,
        desired_job=job,
        career_years=years,
        skills=[s.strip() for s in skills.split(",") if s.strip()],
    )
    result = asyncio.run(_upsert_user(payload))
    typer.echo(
        f"저장 완료: #{result['id']} {result['username']} ㅣ {result['desired_job']} ㅣ "
        f"경력 {result['career_years']}년"
    )


async def _upsert_user(payload: ops.UserPayload) -> dict:
    from mentoai import ops

    try:
        return await ops.create_user(payload)
    except ValueError:
        existing = await ops.find_user_by_name(payload.username)
        assert existing is not None
        return await ops.update_user(existing["id"], payload)


@users_app.command("rm")
def users_rm(identifier: str = typer.Argument(..., help="사용자 ID 또는 이름")) -> None:
    """인재 삭제 (관련 캐시 cascade)."""
    from mentoai import ops

    async def _run() -> int:
        if identifier.isdigit():
            user_id = int(identifier)
        else:
            existing = await ops.find_user_by_name(identifier)
            if existing is None:
                raise KeyError(f"사용자 없음: {identifier}")
            user_id = existing["id"]
        await ops.delete_user(user_id)
        return user_id

    try:
        removed = asyncio.run(_run())
    except KeyError as error:
        detail = error.args[0] if error.args else "사용자 없음"
        typer.echo(f"삭제 실패: {detail}")
        raise typer.Exit(1) from error
    typer.echo(f"삭제 완료: #{removed}")


@app.command()
def serve(
    host: str = typer.Option("0.0.0.0", help="바인딩 호스트"),
    port: int = typer.Option(8000, help="포트"),
    reload: bool = typer.Option(False, help="개발용 핫 리로드"),
) -> None:
    """API 서버 실행 (uvicorn)."""
    import uvicorn

    uvicorn.run("mentoai.api.main:app", host=host, port=port, reload=reload)


if __name__ == "__main__":
    app()
