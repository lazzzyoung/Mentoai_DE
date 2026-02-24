# RAG 추천 가중치 전략

## 목적
추천 점수를 "검색 유사도"와 "사용자 프로필 적합도"로 분리해 안정적으로 랭킹한다.

- 검색 유사도: FTS(BM25) + 임베딩 코사인
- 프로필 적합도: 직무 + 기술 + 경력

## 최종 점수

```text
final_score = w_retrieval * retrieval_score + (1 - w_retrieval) * profile_score
```

- `w_retrieval` = `RANK_RETRIEVAL_WEIGHT` (기본 0.7)

## 검색 유사도(retrieval_score)

```text
retrieval_score = RETRIEVAL_ALPHA * lexical_score + (1 - RETRIEVAL_ALPHA) * semantic_score
```

- `lexical_score`: BM25 정규화 점수
- `semantic_score`: query/job 임베딩 코사인 정규화 점수

## 프로필 적합도(profile_score)

```text
profile_score = w_role * role_score + w_skills * skills_score + w_career * career_score
```

### 경력 구간별 가중치

| 사용자 경력 | 직무(w_role) | 기술(w_skills) | 경력(w_career) |
|---|---:|---:|---:|
| 0~2년 | 0.45 | 0.40 | 0.15 |
| 3~6년 | 0.40 | 0.40 | 0.20 |
| 7년+ | 0.30 | 0.30 | 0.40 |

## 서브 점수 정의(요약)

- `role_score`: 희망직무와 공고 제목/본문 토큰 중첩 기반
- `skills_score`: 사용자 보유 기술이 공고 기술/본문에 등장하는 커버 비율
- `career_score`: 공고 본문의 경력 요구(예: "3년 이상", "신입", "7년 이상")와 사용자 경력 차이

## 튜닝 가이드

1. 초기값은 위 테이블 그대로 사용
2. 로그에 `role/skills/career` 서브 점수를 함께 저장
3. 구간별 CTR/지원전환율/면접진행률로 가중치 재조정
4. 데이터가 충분하면 LTR(LambdaMART)로 대체 검토

## 관련 설정

- `RETRIEVAL_ALPHA` (기본 0.45)
- `RANK_RETRIEVAL_WEIGHT` (기본 0.7)
- `CANDIDATE_LIMIT` (기본 50)
