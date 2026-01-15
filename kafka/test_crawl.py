import requests
from bs4 import BeautifulSoup
import re

def test_crawler_structure():
    print("🚀 워크24 데이터 구조 정밀 진단 시작...")
    
    # 1. 요청 설정
    url = "https://www.work24.go.kr/wk/a/b/1200/retriveDtlEmpSrchList.do?occupation=135101%7C135102%7C136102%7C026%7C024&pageIndex=1"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }

    try:
        response = requests.get(url, headers=headers)
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # 2. 공고 행(Row) 찾기
        job_rows = soup.find_all('tr', id=re.compile(r'^list\d+'))
        print(f"📌 발견된 공고 행(Row) 개수: {len(job_rows)}개\n")

        # 3. 각 행의 td 데이터 날것 그대로 출력
        for i, row in enumerate(job_rows):
            print(f"--- [공고 #{i+1}] ---")
            cols = row.select('td')
            print(f"📊 칸(td) 개수: {len(cols)}")
            
            for idx, col in enumerate(cols):
                # 텍스트 내부의 지저분한 공백/줄바꿈을 식별하기 위해 separator 사용
                raw_text = col.get_text(separator='|', strip=True)
                print(f"  🔹 td[{idx}]: {raw_text}")
            
            print("-" * 50)
            
            # 너무 많이 출력되면 보기 힘드니 3개만 보고 종료
            if i >= 2:
                print("... (이하 생략) ...")
                break

    except Exception as e:
        print(f"❌ 에러 발생: {e}")

if __name__ == "__main__":
    test_crawler_structure()