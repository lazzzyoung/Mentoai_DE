# kafka/producer_backfill.py
import sys
from utils.scraper import fetch_job_list, get_detail_info
# ... (중략: producer 설정 등 daily와 유사) ...

def run_backfill(start_page, end_page):
    print(f"📂 [Backfill] {start_page} ~ {end_page} 페이지 수집 시작 (50개씩)...")
    for p in range(start_page, end_page + 1):
        print(f"\n📄 현재 페이지: {p}")
        job_rows = fetch_job_list(p)
        # ... (이하 수집 및 전송 로직 동일) ...
        time.sleep(2) # 백필은 대량이므로 서버 부하 방지용 휴식 필수

if __name__ == "__main__":
    s_page = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    e_page = int(sys.argv[2]) if len(sys.argv) > 2 else 5
    run_backfill(s_page, e_page)