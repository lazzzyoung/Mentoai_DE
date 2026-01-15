# kafka/producer.py
import time
import json
import re
import requests
import random
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

def get_detail_info(auth_no):
    """
    [필드 분리 기능 추가]
    단순 텍스트 덤프가 아니라, '자격요건', '우대사항', '직무내용'을 분리해서 추출
    """
    detail_url = f"https://www.work.go.kr/empInfo/empInfoSrch/detail/empDetailAuthView.do?wantedAuthNo={auth_no}"
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) Chrome/120.0.0.0 Safari/537.36'
    }
    
    print(f"   👉 [Detail] 상세 접속: {auth_no}")
    
    try:
        time.sleep(random.uniform(0.3, 0.6))
        
        resp = requests.get(detail_url, headers=headers)
        if resp.status_code != 200:
            print(f"   ❌ [Detail] 접속 실패 (Status: {resp.status_code})")
            return None

        soup = BeautifulSoup(resp.text, 'html.parser')
        
        # -------------------------------------------------------
        # 데이터 구조화 로직
        # -------------------------------------------------------
        # 기본값 설정
        extracted_data = {
            "job_description": "상세 내용 없음", # 직무내용
            "requirements": "학력/경력 무관",    # 자격요건 (경력, 학력)
            "preferred": "우대사항 없음"         # 우대사항 (전공, 자격증, 우대조건)
        }
        
        content_area = soup.find(id='contents') or soup.find(class_='emp_detail')
        
        if content_area:
            # 1. 직무내용 추출 (보통 '직무내용' 헤더를 가진 iframe이나 td에 있음)
            # 워크넷은 직무내용이 텍스트로 길게 들어가므로 별도 탐색
            job_desc_header = content_area.find(lambda tag: tag.name == "th" and "직무내용" in tag.get_text())
            if job_desc_header:
                # th 바로 다음의 td를 찾음
                job_desc_body = job_desc_header.find_next_sibling('td')
                if job_desc_body:
                    extracted_data["job_description"] = clean_space(job_desc_body.get_text())

            # 2. 자격요건 & 우대사항 (테이블 전체 스캔)
            # 'th' 태그의 텍스트를 보고 판단하여 'td'의 내용을 수집
            
            req_list = []
            pref_list = []
            
            tables = content_area.find_all('table')
            for table in tables:
                rows = table.find_all('tr')
                for row in rows:
                    th = row.find('th')
                    td = row.find('td')
                    if not th or not td: continue
                    
                    header_text = clean_space(th.get_text())
                    body_text = clean_space(td.get_text())
                    
                    if not body_text: continue

                    # (A) 자격요건 관련 키워드
                    if any(kw in header_text for kw in ["경력조건", "학력", "모집직종"]):
                        req_list.append(f"{header_text}: {body_text}")
                        
                    # (B) 우대사항 관련 키워드
                    elif any(kw in header_text for kw in ["우대조건", "전공", "자격면허", "외국어", "컴퓨터"]):
                        # '비희망', '관계없음' 같은 의미 없는 데이터는 제외
                        if "비희망" not in body_text and "관계없음" not in body_text:
                            pref_list.append(f"{header_text}: {body_text}")

            # 리스트를 문자열로 합치기
            if req_list:
                extracted_data["requirements"] = " | ".join(req_list)
            
            if pref_list:
                extracted_data["preferred"] = " | ".join(pref_list)
            
            print(f"      ✅ 직무: {len(extracted_data['job_description'])}자 | 자격: {bool(req_list)} | 우대: {bool(pref_list)}")

        else:
            print("   ⚠️ [Warn] 본문 영역 못 찾음. 전체 텍스트 수집으로 대체.")
            extracted_data["job_description"] = clean_space(soup.body.get_text())[:1000]

        return extracted_data

    except Exception as e:
        print(f"   ❌ [Detail] 에러 발생: {e}")
        return None

def scrape_and_produce(page_index=1):
    producer = get_kafka_producer()
    topic_name = 'career_raw'
    
    print(f"🚀 [Page {page_index}] 크롤링 시작 (구조화 데이터 추출)...")
    
    # 리스트 페이지 (고용24)
    url = f"https://www.work24.go.kr/wk/a/b/1200/retriveDtlEmpSrchList.do?occupation=135101%7C135102%7C136102%7C026%7C024&pageIndex={page_index}"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }

    try:
        response = requests.get(url, headers=headers)
        soup = BeautifulSoup(response.text, 'html.parser')
        job_rows = soup.find_all('tr', id=re.compile(r'^list\d+'))
        
        print(f"📌 [List] 공고 {len(job_rows)}개 발견")
        
        count = 0
        for i, row in enumerate(job_rows):
            print(f"\n--- [공고 #{i+1}] ---")
            
            # K-Number
            row_html = str(row)
            auth_match = re.search(r"(K\d{10,})", row_html)
            if not auth_match: continue
            auth_no = auth_match.group(1)
            
            # 기본 정보 Parsing
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

            # -----------------------------------------------------
            # [상세] 구조화된 데이터 추출 호출
            # -----------------------------------------------------
            detail_data = get_detail_info(auth_no)
            
            if detail_data:
                job_desc = detail_data["job_description"]
                req = detail_data["requirements"]
                pref = detail_data["preferred"]
            else:
                job_desc = "수집 실패"
                req = "수집 실패"
                pref = "수집 실패"

            # 워크넷 링크 (사용자 제공용)
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
                # ▼ 깔끔하게 분리된 필드들
                "description": job_desc,      # 순수 직무내용
                "requirements": req,          # 자격요건 (경력, 학력 등)
                "preferred_qualifications": pref, # 우대사항
                "collected_at": time.strftime('%Y-%m-%dT%H:%M:%SZ')
            }
            
            producer.send(topic_name, value=data)
            print("   ✅ [Kafka] 전송 완료")
            count += 1
                
        producer.flush()
        print(f"\n🎉 총 {count}건의 데이터를 '{topic_name}' 토픽으로 전송했습니다.")

    except Exception as e:
        print(f"❌ [Critical] 에러: {e}")
    finally:
        producer.close()

if __name__ == "__main__":
    scrape_and_produce(page_index=1)