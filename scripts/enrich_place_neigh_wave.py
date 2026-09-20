#!/usr/bin/env python3
"""Enrich neighborhood hospital targets from Naver Place search HTML.

Usage:
  python3 scripts/enrich_place_neigh_wave.py \\
    --targets data/hospitals/place-neigh-gyeonggi-wave3-targets.json \\
    --out data/hospitals/place-neigh-gyeonggi-wave3.jsonl \\
    --start 0 --limit 20
"""
from __future__ import annotations

import argparse
import json
import re
import ssl
import time
import urllib.parse
import urllib.request
from pathlib import Path

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
)
REJECT_HP = re.compile(
    r"(instagram\.com|facebook\.com|youtube\.com|saramin\.|"
    r"mypet-119|animal\.go\.kr|carmap\.|jobkorea|wanted\.co)",
    re.I,
)
LARGE_ANIMAL = re.compile(
    r"(축협|가축병원|가축진료|말전문|양계|수산질병|산업동물|대동물전|우시장)"
)
DEPT_WORDS = [
    "내과",
    "외과",
    "치과",
    "안과",
    "피부과",
    "종양",
    "심장",
    "영상",
    "내시경",
    "재활",
    "한방",
    "예방접종",
    "건강검진",
    "중성화",
    "응급",
    "고양이",
    "특수동물",
    "야행성",
    "조류",
    "파충류",
]
GYEONGGI_MARKERS = ("경기", "고양", "성남", "수원", "용인", "부천", "안양", "남양주", "화성", "평택", "김포", "파주", "의정부", "시흥", "광명", "군포", "하남", "오산", "이천", "안성", "양주", "구리", "포천", "의왕", "여주", "동두천", "과천", "가평", "양평", "연천")
OTHER_REGION = re.compile(
    r"(서울특별시|서울시|부산|대구|인천|광주광역|대전|울산|세종|강원|충북|충남|전북|전남|경북|경남|제주|"
    r"서울\s|부산\s|대구\s|인천\s)"
)


def fetch(url: str, timeout: int = 30) -> str:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": UA,
            "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8",
            "Accept": "text/html,application/xhtml+xml",
        },
    )
    ctx = ssl.create_default_context()
    with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
        return r.read().decode("utf-8", "ignore")


def brace_obj(s: str, start: int):
    depth = 0
    i = start
    in_str = False
    esc = False
    while i < len(s):
        ch = s[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
        else:
            if ch == '"':
                in_str = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(s[start : i + 1])
                    except json.JSONDecodeError:
                        return None
        i += 1
    return None


def brace_array(s: str, start: int):
    depth = 0
    i = start
    in_str = False
    esc = False
    while i < len(s):
        ch = s[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
        else:
            if ch == '"':
                in_str = True
            elif ch == "[":
                depth += 1
            elif ch == "]":
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(s[start : i + 1])
                    except json.JSONDecodeError:
                        return None
        i += 1
    return None


def clean_place_name(name: str | None) -> str:
    if not name:
        return ""
    # JSON may still contain escaped mark tags
    name = name.replace("\\u003C", "<").replace("\\u003E", ">").replace("\\u002F", "/")
    name = re.sub(r"</?mark>", "", name)
    return re.sub(r"<[^>]+>", "", name).strip()


def extract_places(html: str) -> list[dict]:
    places: list[dict] = []
    by_id: dict[str, dict] = {}

    def upsert(pid: str, data: dict) -> dict:
        if pid not in by_id:
            by_id[pid] = {
                "id": pid,
                "name": "",
                "phone": None,
                "roadAddress": "",
                "address": "",
                "category": "",
                "description": "",
            }
            places.append(by_id[pid])
        p = by_id[pid]
        for k, v in data.items():
            if v is None or v == "":
                continue
            if k in ("roadAddress", "address") and p.get(k):
                # prefer longer address
                if len(str(v)) > len(str(p.get(k) or "")):
                    p[k] = v
                continue
            if k == "name":
                p[k] = clean_place_name(str(v))
                continue
            if k not in p or not p.get(k):
                p[k] = v
            elif k in ("newBusinessHours", "homepages") and not p.get(k):
                p[k] = v
        return p

    for m in re.finditer(r'"PlaceDetailBase:(\d+)":\{', html):
        pid = m.group(1)
        obj = brace_obj(html, m.end() - 1)
        if not obj:
            continue
        upsert(
            pid,
            {
                "name": obj.get("name"),
                "phone": obj.get("phone") or obj.get("virtualPhone"),
                "roadAddress": obj.get("roadAddress") or "",
                "address": obj.get("address") or "",
                "category": obj.get("category") or "",
                "source": "detail",
            },
        )

    for m in re.finditer(r'"PlaceListBusinessesItem:(\d+)":\{', html):
        pid = m.group(1)
        obj = brace_obj(html, m.end() - 1)
        if not obj:
            continue
        nbh = obj.get("newBusinessHours")
        # normalize list-style hours into array form expected by format_hours
        nbh_arr = None
        if isinstance(nbh, dict):
            nbh_arr = [
                {
                    "freeText": nbh.get("description") or nbh.get("status"),
                    "businessHours": [],
                    "comingRegularClosedDays": nbh.get("dayOffDescription") or "",
                }
            ]
        elif isinstance(nbh, list):
            nbh_arr = nbh
        upsert(
            pid,
            {
                "name": obj.get("name") or obj.get("normalizedName"),
                "phone": obj.get("phone") or obj.get("virtualPhone"),
                "roadAddress": obj.get("fullAddress")
                or obj.get("roadAddress")
                or "",
                "address": obj.get("address") or obj.get("commonAddress") or "",
                "category": obj.get("category") or "",
                "newBusinessHours": nbh_arr,
                "source": "list",
            },
        )

    # Attach hours/homepages/description by scanning near Menu:pid (panel detail)
    for p in places:
        pid = p["id"]
        key = f"Menu:{pid}_"
        idx = html.find(key)
        window = html[max(0, idx - 12000) : idx + 800] if idx > 0 else ""
        search_spaces = [window, html] if len(places) == 1 else ([window] if window else [])
        for space in search_spaces:
            if not space:
                continue
            if not p.get("newBusinessHours") and '"newBusinessHours":[' in space:
                nm = re.search(r'"newBusinessHours":(\[)', space)
                if nm:
                    arr = brace_array(space, nm.end() - 1)
                    if arr:
                        p["newBusinessHours"] = arr
            if not p.get("homepages") and '"homepages"' in space:
                hm = re.search(r'"homepages":(\{)', space)
                if hm:
                    obj = brace_obj(space, hm.end() - 1)
                    if obj and obj.get("__typename") == "Homepage":
                        p["homepages"] = obj
            if not p.get("description"):
                dm = re.search(r'"description"\s*:\s*"((?:\\.|[^"\\])*)"', space)
                if dm:
                    try:
                        p["description"] = json.loads(f'"{dm.group(1)}"')
                    except Exception:
                        p["description"] = dm.group(1)

    # Fallback: panel hours/homepage if single animal hospital place
    animal = [
        p
        for p in places
        if "동물" in (p.get("category") or "") or "동물" in (p.get("name") or "")
    ]
    use = animal or places
    if len(use) == 1:
        p = use[0]
        if not p.get("newBusinessHours"):
            nm = re.search(r'"newBusinessHours":(\[)', html)
            if nm:
                arr = brace_array(html, nm.end() - 1)
                if arr:
                    p["newBusinessHours"] = arr
        if not p.get("homepages"):
            for hm in re.finditer(r'"homepages":(\{)', html):
                obj = brace_obj(html, hm.end() - 1)
                if obj and obj.get("__typename") == "Homepage":
                    p["homepages"] = obj
                    break

    return places


def road_token(addr: str) -> str | None:
    if not addr:
        return None
    m = re.search(r"([가-힣A-Za-z0-9]+(?:로|길)\d*(?:번길)?)", addr.replace(" ", ""))
    return m.group(1) if m else None


def build_queries(t: dict) -> list[str]:
    name = t["name"]
    sigungu = t.get("sigungu") or ""
    addr = t.get("address") or ""
    rt = road_token(addr) or ""
    dong = ""
    m = re.search(r"([가-힣]+(?:동|읍|면))", addr)
    if m:
        dong = m.group(1)
    qs = []
    if sigungu:
        qs.append(f"{name} {sigungu}")
    if rt:
        qs.append(f"{name} {rt}")
    if dong and sigungu:
        qs.append(f"{name} {sigungu} {dong}")
    phone = t.get("phone")
    if phone:
        qs.append(f"{name} {phone}")
    qs.append(f"{name} 경기도")
    # unique preserve order
    out = []
    seen = set()
    for q in qs:
        if q not in seen:
            seen.add(q)
            out.append(q)
    return out


def pick_homepage(hp) -> str | None:
    if not hp:
        return None
    cands = []
    repr_ = hp.get("repr")
    if isinstance(repr_, dict) and repr_.get("url"):
        cands.append(repr_["url"])
    for e in hp.get("etc") or []:
        if isinstance(e, dict) and e.get("url"):
            cands.append(e["url"])
    for url in cands:
        if not url:
            continue
        url = url.strip().rstrip("/")
        if REJECT_HP.search(url):
            continue
        return url
    return None


def format_hours(nbh):
    if not nbh:
        return None, None
    raw_parts = []
    is24 = False
    for block in nbh:
        if not isinstance(block, dict):
            continue
        free = block.get("freeText")
        if free:
            raw_parts.append(str(free))
            if "24시간" in str(free):
                is24 = True
        for wh in block.get("businessHours") or []:
            day = wh.get("day") or ""
            bh = wh.get("businessHours") or {}
            start, end = bh.get("start"), bh.get("end")
            if start and end:
                raw_parts.append(f"{day} {start}~{end}".strip())
                if (start in ("00:00", "0:00") and end in ("24:00", "23:59")) or (
                    "24시간" in day
                ):
                    is24 = True
            for br in wh.get("breakHours") or []:
                if br.get("start") and br.get("end"):
                    raw_parts.append(f"휴게 {br['start']}~{br['end']}")
            for lo in wh.get("lastOrderTimes") or []:
                if lo.get("time"):
                    raw_parts.append(f"접수마감 {lo['time']}")
            if wh.get("description"):
                raw_parts.append(str(wh["description"]))
        reg = block.get("comingRegularClosedDays")
        if reg:
            raw_parts.append(f"정기휴무 {reg}")
    # dedupe preserve order
    seen = set()
    cleaned = []
    for p in raw_parts:
        p = p.strip()
        if not p or p in seen:
            continue
        # skip ephemeral status like "10:00에 진료 시작"
        if re.search(r"진료 (시작|종료)|영업 (시작|종료)", p) and "~" not in p:
            continue
        seen.add(p)
        cleaned.append(p)
    joined = "; ".join(cleaned) if cleaned else None
    if joined and ("24시간" in joined or "00:00~24:00" in joined or "00:00~23:59" in joined):
        is24 = True
    hint = None
    if is24:
        hint = "hours_24h"
    elif joined and re.search(r"(매주\s*)?일요일?\s*휴무|일\s*휴무", joined):
        hint = "sunday_closed"
    elif joined and ("연중무휴" in joined or re.search(r"매일\s+\d", joined)):
        hint = "daily"
    elif joined and "오늘 휴무" in joined and len(cleaned) == 1:
        # status-only, not useful as hours
        return None, None
    return hint, joined


def norm_phone(p: str | None) -> str:
    if not p:
        return ""
    return re.sub(r"\D", "", str(p))


def phones_match(a: str | None, b: str | None) -> bool:
    na, nb = norm_phone(a), norm_phone(b)
    if not na or not nb:
        return False
    return na == nb or na[-8:] == nb[-8:]


def addr_match(target_addr: str, place: dict) -> bool:
    pa = (place.get("roadAddress") or "") + " " + (place.get("address") or "")
    pa_nos = re.sub(r"\s+", "", pa)
    ta_nos = re.sub(r"\s+", "", target_addr or "")
    rt = road_token(target_addr or "")
    if rt and rt in pa_nos:
        return True
    # significant number sequences from target in place
    nums = re.findall(r"\d{2,}", ta_nos)
    dong = re.search(r"([가-힣]+(?:동|읍|면))", ta_nos)
    if dong and dong.group(1) in pa_nos:
        if any(n in pa_nos for n in nums[:3]):
            return True
    # sigungu + road-ish
    for token in re.findall(r"[가-힣]{2,}시|[가-힣]{1,3}구", ta_nos):
        if token in pa_nos and rt and rt[:2] in pa_nos:
            return True
    return False


def in_gyeonggi(place: dict) -> bool:
    text = " ".join(
        [
            place.get("roadAddress") or "",
            place.get("address") or "",
            place.get("name") or "",
        ]
    )
    if "경기" in text:
        return True
    return any(m in text for m in GYEONGGI_MARKERS)


def other_region_note(place: dict) -> str | None:
    text = (place.get("roadAddress") or "") + " " + (place.get("address") or "")
    m = OTHER_REGION.search(text)
    if m:
        return m.group(1).strip()
    return None


def extract_depts(*texts: str) -> list[str]:
    blob = " ".join(t for t in texts if t)
    out = []
    for w in DEPT_WORDS:
        if w in blob and w not in out:
            out.append(w)
    return out


def is_closed_text(*texts: str) -> bool:
    blob = " ".join(t for t in texts if t)
    return bool(re.search(r"(폐업|영업중단|閉店|휴업\s*중|운영\s*종료)", blob))


def check_directory_closed(name: str, address: str) -> tuple[bool, str]:
    """Best-effort closed check via mypet-119 / hospitalk search pages."""
    notes = []
    queries = [
        (
            "mypet-119",
            f"https://www.mypet-119.com/search?q={urllib.parse.quote(name)}",
        ),
        (
            "hospitalk",
            f"https://www.hospitalk.com/search?keyword={urllib.parse.quote(name)}",
        ),
    ]
    rt = road_token(address or "")
    for label, url in queries:
        try:
            html = fetch(url, timeout=15)
        except Exception as e:
            notes.append(f"{label} fetch fail")
            continue
        if "폐업" in html and (name[:4] in html or (rt and rt in html)):
            # crude: name and 폐업 on same page
            if re.search(rf"{re.escape(name[:6])}.{{0,200}}폐업|폐업.{{0,200}}{re.escape(name[:6])}", html):
                return True, f"{label} 폐업 표기"
            if rt and re.search(rf"{re.escape(rt)}.{{0,120}}폐업|폐업.{{0,120}}{re.escape(rt)}", html):
                return True, f"{label} 주소일치 폐업"
        notes.append(f"{label} 폐업미확인")
    return False, "; ".join(notes)


def score_place(t: dict, p: dict) -> tuple[int, list[str]]:
    phone = t.get("phone")
    addr = t.get("address") or ""
    name = t["name"]
    score = 0
    reasons = []
    if phones_match(phone, p.get("phone")):
        score += 3
        reasons.append("전화일치")
    if addr_match(addr, p):
        score += 2
        reasons.append("주소일치")
    pn = re.sub(r"\s+", "", p.get("name") or "")
    tn = re.sub(r"\s+", "", name)
    if tn and pn and (tn[:4] in pn or pn[:4] in tn):
        score += 1
        reasons.append("이름유사")
    if in_gyeonggi(p):
        score += 0  # no score bump; used as filter
    return score, reasons


def enrich_one(t: dict, sleep_s: float = 0.8) -> dict:
    name = t["name"]
    search_url = t.get("place_search_url") or (
        "https://search.naver.com/search.naver?query="
        + urllib.parse.quote(f"{name} 경기도")
    )
    row = {
        "id": t["id"],
        "name": name,
        "place_status": "no_hit",
        "place_homepage": None,
        "place_phone": None,
        "place_hours_hint": None,
        "place_hours_raw": None,
        "place_dept_keywords": [],
        "place_notes": "",
        "place_search_url": search_url,
    }

    # Large animal by name
    if LARGE_ANIMAL.search(name) or LARGE_ANIMAL.search(t.get("address") or ""):
        row["place_status"] = "LARGE_ANIMAL_ONLY_EXCLUDE"
        row["place_notes"] = "시설명/주소 대동물·축협·가축 계열"
        return row

    phone = t.get("phone")
    addr = t.get("address") or ""
    all_places: list[dict] = []
    html_blobs: list[str] = []
    queries = build_queries(t)
    # Prefer target place_search_url first if present
    urls = [search_url]
    for q in queries:
        u = "https://search.naver.com/search.naver?query=" + urllib.parse.quote(q)
        if u not in urls:
            urls.append(u)

    for u in urls[:3]:  # cap fetches per target
        try:
            html = fetch(u)
        except Exception as e:
            row["place_notes"] = f"Naver fetch 실패: {e}"
            time.sleep(sleep_s)
            continue
        time.sleep(sleep_s)
        html_blobs.append(html)
        places = extract_places(html)
        all_places.extend(places)
        # early exit if strong match found
        for p in places:
            sc, _ = score_place(t, p)
            if sc >= 3 and (
                "동물" in (p.get("category") or "") or "동물" in (p.get("name") or "")
            ):
                break
        else:
            continue
        break

    # dedupe places by id, prefer ones with homepages/hours
    by_id: dict[str, dict] = {}
    for p in all_places:
        pid = p["id"]
        if pid not in by_id:
            by_id[pid] = p
        else:
            cur = by_id[pid]
            for k in ("homepages", "newBusinessHours", "description", "phone"):
                if p.get(k) and not cur.get(k):
                    cur[k] = p[k]
            if len(p.get("roadAddress") or "") > len(cur.get("roadAddress") or ""):
                cur["roadAddress"] = p["roadAddress"]
    places = list(by_id.values())

    animal_places = [
        p
        for p in places
        if "동물" in (p.get("category") or "")
        or "동물" in (p.get("name") or "")
        or "병원" in (p.get("name") or "")
    ]
    candidates = animal_places or places

    matched = []
    for p in candidates:
        score, reasons = score_place(t, p)
        if score >= 2 or (score >= 1 and phones_match(phone, p.get("phone"))):
            matched.append((score, reasons, p))
    matched.sort(key=lambda x: -x[0])

    combined_html = "\n".join(html_blobs)[:80000]
    if matched and is_closed_text(combined_html):
        if re.search(
            rf"{re.escape(name[:4])}.{{0,80}}폐업|폐업.{{0,80}}{re.escape(name[:4])}",
            combined_html,
        ):
            row["place_status"] = "CLOSED_EXCLUDE"
            row["place_phone"] = matched[0][2].get("phone") or phone
            row["place_notes"] = "Naver Place/검색 폐업 표기"
            return row

    if not candidates:
        closed, cnote = check_directory_closed(name, addr)
        if closed:
            row["place_status"] = "CLOSED_EXCLUDE"
            row["place_phone"] = phone
            row["place_notes"] = cnote
            return row
        row["place_status"] = "no_hit"
        row["place_phone"] = phone
        row["place_notes"] = "경기도 Place panel/list 미노출"
        return row

    if not matched:
        regions = []
        for p in candidates[:5]:
            if not in_gyeonggi(p):
                r = other_region_note(p)
                if r:
                    regions.append(r)
        same = [
            p
            for p in candidates
            if re.sub(r"\s+", "", name)[:4]
            in re.sub(r"\s+", "", p.get("name") or "")
        ]
        gyeonggi_same = [p for p in same if in_gyeonggi(p)]
        if len(gyeonggi_same) >= 2 and not (
            phone and any(phones_match(phone, p.get("phone")) for p in gyeonggi_same)
        ):
            # if address uniquely matches one, use it
            addr_hits = [p for p in gyeonggi_same if addr_match(addr, p)]
            if len(addr_hits) == 1:
                matched = [(2, ["주소일치"], addr_hits[0])]
            else:
                row["place_status"] = "ambiguous"
                row["place_notes"] = (
                    f"동명 Place {len(gyeonggi_same)}곳, 전화/주소로 불일치 해소 불가"
                )
                return row
        if not matched and regions and not any(in_gyeonggi(p) for p in candidates[:3]):
            row["place_status"] = "no_hit"
            row["place_notes"] = f"경기도 Place 미매칭; 타지역 우세({regions[0]})"
            row["place_phone"] = phone
            return row
        if not matched:
            if len(gyeonggi_same) == 1 and addr_match(addr, gyeonggi_same[0]):
                matched = [(2, ["주소일치"], gyeonggi_same[0])]
            elif len(gyeonggi_same) == 1 and phones_match(
                phone, gyeonggi_same[0].get("phone")
            ):
                matched = [(3, ["전화일치"], gyeonggi_same[0])]
            else:
                closed, cnote = check_directory_closed(name, addr)
                if closed:
                    row["place_status"] = "CLOSED_EXCLUDE"
                    row["place_phone"] = phone
                    row["place_notes"] = cnote
                    return row
                row["place_status"] = "no_hit"
                row["place_phone"] = phone
                row["place_notes"] = "동명/유사 Place 있으나 전화·주소 불일치로 미매칭"
                return row

    top = [m for m in matched if m[0] == matched[0][0]]
    if len(top) > 1 and top[0][0] < 3:
        # Prefer phone+addr unique
        strong = [m for m in matched if m[0] >= 4]
        if len(strong) == 1:
            matched = strong
        else:
            row["place_status"] = "ambiguous"
            row["place_notes"] = f"동명 Place 복수 매칭({len(top)}), 구분 어려움"
            return row

    score, reasons, p = matched[0]
    blob = " ".join(
        [p.get("name") or "", p.get("category") or "", p.get("description") or ""]
    )
    if LARGE_ANIMAL.search(blob):
        row["place_status"] = "LARGE_ANIMAL_ONLY_EXCLUDE"
        row["place_phone"] = p.get("phone") or phone
        row["place_notes"] = "Place 대동물·축협·가축 계열"
        return row

    if is_closed_text(p.get("description") or "", p.get("name") or ""):
        row["place_status"] = "CLOSED_EXCLUDE"
        row["place_phone"] = p.get("phone") or phone
        row["place_notes"] = "Place 폐업/영업종료 표기"
        return row

    # If list hit without homepage, try one more specific panel query
    if not p.get("homepages") and p.get("source") == "list":
        panel_q = f"{clean_place_name(p.get('name'))} {road_token(addr) or t.get('sigungu') or ''}"
        try:
            html2 = fetch(
                "https://search.naver.com/search.naver?query="
                + urllib.parse.quote(panel_q.strip())
            )
            time.sleep(sleep_s)
            for p2 in extract_places(html2):
                if p2["id"] == p["id"] or phones_match(p.get("phone"), p2.get("phone")):
                    if p2.get("homepages"):
                        p["homepages"] = p2["homepages"]
                    if p2.get("newBusinessHours") and (
                        not p.get("newBusinessHours")
                        or (
                            isinstance(p2["newBusinessHours"], list)
                            and p2["newBusinessHours"]
                            and isinstance(p2["newBusinessHours"][0], dict)
                            and p2["newBusinessHours"][0].get("businessHours")
                        )
                    ):
                        p["newBusinessHours"] = p2["newBusinessHours"]
                    if p2.get("description"):
                        p["description"] = p2["description"]
                    break
        except Exception:
            pass

    hp = pick_homepage(p.get("homepages"))
    hint, hours_raw = format_hours(p.get("newBusinessHours"))
    depts = extract_depts(p.get("description") or "", hours_raw or "")

    row["place_status"] = "hit"
    row["place_homepage"] = hp
    row["place_phone"] = p.get("phone") or phone
    row["place_hours_hint"] = hint
    row["place_hours_raw"] = hours_raw
    row["place_dept_keywords"] = depts
    note_bits = [f"{t.get('sigungu','')} Place hit({'·'.join(reasons)})"]
    if hp:
        note_bits.append("홈확인")
    else:
        note_bits.append("홈없음/제외")
    if hours_raw:
        note_bits.append("영업시간확인")
    else:
        note_bits.append("영업시간미노출")
    row["place_notes"] = "; ".join(note_bits)
    return row


def load_existing(path: Path) -> dict[str, dict]:
    if not path.exists():
        return {}
    out = {}
    with path.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            o = json.loads(line)
            out[o["id"]] = o
    return out


def append_rows(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--targets", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--start", type=int, default=0)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--sleep", type=float, default=0.85)
    ap.add_argument("--force-ids", default="", help="comma ids to re-fetch")
    args = ap.parse_args()

    targets = json.loads(Path(args.targets).read_text())["targets"]
    out_path = Path(args.out)
    existing = load_existing(out_path)
    force = set(x for x in args.force_ids.split(",") if x)

    start = args.start
    end = len(targets) if args.limit <= 0 else min(len(targets), start + args.limit)
    batch = targets[start:end]
    new_rows = []
    for i, t in enumerate(batch):
        idx = start + i + 1
        if t["id"] in existing and t["id"] not in force:
            print(f"[{idx}] skip existing {t['id']} {t['name']}")
            continue
        print(f"[{idx}/{len(targets)}] {t['name']} ({t.get('sigungu')}) ...", flush=True)
        row = enrich_one(t, sleep_s=args.sleep)
        print(
            f"  -> {row['place_status']} phone={row['place_phone']} hp={row['place_homepage']} hours={bool(row['place_hours_raw'])}",
            flush=True,
        )
        new_rows.append(row)
        # append immediately for crash safety
        append_rows(out_path, [row])
        existing[row["id"]] = row

    print(f"Wrote {len(new_rows)} new rows to {out_path}")


if __name__ == "__main__":
    main()
