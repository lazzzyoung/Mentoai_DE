-- 로그인 신원 연결: 구글(sub)/앱인토스(userKey) 계정을 서비스 사용자에 매핑한다.
-- 첫 로그인 시 users+user_specs가 자동 생성되고 여기에 연결된다.
CREATE TABLE IF NOT EXISTS auth_identities (
    provider TEXT NOT NULL,
    provider_user_id TEXT NOT NULL,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at TEXT NOT NULL,
    PRIMARY KEY (provider, provider_user_id)
);
