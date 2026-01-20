import sys
import os
import re
import json
import time

# 경로 설정
sys.path.append(os.path.dirname(os.path.abspath(os.path.dirname(__file__))))

from utils.scraper import fetch_job_list, get_detail_info, clean_space

def run_debug_producer():
    print("🐞 [DEBUG] 디버깅 모드 시작... 공고 리스트를 분석합니다.")
    
    
    job_rows = fetch_job_list(page_index=1)
    print(f"📌 [List] fetch_job_list 결과: 총 {len(job_rows)}개의 행(tr)을 찾았습니다.")
    
    if len(job_rows) == 0:
        print("❌ [Critical] 행을 하나도 못 찾았습니다. scraper.py의 CSS 선택자나 URL을 점검하세요.")
        return

    success_count = 0
    fail_count = 0

    for i, row in enumerate(job_rows):
        print(f"\n--- [Row #{i+1} 분석] ---")
        
        row_str = str(row)
        
        # K로 시작하는 10자리 이상 숫자 (워크넷/고용24 표준)
        auth_match = re.search(r"(K\d{10,})", row_str)
        # W나 다른 문자로 시작하는 ID가 있는지 확인하기 위해 범용 패턴 추가
        generic_match = re.search(r"wantedAuthNo=(\w+)", row_str)

        if not auth_match:
            print(f"   ❌ [Skip] K-ID 매칭 실패")
            if generic_match:
                print(f"      👉 발견된 다른 형태의 ID: {generic_match.group(1)} (패턴 수정 필요)")
            else:
                print(f"      👉 HTML 일부: {row_str[:100]}...")
            fail_count += 1
            continue
        
        auth_no = auth_match.group(1)
        print(f"   ✅ ID 추출 성공: {auth_no}")

        cols = row.select('td')
        if len(cols) < 3:
            print(f"   ❌ [Skip] td 개수 부족 (발견: {len(cols)}개)")
            fail_count += 1
            continue

        try:
            td0_parts = cols[0].get_text(separator='|', strip=True).split('|')
            company = td0_parts[0].strip() if len(td0_parts) > 0 else "N/A"
            title = "N/A"
            if len(td0_parts) > 1:
                potential_title = td0_parts[1].strip()
                if "입사지원" in potential_title or "요약보기" in potential_title:
                     if len(td0_parts) > 2: title = td0_parts[2].strip()
                else:
                    title = potential_title
            
            print(f"   ✅ 파싱 성공: 회사[{company}] / 제목[{title[:10]}...]")
            
        except Exception as e:
            print(f"   ❌ [Error] 파싱 중 에러: {e}")
            fail_count += 1
            continue

        # 상세 페이지 접근 테스트 (현재 상세 정보 수집 불가)
        if i < 3 or i > 25: 
            print("   👉 [Detail] 상세 페이지 접속 시도...")
            detail = get_detail_info(auth_no)
            if detail:
                desc_len = len(detail.get('job_description', ''))
                print(f"      ✅ 상세 수집 성공 (본문 길이: {desc_len})")
            else:
                print("      ⚠️ 상세 수집 실패 (None 반환됨)")
        else:
             print("   Pass (디버깅 속도를 위해 상세 수집 생략)")

        success_count += 1
        time.sleep(0.1) # 로그 꼬임 방지

    print(f"\n==========================================")
    print(f"🐞 디버깅 완료: 성공 {success_count}건 / 실패(Skip) {fail_count}건")
    print(f"==========================================")

if __name__ == "__main__":
    run_debug_producer()