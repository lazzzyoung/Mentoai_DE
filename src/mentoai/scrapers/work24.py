import asyncio
import logging
import random
import re
from datetime import UTC, datetime
from typing import Any

import httpx
from bs4 import BeautifulSoup, Tag

from mentoai.config import get_settings

logger = logging.getLogger(__name__)

LIST_URL = "https://www.work24.go.kr/wk/a/b/1200/retriveDtlEmpSrchList.do"
DETAIL_URL = "https://www.work.go.kr/empInfo/empInfoSrch/detail/empDetailAuthView.do"

LIST_PARAMS = {
    "occupation": "135101,135102,136102,026,024",
    "resultCnt": "50",
    "sortField": "DATE",
    "sortOrderBy": "DESC",
    "pageIndex": "1",
    "siteClcd": "all",
}

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


def clean_space(text: str | None) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


async def fetch_list_rows(client: httpx.AsyncClient) -> list[Tag]:
    response = await client.get(LIST_URL, params=LIST_PARAMS)
    soup = BeautifulSoup(response.text, "lxml")
    return soup.find_all("tr", id=re.compile(r"^list\d+"))


def parse_list_row(row: Tag) -> dict[str, str] | None:
    html = str(row)
    auth_match = re.search(r"wantedAuthNo=([a-zA-Z0-9]+)", html)
    if auth_match:
        auth_no = auth_match.group(1)
    else:
        k_match = re.search(r"(K\d{10,})", html)
        if not k_match:
            return None
        auth_no = k_match.group(1)

    cols = row.select("td")
    if len(cols) < 3:
        return None

    td0_parts = cols[0].get_text(separator="|", strip=True).split("|")
    company = td0_parts[0].strip() if td0_parts else "N/A"
    title = "N/A"
    if len(td0_parts) > 1:
        potential = td0_parts[1].strip()
        if "입사지원" in potential or "요약보기" in potential:
            if len(td0_parts) > 2:
                title = td0_parts[2].strip()
        else:
            title = potential

    pay, location = "면접 후 결정", "지역 미상"
    for part in cols[1].get_text(separator="|", strip=True).split("|"):
        part = clean_space(part)
        if any(x in part for x in ["연봉", "월급", "시급"]):
            pay = part
        elif any(x in part for x in ["시 ", "구 ", "군 "]) and "주" not in part:
            location = part

    td2 = cols[2].get_text(separator="|", strip=True)
    reg_match = re.search(r"등록일\s?:\s?(\d{4}-\d{2}-\d{2})", td2)
    reg_date = reg_match.group(1) if reg_match else datetime.now(UTC).strftime("%Y-%m-%d")
    deadline_match = re.search(r"마감일\s?:\s?(\d{4}-\d{2}-\d{2})", td2)
    deadline = deadline_match.group(1) if deadline_match else "채용시까지"

    return {
        "auth_no": auth_no,
        "company": company,
        "title": title,
        "pay": pay,
        "location": location,
        "reg_date": reg_date,
        "deadline": deadline,
    }


def parse_detail_page(html: str) -> dict[str, str]:
    """상세 페이지에서 직무내용/자격/우대 추출. 구조가 달라도 기본값을 반환한다."""
    extracted = {
        "job_description": "상세 내용 없음 (외부 채용 사이트 참조)",
        "requirements": "학력/경력 무관",
        "preferred": "우대사항 없음",
    }
    soup = BeautifulSoup(html, "lxml")
    content_area = soup.find(id="contents") or soup.find(class_="emp_detail")
    if not content_area:
        return extracted

    job_desc_header = content_area.find(
        lambda tag: tag.name == "th" and "직무내용" in tag.get_text()
    )
    if job_desc_header is not None:
        job_desc_body = job_desc_header.find_next_sibling("td")
        if job_desc_body is not None:
            extracted["job_description"] = clean_space(job_desc_body.get_text())

    req_list: list[str] = []
    pref_list: list[str] = []
    for table in content_area.find_all("table"):
        for tr in table.find_all("tr"):
            th, td = tr.find("th"), tr.find("td")
            if th is None or td is None:
                continue
            header_text, body_text = clean_space(th.get_text()), clean_space(td.get_text())
            if not body_text or any(x in body_text for x in ["관계없음", "비희망", "해당없음"]):
                continue
            if any(kw in header_text for kw in ["경력조건", "학력", "모집직종"]):
                req_list.append(f"{header_text}: {body_text}")
            elif any(kw in header_text for kw in ["우대조건", "전공", "자격면허", "외국어", "컴퓨터"]):
                pref_list.append(f"{header_text}: {body_text}")

    if req_list:
        extracted["requirements"] = " | ".join(req_list)
    if pref_list:
        extracted["preferred"] = " | ".join(pref_list)
    return extracted


async def scrape() -> list[dict[str, Any]]:
    """work24(구인구직포털) 공고를 수집해 bronze 레코드로 반환한다."""
    settings = get_settings()
    records: list[dict[str, Any]] = []
    async with httpx.AsyncClient(
        headers={"User-Agent": USER_AGENT}, timeout=15, follow_redirects=True
    ) as client:
        rows = await fetch_list_rows(client)
        logger.info("work24: 리스트 %d행", len(rows))
        for row in rows:
            parsed = parse_list_row(row)
            if parsed is None:
                continue
            try:
                response = await client.get(DETAIL_URL, params={"wantedAuthNo": parsed["auth_no"]})
                detail = parse_detail_page(response.text) if response.status_code == 200 else None
            except httpx.HTTPError as error:
                logger.warning("work24 상세 요청 실패(%s): %s", parsed["auth_no"], error)
                detail = None
            if detail is None:
                detail = {
                    "job_description": "상세 내용 없음",
                    "requirements": "",
                    "preferred": "",
                }

            records.append(
                {
                    "source": "work24",
                    "source_id": parsed["auth_no"],
                    "collected_at": datetime.now(UTC),
                    "payload": {
                        "source_id": parsed["auth_no"],
                        "company": parsed["company"],
                        "title": parsed["title"],
                        "link": f"{DETAIL_URL}?wantedAuthNo={parsed['auth_no']}",
                        "pay": parsed["pay"],
                        "location": parsed["location"],
                        "reg_date": parsed["reg_date"],
                        "deadline": parsed["deadline"],
                        "description": detail["job_description"],
                        "requirements": detail["requirements"],
                        "preferred": detail["preferred"],
                    },
                }
            )
            await asyncio.sleep(settings.scrape_delay_seconds + random.uniform(0, 0.3))
    return records
