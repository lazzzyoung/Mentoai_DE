# kafka/utils/scraper.py
import time
import re
import requests
import random
from bs4 import BeautifulSoup

def clean_space(text):
    if not text: return ""
    return re.sub(r'\s+', ' ', text).strip()

def get_detail_info(auth_no):
    """
    [기존 producer.py 로직 복원]
    상세 페이지에서 직무내용, 자격요건, 우대사항을 정밀하게 추출
    """
    detail_url = f"https://www.work.go.kr/empInfo/empInfoSrch/detail/empDetailAuthView.do?wantedAuthNo={auth_no}"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) Chrome/120.0.0.0 Safari/537.36'
    }
    
    try:
        # 차단 방지용 랜덤 딜레이
        time.sleep(random.uniform(0.3, 0.6))
        
        resp = requests.get(detail_url, headers=headers, timeout=10)
        if resp.status_code != 200:
            return None

        soup = BeautifulSoup(resp.text, 'html.parser')
        
        extracted_data = {
            "job_description": "상세 내용 없음",
            "requirements": "학력/경력 무관",
            "preferred": "우대사항 없음"
        }
        
        # 워크넷 상세 페이지 구조 (contents 혹은 emp_detail 클래스)
        content_area = soup.find(id='contents') or soup.find(class_='emp_detail')
        
        if content_area:
            # 1. 직무내용 추출 (th 태그 중 '직무내용' 텍스트를 가진 요소 찾기)
            job_desc_header = content_area.find(lambda tag: tag.name == "th" and "직무내용" in tag.get_text())
            if job_desc_header:
                job_desc_body = job_desc_header.find_next_sibling('td')
                if job_desc_body:
                    extracted_data["job_description"] = clean_space(job_desc_body.get_text())

            # 2. 자격요건 & 우대사항 (테이블 전체 스캔 방식 - 기존 로직 유지)
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
                        if "비희망" not in body_text and "관계없음" not in body_text:
                            pref_list.append(f"{header_text}: {body_text}")

            if req_list:
                extracted_data["requirements"] = " | ".join(req_list)
            
            if pref_list:
                extracted_data["preferred"] = " | ".join(pref_list)

        return extracted_data

    except Exception as e:
        print(f"      ❌ 상세페이지 에러({auth_no}): {e}")
        return None

def fetch_job_list(page_index):
    """
    고용24 리스트 페이지 호출 (50개씩 보기 적용)
    """
    url = "https://www.work24.go.kr/wk/a/b/1200/retriveDtlEmpSrchList.do"
    params = {
        "occupation": "135101,135102,136102,026,024",
        "resultCnt": "50",     # 50개씩 보기
        "sortField": "DATE",   # 최신순
        "sortOrderBy": "DESC",
        "pageIndex": page_index,
        "siteClcd": "all"      # 워크넷, 민간 취업포털 전체
    }
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }
    
    try:
        response = requests.get(url, params=params, headers=headers, timeout=10)
        soup = BeautifulSoup(response.text, 'html.parser')
        # 리스트 테이블 행 찾기
        return soup.find_all('tr', id=re.compile(r'^list\d+'))
    except Exception as e:
        print(f"❌ 리스트 호출 실패: {e}")
        return []