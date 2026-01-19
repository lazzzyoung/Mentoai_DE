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
    상세 페이지 데이터 추출 (민간 공고 호환성 강화)
    """
    detail_url = f"https://www.work.go.kr/empInfo/empInfoSrch/detail/empDetailAuthView.do?wantedAuthNo={auth_no}"
    headers = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) Chrome/120.0.0.0 Safari/537.36'}
    
    # 기본값 (상세 수집 실패 시에도 이 값으로 리턴)
    extracted_data = {
        "job_description": "상세 내용 없음 (외부 채용 사이트 참조)",
        "requirements": "학력/경력 무관",
        "preferred": "우대사항 없음"
    }

    try:
        time.sleep(random.uniform(0.3, 0.6))
        resp = requests.get(detail_url, headers=headers, timeout=10)
        
        # 접속 자체가 안 되면 None 리턴 (이 경우에만 건너뜀)
        if resp.status_code != 200:
            return None

        soup = BeautifulSoup(resp.text, 'html.parser')
        
        # 1. 워크넷 표준 구조 (contents)
        content_area = soup.find(id='contents') or soup.find(class_='emp_detail')
        
        # 2. 민간 포털 연동 공고의 경우 (iframe 등 구조가 다를 수 있음)
        # 구조가 달라서 content_area를 못 찾아도 에러내지 않고 위에서 정의한 기본값 리턴
        
        if content_area:
            # 직무내용
            job_desc_header = content_area.find(lambda tag: tag.name == "th" and "직무내용" in tag.get_text())
            if job_desc_header:
                job_desc_body = job_desc_header.find_next_sibling('td')
                if job_desc_body:
                    extracted_data["job_description"] = clean_space(job_desc_body.get_text())

            # 자격/우대 (테이블 스캔)
            req_list, pref_list = [], []
            tables = content_area.find_all('table')
            for table in tables:
                rows = table.find_all('tr')
                for row in rows:
                    th, td = row.find('th'), row.find('td')
                    if not th or not td: continue
                    
                    h_txt, b_txt = clean_space(th.get_text()), clean_space(td.get_text())
                    if not b_txt or any(x in b_txt for x in ["관계없음", "비희망", "해당없음"]): continue

                    if any(kw in h_txt for kw in ["경력조건", "학력", "모집직종"]):
                        req_list.append(f"{h_txt}: {b_txt}")
                    elif any(kw in h_txt for kw in ["우대조건", "전공", "자격면허", "외국어", "컴퓨터"]):
                        pref_list.append(f"{h_txt}: {b_txt}")

            if req_list: extracted_data["requirements"] = " | ".join(req_list)
            if pref_list: extracted_data["preferred"] = " | ".join(pref_list)

        return extracted_data

    except Exception as e:
        # 에러가 나도 기본값은 반환해서 리스트 정보라도 저장하게 함
        print(f"      ⚠️ 상세 페이지 파싱 실패({auth_no}): {e}")
        return extracted_data

def fetch_job_list(page_index):
    """리스트 페이지 호출 (50개씩)"""
    url = "https://www.work24.go.kr/wk/a/b/1200/retriveDtlEmpSrchList.do"
    params = {
        "occupation": "135101,135102,136102,026,024",
        "resultCnt": "50",
        "sortField": "DATE",
        "sortOrderBy": "DESC",
        "pageIndex": page_index,
        "siteClcd": "all"
    }
    headers = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'}
    
    try:
        response = requests.get(url, params=params, headers=headers, timeout=10)
        soup = BeautifulSoup(response.text, 'html.parser')
        return soup.find_all('tr', id=re.compile(r'^list\d+'))
    except Exception:
        return []