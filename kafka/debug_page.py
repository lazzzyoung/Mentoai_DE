# kafka/debug_page.py
import requests
from bs4 import BeautifulSoup
import re

def debug_work24():
    url = "https://www.work24.go.kr/wk/a/b/1200/retriveDtlEmpSrchList.do?occupation=135101%7C135102%7C136102%7C026%7C024&pageIndex=1"
    headers = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}
    
    try:
        response = requests.get(url, headers=headers)
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # 1. HTML 저장
        with open("work24_debug.html", "w", encoding="utf-8") as f:
            f.write(soup.prettify())
        print("💾 'work24_debug.html' 저장 완료.")

        # 2. 첫 번째 행 분석
        row = soup.find('tr', id=re.compile(r'^list\d+'))
        if row:
            cols = row.select('td')
            print(f"📊 발견된 td 개수: {len(cols)}")
            for i, col in enumerate(cols):
                print(f"--- [td {i}] ---")
                print(col.get_text(separator=" ", strip=True))
        else:
            print("❌ 공고 행(tr)을 찾지 못했습니다.")
            
    except Exception as e:
        print(f"❌ 에러: {e}")

if __name__ == "__main__":
    debug_work24()