# kafka/producer.py
import time
import json
import re
import requests
from bs4 import BeautifulSoup
from kafka import KafkaProducer

def get_kafka_producer():
    return KafkaProducer(
        bootstrap_servers=['localhost:9092'],
        value_serializer=lambda v: json.dumps(v).encode('utf-8')
    )

def clean_space(text):
    if not text: return ""
    return re.sub(r'\s+', ' ', text).strip()

def scrape_and_produce(page_index=1):
    producer = get_kafka_producer()
    topic_name = 'career_raw'
    
    print(f"🚀 [Page {page_index}] 강력 크롤링 시작 (Hidden Auth No 탐색)...")
    
    url = f"https://www.work24.go.kr/wk/a/b/1200/retriveDtlEmpSrchList.do?occupation=135101%7C135102%7C136102%7C026%7C024&pageIndex={page_index}"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }

    try:
        response = requests.get(url, headers=headers)
        soup = BeautifulSoup(response.text, 'html.parser')
        job_rows = soup.find_all('tr', id=re.compile(r'^list\d+'))
        
        count = 0
        for row in job_rows:
            cols = row.select('td')
            if len(cols) < 3: continue

            # -------------------------------------------------
            # 1. K-Number(구인인증번호) 전수 조사
            # -------------------------------------------------
            # href가 #none일 수 있으므로, row 전체 HTML에서 패턴 검색
            # 패턴: K + 숫자 10자리 이상 (예: K120422601150021)
            row_html = str(row)
            auth_match = re.search(r"(K\d{10,})", row_html)
            
            auth_no = "N/A"
            full_link = "N/A"
            
            if auth_match:
                auth_no = auth_match.group(1)
                full_link = (
                    f"https://www.work24.go.kr/wk/a/b/1500/empDetailAuthView.do?"
                    f"wantedAuthNo={auth_no}&infoTypeCd=VALIDATION&infoTypeGroup=tb_workinfoworknet"
                )
            else:
                # K번호를 못 찾으면 의미 없는 데이터이므로 스킵
                continue

            # -------------------------------------------------
            # 2. 회사명 & 제목 (파이프 분리 방식)
            # -------------------------------------------------
            td0_parts = cols[0].get_text(separator='|', strip=True).split('|')
            company = td0_parts[0].strip() if len(td0_parts) > 0 else "N/A"
            
            # 제목 추출 로직 보완: '요약보기' 등이 아닌 진짜 제목 찾기
            title = "N/A"
            if len(td0_parts) > 1:
                potential_title = td0_parts[1].strip()
                # 만약 두 번째 조각이 이상하면 세 번째 조각 확인
                if "입사지원" in potential_title or "요약보기" in potential_title:
                     if len(td0_parts) > 2:
                         title = td0_parts[2].strip()
                else:
                    title = potential_title

            # -------------------------------------------------
            # 3. 상세 정보 (급여, 지역 등)
            # -------------------------------------------------
            td1_parts = cols[1].get_text(separator='|', strip=True).split('|')
            
            pay = "면접 후 결정"
            experience = "경력 무관"
            education = "학력 무관"
            location = "지역 미상"

            for part in td1_parts:
                part = clean_space(part)
                if not part: continue

                if any(x in part for x in ["연봉", "월급", "시급", "만원", "원"]):
                    pay = part
                elif any(x in part for x in ["경력", "신입"]):
                    experience = part
                elif any(x in part for x in ["학력", "대졸", "고졸", "박사"]):
                    education = part
                elif any(x in part for x in ["시 ", "구 ", "군 ", "로 ", "길 "]) and "주" not in part:
                    location = part

            # -------------------------------------------------
            # 4. 날짜 정보
            # -------------------------------------------------
            td2_text = cols[2].get_text(separator='|', strip=True)
            deadline_match = re.search(r"마감일\s?:\s?(\d{4}-\d{2}-\d{2})", td2_text)
            reg_match = re.search(r"등록일\s?:\s?(\d{4}-\d{2}-\d{2})", td2_text)
            
            deadline = deadline_match.group(1) if deadline_match else "채용시까지"
            reg_date = reg_match.group(1) if reg_match else time.strftime('%Y-%m-%d')

            # -------------------------------------------------
            # 5. Kafka 전송
            # -------------------------------------------------
            if title != "N/A" and full_link != "N/A":
                data = {
                    "source_id": auth_no,
                    "company": company,
                    "title": title,
                    "link": full_link,
                    "pay": pay,
                    "education": education,
                    "experience": experience,
                    "location": location,
                    "deadline": deadline,
                    "reg_date": reg_date,
                    "collected_at": time.strftime('%Y-%m-%dT%H:%M:%SZ')
                }
                
                producer.send(topic_name, value=data)
                print(f"✅ [{company}] {title[:20]}...")
                count += 1
                
        producer.flush()
        print(f"\n🎉 총 {count}건의 데이터를 '{topic_name}' 토픽으로 전송했습니다.")

    except Exception as e:
        print(f"❌ 에러 발생: {e}")
    finally:
        producer.close()

if __name__ == "__main__":
    scrape_and_produce(page_index=1)