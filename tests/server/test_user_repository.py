import pytest

from server.app.repositories import user_repository as repo


class _AsyncContext:
    def __init__(self, value):
        self._value = value

    async def __aenter__(self):
        return self._value

    async def __aexit__(self, exc_type, exc, tb):
        return None


class _FakePool:
    def __init__(self, conn):
        self._conn = conn
        self.closed = False

    def acquire(self):
        return _AsyncContext(self._conn)

    async def close(self):
        self.closed = True


class _SchemaConn:
    def __init__(self):
        self.executed: list[str] = []

    async def execute(self, query: str, *args):
        self.executed.append(" ".join(query.split()))


class _CreateUserConn:
    def __init__(self):
        self.executed: list[tuple[str, tuple[object, ...]]] = []

    def transaction(self):
        return _AsyncContext(None)

    async def fetchval(self, query: str, *args):
        if "RETURNING id" in query:
            return 101
        raise AssertionError("예상하지 못한 fetchval 호출")

    async def execute(self, query: str, *args):
        self.executed.append((" ".join(query.split()), args))


@pytest.mark.anyio
async def test_user_tables_are_bootstrapped_once(monkeypatch):
    conn = _SchemaConn()
    pool = _FakePool(conn)

    monkeypatch.setattr(repo, "_pool", pool)
    monkeypatch.setattr(repo, "_pool_lock", None)
    monkeypatch.setattr(repo, "_schema_lock", None)
    monkeypatch.setattr(repo, "_schema_initialized", False)

    await repo._ensure_user_tables()
    await repo._ensure_user_tables()

    assert len(conn.executed) == 4
    assert any("CREATE TABLE IF NOT EXISTS users" in q for q in conn.executed)
    assert any("CREATE TABLE IF NOT EXISTS user_specs" in q for q in conn.executed)
    assert any("CREATE INDEX IF NOT EXISTS idx_user_specs_user_id" in q for q in conn.executed)
    assert any(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_user_specs_user_id" in q for q in conn.executed
    )


@pytest.mark.anyio
async def test_quick_user_creation_calls_schema_bootstrap(monkeypatch):
    conn = _CreateUserConn()
    pool = _FakePool(conn)
    called = {"schema": False}

    async def fake_ensure_user_tables():
        called["schema"] = True

    async def fake_get_pool():
        return pool

    async def fake_column_exists(_conn, table: str, column: str):
        enabled_columns = {
            ("users", "username"),
            ("users", "email"),
            ("user_specs", "user_id"),
            ("user_specs", "desired_job"),
            ("user_specs", "career_years"),
            ("user_specs", "skills"),
        }
        return (table, column) in enabled_columns

    monkeypatch.setattr(repo, "_ensure_user_tables", fake_ensure_user_tables)
    monkeypatch.setattr(repo, "_get_pool", fake_get_pool)
    monkeypatch.setattr(repo, "_resolve_column_exists", fake_column_exists)

    user_id = await repo.create_quick_user(
        user_name="홍길동",
        desired_job="데이터 엔지니어",
        career_years=2,
        skills=["Python", "Spark"],
    )

    assert called["schema"] is True
    assert user_id == 101
    assert len(conn.executed) == 1
    inserted_args = conn.executed[0][1]
    assert inserted_args[0] == 101
    assert inserted_args[1] == "데이터 엔지니어"
    assert inserted_args[2] == 2
    assert inserted_args[3] == ["Python", "Spark"]
