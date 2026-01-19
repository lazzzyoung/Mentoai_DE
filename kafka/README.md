# 📡 MentoAI Career Data Producer

고용24(Work24) 및 워크넷(Worknet)의 채용 공고 데이터를 수집하여 Kafka Topic으로 전송하는 데이터 수집 모듈입니다.  
**실시간성(Daily)**과 **대용량 처리(Backfill)**를 구분하기 위해 토픽과 진입점(Entry Point)을 이원화하여 설계되었습니다.

> **마지막 업데이트:** 2026.01.19  
> **작성자:** 강태영 (컴퓨터공학과 / 2022110200)

---

## 📂 디렉토리 구조


kafka/
├── utils/
│   ├── __init__.py      # 파이썬 패키지 인식용 파일
│   └── scraper.py       # [Core] 고용24/워크넷 크롤링 핵심 로직 (상세 페이지 파싱 포함)
├── producer_daily.py    # [Real-time] 최신 1페이지 공고 수집 -> 'career_raw' 토픽
├── producer_backfill.py # [Batch] 과거 공고 대량 수집 -> 'career_backfill' 토픽
├── producer_debug.py    # [Dev] 파싱 로직 테스트 및 디버깅용 (Kafka 전송 제외)
└── README.md            # 모듈 설명서


⸻

🛠 주요 업데이트 사항 (2026.01.19)
	1.	URL 최적화 적용
resultCnt=50 파라미터를 사용하여 한 번의 요청으로 50개의 공고를 수집함으로써 기존 대비 속도를 5배 향상시켰습니다.
	2.	민간 공고 호환성 강화
K로 시작하는 표준 ID뿐만 아니라, 외부 취업포털(사람인, 잡코리아 등) 연동 공고의 ID(wantedAuthNo)까지 식별하도록 정규표현식을 개선하여 수집 누락을 최소화했습니다.
	3.	데이터 완전성 복구
리스트 파싱 로직을 개선하여 기존에 누락되던 link, pay, location, deadline, reg_date 필드를 완벽하게 복구했습니다.
	4.	아키텍처 최적화를 위한 토픽 이원화
	•	career_raw: 실시간 증분 수집 데이터용 (저지연 처리 목적)
	•	career_backfill: 과거 데이터 소급 적재용 (대량 처리 및 리소스 분리 목적)

⸻

🚀 사용 방법

모든 스크립트는 프로젝트 루트 폴더(mentoai_DE)에서 실행하는 것을 권장합니다.

1. Daily Producer (실시간 수집)

가장 최신 공고 50개를 수집하여 Kafka로 전송합니다. Airflow DAG에 의해 주기적으로 실행됩니다.

# 프로젝트 루트에서 실행
python3 kafka/producer_daily.py

	•	대상 토픽: career_raw
	•	동작: 최신 1페이지만 크롤링하여 전송 후 종료

⸻

2. Backfill Producer (과거 데이터 적재)

특정 범위의 페이지를 지정하여 대량으로 수집할 때 사용합니다.

# 사용법: python3 kafka/producer_backfill.py [시작페이지] [끝페이지]

# 예시: 1페이지부터 10페이지까지 수집 (총 500개 공고)
python3 kafka/producer_backfill.py 1 10

	•	대상 토픽: career_backfill
	•	동작: 지정된 범위를 순회하며 수집
서버 차단 방지를 위해 페이지당 2~4초의 랜덤 딜레이가 적용됩니다.

⸻

3. Debug Mode (개발 및 테스트)

Kafka 전송 없이 터미널에 파싱 결과를 출력하여 로직을 점검합니다.

python3 kafka/producer_debug.py


⸻

📊 데이터 스키마 (JSON 샘플)

Kafka 메시지 브로커로 전송되는 최종 데이터 구조입니다.

{
  "source_id": "K120612601190046",
  "company": "주식회사 채널5코리아",
  "title": "2026 채널5코리아 백엔드 개발자 공채",
  "link": "https://www.work.go.kr/empInfo/empInfoSrch/detail/empDetailAuthView.do?wantedAuthNo=K120612601190046",
  "pay": "연봉 4,000 만원 이상",
  "location": "서울시 강남구",
  "deadline": "2026-02-28",
  "reg_date": "2026-01-19",
  "description": "API 서버 개발 및 유지보수, DB 스키마 설계...",
  "requirements": "경력조건: 신입 | 학력: 대졸(4년)",
  "preferred_qualifications": "자격면허: 정보처리기사 | 우대조건: 관련 전공자",
  "collected_at": "2026-01-19T18:45:00Z"
}


⸻

⚠️ 문제 해결 (Troubleshooting)

	•	데이터 누락 (N/A)
고용24 사이트의 HTML 구조 변경 시 scraper.py 내의 정규표현식 및 Selector 수정이 필요할 수 있습니다.
	•	상세 페이지 수집 실패
민간 연동 공고의 경우 상세 페이지 구조가 상이할 수 있으며,
이 경우 리스트 정보만 수집하고 본문은 외부 참조로 기록됩니다.

⸻

