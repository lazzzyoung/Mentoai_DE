import sys
import os

# 경로 설정 (utils 패키지 인식용)
sys.path.append(os.path.dirname(os.path.abspath(os.path.dirname(__file__))))

import json
import time
import re
import random
from kafka import KafkaProducer
from kafka.utils.recruit24_scraper import fetch_job_list, get_detail_info, clean_space

def run_backfill(start_page, end_page):
    
    bootstrap_server = os.getenv('KAFKA_BOOTSTRAP_SERVERS', 'localhost:9092')
    
    producer = KafkaProducer(
        bootstrap_servers=[bootstrap_server],
        value_serializer=lambda v: json.dumps(v).encode('utf-8'),
        linger_ms=20,
        batch_size=16384
    )
    
    TOPIC_NAME = 'career_backfill'

    print(f"📂 [Backfill] 과거 데이터 수집 시작: {start_page} ~ {end_page}페이지 (Server: {bootstrap_server})")
    print(f"   👉 Target Topic: {TOPIC_NAME}")

    total_count = 0
    
    for page in range(start_page, end_page + 1):
        print(f"\n📖 [Page {page}/{end_page}] 데이터 긁어오는 중...")
        job_rows = fetch_job_list(page_index=page)
        
        if not job_rows:
            print(f"   ⚠️ {page}페이지 로딩 실패 또는 공고 없음. Skip.")
            time.sleep(2)
            continue

        page_count = 0
        for i, row in enumerate(job_rows):
            try:
                row_html = str(row)
                
                auth_match = re.search(r"wantedAuthNo=([a-zA-Z0-9]+)", row_html)
                if auth_match:
                    auth_no = auth_match.group(1)
                else:
                    k_match = re.search(r"(K\d{10,})", row_html)
                    auth_no = k_match.group(1) if k_match else None
                
                if not auth_no: continue

                cols = row.select('td')
                if len(cols) < 3: continue
                
                td0_parts = cols[0].get_text(separator='|', strip=True).split('|')
                company = td0_parts[0].strip() if len(td0_parts) > 0 else "N/A"
                title = "N/A"
                if len(td0_parts) > 1:
                    potential_title = td0_parts[1].strip()
                    if "입사지원" in potential_title or "요약보기" in potential_title:
                         if len(td0_parts) > 2: title = td0_parts[2].strip()
                    else:
                        title = potential_title

                td1_parts = cols[1].get_text(separator='|', strip=True).split('|')
                pay, location = "면접 후 결정", "지역 미상"
                for part in td1_parts:
                    part = clean_space(part)
                    if any(x in part for x in ["연봉", "월급", "시급"]): pay = part
                    elif any(x in part for x in ["시 ", "구 ", "군 "]) and "주" not in part: location = part

                td2_text = cols[2].get_text(separator='|', strip=True)
                reg_match = re.search(r"등록일\s?:\s?(\d{4}-\d{2}-\d{2})", td2_text)
                reg_date = reg_match.group(1) if reg_match else time.strftime('%Y-%m-%d')
                deadline_match = re.search(r"마감일\s?:\s?(\d{4}-\d{2}-\d{2})", td2_text)
                deadline = deadline_match.group(1) if deadline_match else "채용시까지"

                detail = get_detail_info(auth_no)
                if not detail:
                     detail = {"job_description": "수집 에러", "requirements": "", "preferred": ""}

                worknet_link = f"https://www.work.go.kr/empInfo/empInfoSrch/detail/empDetailAuthView.do?wantedAuthNo={auth_no}"

                data = {
                    "source_id": auth_no,
                    "company": company,
                    "title": title,
                    "link": worknet_link,
                    "pay": pay,
                    "location": location,
                    "deadline": deadline,
                    "reg_date": reg_date,
                    "description": detail["job_description"],
                    "requirements": detail["requirements"],
                    "preferred_qualifications": detail["preferred"],
                    "collected_at": time.strftime('%Y-%m-%dT%H:%M:%SZ')
                }

                producer.send(
                    TOPIC_NAME, 
                    key=auth_no.encode('utf-8'),
                    value=data
                )
                
                if (i+1) % 10 == 0:
                    print(f"   ✅ [P.{page}] {i+1}번째: {company[:6]}... 전송 완료")
                
                page_count += 1
                total_count += 1

            except Exception:
                continue
        
        producer.flush()
        print(f"   🏁 [Page {page}] {page_count}건 전송 완료. 대기 중...")
        time.sleep(random.uniform(2.0, 4.0)) 

    producer.close()
    print(f"\n🎉 Backfill 완료! 총 {total_count}건을 '{TOPIC_NAME}' 토픽으로 전송했습니다.")

if __name__ == "__main__":
    s_page = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    e_page = int(sys.argv[2]) if len(sys.argv) > 2 else 2
    run_backfill(s_page, e_page)