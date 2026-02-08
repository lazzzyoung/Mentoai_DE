import re
import time
from typing import Any

DEFAULT_DETAIL = {"job_description": "수집 에러", "requirements": "", "preferred": ""}
DEFAULT_PAY = "면접 후 결정"
DEFAULT_LOCATION = "지역 미상"
DEFAULT_TITLE = "N/A"
WORKNET_DETAIL_URL = (
    "https://www.work.go.kr/empInfo/empInfoSrch/detail/empDetailAuthView.do"
)

_AUTH_NO_PATTERN = re.compile(r"wantedAuthNo=([a-zA-Z0-9]+)")
_FALLBACK_AUTH_NO_PATTERN = re.compile(r"(K\d{10,})")
_REG_DATE_PATTERN = re.compile(r"등록일\s?:\s?(\d{4}-\d{2}-\d{2})")
_DEADLINE_PATTERN = re.compile(r"마감일\s?:\s?(\d{4}-\d{2}-\d{2})")


def build_worknet_link(auth_no: str) -> str:
    return f"{WORKNET_DETAIL_URL}?wantedAuthNo={auth_no}"


def parse_auth_no(row_html: str) -> str | None:
    auth_match = _AUTH_NO_PATTERN.search(row_html)
    if auth_match:
        return auth_match.group(1)

    fallback_match = _FALLBACK_AUTH_NO_PATTERN.search(row_html)
    if fallback_match:
        return fallback_match.group(1)

    return None


def parse_list_row(row: Any) -> dict[str, str] | None:
    auth_no = parse_auth_no(str(row))
    if not auth_no:
        return None

    cols = row.select("td")
    if len(cols) < 3:
        return None

    td0_parts = cols[0].get_text(separator="|", strip=True).split("|")
    company = td0_parts[0].strip() if td0_parts else "N/A"
    title = _parse_title(td0_parts)

    td1_parts = cols[1].get_text(separator="|", strip=True).split("|")
    pay, location = _parse_pay_and_location(td1_parts)

    td2_text = cols[2].get_text(separator="|", strip=True)
    reg_date = _extract_first_match(
        _REG_DATE_PATTERN, td2_text, time.strftime("%Y-%m-%d")
    )
    deadline = _extract_first_match(_DEADLINE_PATTERN, td2_text, "채용시까지")

    return {
        "auth_no": auth_no,
        "company": company,
        "title": title,
        "pay": pay,
        "location": location,
        "reg_date": reg_date,
        "deadline": deadline,
    }


def build_job_message(
    parsed_row: dict[str, str], detail: dict[str, str] | None
) -> dict[str, str]:
    detail_payload = detail or DEFAULT_DETAIL
    auth_no = parsed_row["auth_no"]

    return {
        "source": "recruit24",
        "source_id": auth_no,
        "company": parsed_row["company"],
        "title": parsed_row["title"],
        "link": build_worknet_link(auth_no),
        "pay": parsed_row["pay"],
        "location": parsed_row["location"],
        "deadline": parsed_row["deadline"],
        "reg_date": parsed_row["reg_date"],
        "description": detail_payload.get(
            "job_description", DEFAULT_DETAIL["job_description"]
        ),
        "requirements": detail_payload.get(
            "requirements", DEFAULT_DETAIL["requirements"]
        ),
        "preferred_qualifications": detail_payload.get(
            "preferred", DEFAULT_DETAIL["preferred"]
        ),
        "collected_at": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


def _parse_title(td0_parts: list[str]) -> str:
    if len(td0_parts) <= 1:
        return DEFAULT_TITLE

    potential_title = td0_parts[1].strip()
    if "입사지원" in potential_title or "요약보기" in potential_title:
        if len(td0_parts) > 2:
            return td0_parts[2].strip()
        return DEFAULT_TITLE
    return potential_title


def _parse_pay_and_location(parts: list[str]) -> tuple[str, str]:
    pay = DEFAULT_PAY
    location = DEFAULT_LOCATION

    for part in parts:
        part = clean_space(part)
        if any(keyword in part for keyword in ("연봉", "월급", "시급")):
            pay = part
        elif (
            any(keyword in part for keyword in ("시 ", "구 ", "군 "))
            and "주" not in part
        ):
            location = part

    return pay, location


def _extract_first_match(pattern: re.Pattern[str], text: str, default: str) -> str:
    match = pattern.search(text)
    if match:
        return match.group(1)
    return default


def clean_space(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()
