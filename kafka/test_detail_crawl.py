# kafka/test_detail_crawl.py
import requests
from bs4 import BeautifulSoup
import time
import re

def check_url_accessibility(name, url, headers):
    print(f"\n🧪 [테스트: {name}]")
    print(f"   🔗 URL: {url}")
    
    try:
        response = requests.get(url, headers=headers, timeout=5)
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # 1. 페이지 타이틀 확인
        title = soup.title.get_text(strip=True) if soup.title else "No Title"
        print(f"   📄 타이틀: {title}")
        
        # 2. 본문 핵심 키워드 확인 (성공 여부 판단)
        body_text = soup.body.get_text(separator=' ', strip=True) if soup.body else ""
        
        # 성공 시그널: '모집요강', '직무내용', '지원자격' 등이 있어야 함
        success_keywords = ["모집요강", "직무내용", "지원자격", "근무조건", "상세요강"]
        found_success = [kw for kw in success_keywords if kw in body_text]
        
        # 실패 시그널: '로그인', '권한', '비밀번호'
        fail_keywords = ["로그인", "접근 권한", "비밀번호"]
        found_fail = [kw for kw in fail_keywords if kw in body_text[:300]] # 상단에 주로 뜸
        
        if found_success:
            print(f"   ✅ [성공] 채용 공고 본문이 확인되었습니다! (발견된 키워드: {found_success})")
            
            # 본문 추출 시뮬레이션
            # 워크넷(구버전/모바일)은 보통 id='cont' 또는 class='col_wide' 등을 씀
            content = ""
            target_ids = ['contents', 'artclView', 'corpInfoView']
            for tid in target_ids:
                div = soup.find('div', {'id': tid})
                if div:
                    content = div.get_text(strip=True)[:100]
                    break
            print(f"   📝 본문 미리보기: {content}...")
            return True
        elif found_fail:
            print(f"   ❌ [실패] 로그인/보안 페이지로 차단됨 (발견된 키워드: {found_fail})")
            return False
        else:
            print("   ⚠️ [미상] 성공도 실패도 아닌 애매한 상태입니다.")
            return False

    except Exception as e:
        print(f"   ❌ [에러] 요청 실패: {e}")
        return False

def run_test():
    target_auth_no = "K120612601150031" # 테스트용 구인인증번호
    
    # 공통 헤더
    pc_headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) Chrome/120.0.0.0 Safari/537.36'
    }
    
    mobile_headers = {
        'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1'
    }

    # --- 후보 1: 워크넷(Legacy) PC 버전 ---
    # Work24가 아니라 원천 데이터인 Work.go.kr로 접속
    url_1 = f"https://www.work.go.kr/empInfo/empInfoSrch/detail/empDetailAuthView.do?wantedAuthNo={target_auth_no}"
    
    # --- 후보 2: 워크넷(Legacy) 모바일 버전 ---
    # 모바일 페이지는 보안이 느슨한 경우가 많음
    url_2 = f"https://m.work.go.kr/regionJobs/empInfo/empInfoSrch/detail/empDetailAuthView.do?wantedAuthNo={target_auth_no}"
    
    # --- 후보 3: 고용24 모바일 버전 ---
    url_3 = f"https://m.work24.go.kr/wk/a/b/1500/empDetailAuthView.do?wantedAuthNo={target_auth_no}"

    # 테스트 실행
    success_1 = check_url_accessibility("후보 1 (워크넷 PC)", url_1, pc_headers)
    success_2 = check_url_accessibility("후보 2 (워크넷 Mobile)", url_2, mobile_headers)
    success_3 = check_url_accessibility("후보 3 (고용24 Mobile)", url_3, mobile_headers)

    print("\n" + "="*50)
    print("📢 [결론 추천]")
    if success_1:
        print("👉 '후보 1 (워크넷 PC)' 주소를 사용하세요. 가장 안정적입니다.")
    elif success_2:
        print("👉 '후보 2 (워크넷 Mobile)' 주소를 사용하세요. PC 차단을 우회했습니다.")
    elif success_3:
        print("👉 '후보 3 (고용24 Mobile)' 주소를 사용하세요.")
    else:
        print("👉 모든 경로가 막혔습니다. Selenium(브라우저 제어) 방식 도입이 필요할 수 있습니다.")

if __name__ == "__main__":
    run_test()