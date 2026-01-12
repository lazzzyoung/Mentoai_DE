import requests
from bs4 import BeautifulSoup
import json
import re

def test_scraper_final():
    print("🚀 워크24 최종 크롤링 테스트 (URL 및 회사명 보완)...")
    
    url = "https://www.work24.go.kr/wk/a/b/1200/retriveDtlEmpSrchList.do?occupation=135101%7C135102%7C136102%7C026%7C024&pageIndex=1"
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }

    try:
        response = requests.get(url, headers=headers)
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # ID가 list로 시작하는 행 수집
        job_rows = soup.find_all('tr', id=re.compile(r'^list\d+'))
        print(f"📌 발견된 공고 행(Row) 개수: {len(job_rows)}개\n")

        results = []
        for row in job_rows:
            # 1. 회사명: 'corp'가 들어간 span 또는 td 안의 텍스트
            corp_tag = row.select_one('.corp_name') or row.select_one('td.left')
            company = corp_tag.get_text(strip=True).split('요약보기')[0] if corp_tag else "N/A"
            
            # 2. 공고명 및 상세 URL 생성
            title = "N/A"
            full_link = "N/A"
            
            all_links = row.find_all('a')
            for a in all_links:
                href = a.get('href', '')
                # 인증번호(K...) 추출
                auth_match = re.search(r"(K\d+)", href)
                if auth_match:
                    auth_no = auth_match.group(1)
                    title = a.get_text(strip=True)
                    # ✅ 사용자님이 확인하신 '진짜' 상세 페이지 경로로 조립
                    full_link = (
                        f"https://www.work24.go.kr/wk/a/b/1500/empDetailAuthView.do?"
                        f"wantedAuthNo={auth_no}&infoTypeCd=VALIDATION&infoTypeGroup=tb_workinfoworknet"
                    )
                    break

            if title != "N/A":
                results.append({
                    "company": company,
                    "title": title,
                    "link": full_link
                })

        print(json.dumps(results[:5], indent=2, ensure_ascii=False))

    except Exception as e:
        print(f"❌ 에러 발생: {e}")

if __name__ == "__main__":
    test_scraper_final()