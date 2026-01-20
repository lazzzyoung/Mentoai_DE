import sys
import os

# 경로 설정 (utils 패키지 인식용)
sys.path.append(os.path.dirname(os.path.abspath(os.path.dirname(__file__))))

import json
import time
import re
from kafka import KafkaProducer
from utils.scraper import fetch_job_list, get_detail_info, clean_space

def run_daily_producer():
    
    bootstrap_server = os.getenv('KAFKA_BOOTSTRAP_SERVERS', 'localhost:9092')
    
    producer = KafkaProducer(
        bootstrap_servers=[bootstrap_server],
        value_serializer=lambda v: json.dumps(v).encode('utf-8')
    )

    TOPIC_NAME = 'career_raw'

    print(f"🚀 [Daily] 최신 공고 50개 수집 시작... (Server: {bootstrap_server})")
    job_rows = fetch_job_list(page_index=1)
    
    if not job_rows:
        print("⚠️ 공고를 가져오지 못했습니다.")
        return

    count = 0
    for i, row in enumerate(job_rows):
        try:
            row_html = str(row)
            
            # ID 추출 로직
            auth_match = re.search(r"wantedAuthNo=([a-zA-Z0-9]+)", row_html)
            if auth_match:
                auth_no = auth_match.group(1)
            else:
                k_match = re.search(r"(K\d{10,})", row_html)
                if k_match:
                    auth_no = k_match.group(1)
                else:
                    print(f"   ❌ [{i+1}/50] ID 식별 불가 - Skip")
                    continue

            # 기본 정보 파싱
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
            print(f"   ✅ [{i+1}/50] {auth_no} | {company[:6]}... 전송")
            count += 1
            
        except Exception as e:
            print(f"   ⚠️ [{i+1}/50] 에러: {e}")
            continue
        
    producer.flush()
    producer.close()
    print(f"\n🎉 총 {count}건 전송 완료!")

if __name__ == "__main__":
    run_daily_producer()