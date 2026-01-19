# kafka/producer_daily.py
import sys
import os

# 현재 파일 위치 기준, 상위 폴더(mentoai_DE)를 path에 추가하여 utils 패키지 인식
sys.path.append(os.path.dirname(os.path.abspath(os.path.dirname(__file__))))

import json
import time
import re
from kafka import KafkaProducer
from utils.scraper import fetch_job_list, get_detail_info, clean_space

def run_daily_producer():
    producer = KafkaProducer(
        bootstrap_servers=['localhost:9092'],
        value_serializer=lambda v: json.dumps(v).encode('utf-8')
    )

    print("🚀 [Daily] 최신 공고 50개 수집 시작...")
    
    # 50개 리스트 가져오기
    job_rows = fetch_job_list(page_index=1)
    
    if not job_rows:
        print("⚠️ 공고를 가져오지 못했습니다.")
        return

    count = 0
    for i, row in enumerate(job_rows):
        try:
            # -------------------------------------------
            # 1. 고유 ID (K-Number) 추출
            # -------------------------------------------
            row_html = str(row)
            auth_match = re.search(r"(K\d{10,})", row_html)
            if not auth_match: continue
            auth_no = auth_match.group(1)

            # -------------------------------------------
            # 2. 리스트 페이지 기본 정보 파싱 (기존 로직 복원)
            # -------------------------------------------
            cols = row.select('td')
            if len(cols) < 3: continue
            
            # [TD 0] 회사명 | 공고제목
            td0_parts = cols[0].get_text(separator='|', strip=True).split('|')
            company = td0_parts[0].strip() if len(td0_parts) > 0 else "N/A"
            
            title = "N/A"
            if len(td0_parts) > 1:
                potential_title = td0_parts[1].strip()
                # 불필요한 텍스트 제외 로직
                if "입사지원" in potential_title or "요약보기" in potential_title:
                     if len(td0_parts) > 2: title = td0_parts[2].strip()
                else:
                    title = potential_title

            # [TD 1] 급여 | 지역
            td1_parts = cols[1].get_text(separator='|', strip=True).split('|')
            pay, location = "면접 후 결정", "지역 미상"
            for part in td1_parts:
                part = clean_space(part)
                if any(x in part for x in ["연봉", "월급", "시급"]): pay = part
                elif any(x in part for x in ["시 ", "구 ", "군 "]) and "주" not in part: location = part

            # [TD 2] 등록일 | 마감일
            td2_text = cols[2].get_text(separator='|', strip=True)
            reg_match = re.search(r"등록일\s?:\s?(\d{4}-\d{2}-\d{2})", td2_text)
            reg_date = reg_match.group(1) if reg_match else time.strftime('%Y-%m-%d')
            deadline_match = re.search(r"마감일\s?:\s?(\d{4}-\d{2}-\d{2})", td2_text)
            deadline = deadline_match.group(1) if deadline_match else "채용시까지"

            # -------------------------------------------
            # 3. 상세 페이지 크롤링 (Scraper 호출)
            # -------------------------------------------
            detail = get_detail_info(auth_no)
            
            # 워크넷 링크 생성
            worknet_link = f"https://www.work.go.kr/empInfo/empInfoSrch/detail/empDetailAuthView.do?wantedAuthNo={auth_no}"

            data = {
                "source_id": auth_no,
                "company": company,
                "title": title,
                "link": worknet_link,     # 누락되었던 Link 복구
                "pay": pay,               # 누락되었던 Pay 복구
                "location": location,     # 누락되었던 Location 복구
                "deadline": deadline,     # 누락되었던 Deadline 복구
                "reg_date": reg_date,     # 누락되었던 Reg_date 복구
                "description": detail["job_description"] if detail else "수집실패",
                "requirements": detail["requirements"] if detail else "수집실패",
                "preferred_qualifications": detail["preferred"] if detail else "수집실패",
                "collected_at": time.strftime('%Y-%m-%dT%H:%M:%SZ')
            }
            
            producer.send('career_raw', value=data)
            print(f"   ✅ [{i+1}/50] {auth_no} | {company[:6]}... | {title[:10]}... 전송 완료")
            count += 1
            
        except Exception as e:
            print(f"   ⚠️ [{i+1}/50] 에러 발생 (건너뜀): {e}")
            continue
        
    producer.flush()
    producer.close()
    print(f"\n🎉 총 {count}건 전송 완료!")

if __name__ == "__main__":
    run_daily_producer()