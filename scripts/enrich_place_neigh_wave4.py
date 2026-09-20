#!/usr/bin/env python3
"""Enrich neighborhood hospitals via Naver Place (search HTML) + Kakao Map search API."""
from __future__ import annotations

import json
import re
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

REJECT_HP = re.compile(
    r"(instagram\.com|facebook\.com|fb\.com|youtube\.com|youtu\.be|"
    r"saramin\.co|jobkorea\.co|mypet-119\.com|animal\.go\.kr|"
    r"ok114\.co|114\.co\.kr|cyber114|korean114|bizno\.net|"
    r"hospitalk\.net|purpleo\.co|bemypet\.kr)",
    re.I,
)
LARGE_ANIMAL = re.compile(
    r"(축협|가축|수산|사슴|마사회|축산|동물약품|가축약품|산업동물|팜스|우사랑)",
)
CLOSED_MARK = re.compile(r"(폐업|휴업|영업중단|폐쇄)")

GYEONGGI = re.compile(r"(경기|고양|성남|용인|부천|안산|안양|남양주|화성|평택|"
                      r"의정부|시흥|파주|김포|광명|광주|군포|하남|오산|이천|"
                      r"안성|의왕|양주|구리|포천|여주|동두천|과천|가평|연천|양평|수원)")


def fetch(url: str, timeout: int = 25) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Referer": "https://www.naver.com/"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", "ignore")


def extract_typename(html: str, typename: str) -> dict | None:
    marker = f'"__typename":"{typename}"'
    i = html.find(marker)
    if i < 0:
        return None
    j = i
    while j > 0 and html[j] != "{":
        j -= 1
    depth = 0
    for p in range(j, min(len(html), j + 400000)):
        c = html[p]
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(html[j : p + 1])
                except json.JSONDecodeError:
                    return None
    return None


def normalize_phone(p: str | None) -> str:
    if not p:
        return ""
    return re.sub(r"[^0-9]", "", p)


def phones_equal(a: str | None, b: str | None) -> bool:
    na, nb = normalize_phone(a), normalize_phone(b)
    if not na or not nb:
        return False
    if na == nb:
        return True
    # 0507 virtual vs landline — compare last 8 if both long
    if len(na) >= 8 and len(nb) >= 8 and na[-8:] == nb[-8:]:
        return True
    # strip leading 0 / country
    return na[-7:] == nb[-7:] and len(na) >= 7 and len(nb) >= 7


def addr_overlap(a: str, b: str) -> bool:
    if not a or not b:
        return False
    a, b = a.replace(" ", ""), b.replace(" ", "")
    # road name token
    for tok in re.findall(r"[가-힣]+(?:로|길)\d*", a):
        if tok and tok in b:
            return True
    for tok in re.findall(r"\(([^)]+)\)", a):
        if tok and tok in b:
            return True
    return False


def region_is_gyeonggi(text: str) -> bool:
    if not text:
        return False
    if re.search(r"(서울|인천|부산|대구|대전|광주광역|울산|강원|충북|충남|전북|전남|경북|경남|제주|세종)", text):
        # allow 경기 explicitly
        if "경기" in text or "수원" in text:
            return True
        # Gwangju-si vs Gwangju metro: "광주시" with 경기
        if "광주" in text and "경기" not in text and "전남" not in text:
            # ambiguous — rely on other signals
            pass
        if re.search(r"(서울|인천|부산|대구|대전|울산|강원|충북|충남|전북|전남|경북|경남|제주)", text):
            if "경기" not in text:
                return False
    return bool(GYEONGGI.search(text))


def format_hours(nb: dict | None) -> tuple[str | None, str | None]:
    if not nb:
        return None, None
    parts: list[str] = []
    desc = (nb.get("businessStatusDescription") or {}).get("description")
    status = (nb.get("businessStatusDescription") or {}).get("status")
    free = nb.get("freeText")
    if isinstance(free, str) and free.strip():
        parts.append(free.strip())
    elif isinstance(free, list):
        parts.extend(str(x).strip() for x in free if x)

    day_parts: list[str] = []
    for wh in nb.get("businessHours") or []:
        day = wh.get("day") or ""
        d = wh.get("description")
        bh = wh.get("businessHours")
        br = wh.get("breakHours") or []
        lo = wh.get("lastOrderTimes")
        if d:
            day_parts.append(d if not day else f"{d}")
        if bh and isinstance(bh, dict) and bh.get("start") and bh.get("end"):
            seg = f"{day} {bh['start']}~{bh['end']}".strip()
            day_parts.append(seg)
            for b in br:
                if isinstance(b, dict) and b.get("start"):
                    day_parts.append(f"휴게 {b['start']}~{b['end']}")
            if lo:
                if isinstance(lo, list):
                    for t in lo:
                        if isinstance(t, dict) and t.get("time"):
                            day_parts.append(f"접수마감 {t['time']}")
                        elif isinstance(t, str):
                            day_parts.append(f"접수마감 {t}")
                elif isinstance(lo, str):
                    day_parts.append(f"접수마감 {lo}")
        elif d and day and "휴무" in d:
            pass  # already added

    # Prefer concise: status description + unique day lines
    seen = set()
    ordered: list[str] = []
    if desc:
        ordered.append(desc)
    for p in day_parts:
        if p and p not in seen:
            seen.add(p)
            ordered.append(p)
    for p in parts:
        if p and p not in seen:
            seen.add(p)
            ordered.append(p)

    raw = "; ".join(ordered) if ordered else None
    if not raw and status:
        raw = status

    hint = None
    blob = raw or ""
    if re.search(r"24시간|00:00\s*[~～-]\s*24:00|00:00\s*[~～-]\s*00:00", blob):
        hint = "hours_24h"
    elif re.search(r"매주\s*일요일\s*휴무|정기휴무\s*\(매주\s*일요일\)", blob) and not re.search(
        r"일\s*\d{1,2}:\d{2}", blob
    ):
        hint = "sunday_closed"
    elif re.search(r"매일\s*\d", blob) or (status and "매일" in status):
        hint = "daily"

    return hint, raw


def accept_homepage(url: str | None) -> str | None:
    if not url:
        return None
    url = url.strip()
    if not url.startswith("http"):
        url = "http://" + url
    if REJECT_HP.search(url):
        return None
    # aggregator directories often on hospitalk etc — allow blog/cafe/naver and own domains
    return url


def kakao_search(query: str) -> list[dict]:
    q = urllib.parse.quote(query)
    url = f"https://search.map.kakao.com/mapsearch/map.daum?q={q}&msFlag=S&sort=0"
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Referer": "https://map.kakao.com/"})
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read().decode("utf-8", "ignore"))
        return data.get("place") or []
    except Exception:
        return []


def naver_search_html(query: str) -> str:
    q = urllib.parse.quote(query)
    url = f"https://search.naver.com/search.naver?query={q}"
    try:
        return fetch(url)
    except Exception:
        return ""


def parse_naver_place(html: str) -> dict[str, Any]:
    out: dict[str, Any] = {}
    if not html:
        return out
    base = extract_typename(html, "PlaceDetailBase")
    nb = extract_typename(html, "NewBusinessHour")
    hp = extract_typename(html, "Homepage")
    if base:
        out["name"] = base.get("name")
        out["phone"] = base.get("virtualPhone") or base.get("phone")
        out["landline"] = base.get("phone")
        out["address"] = base.get("roadAddress") or base.get("address")
        out["place_id"] = base.get("id")
        out["category"] = base.get("category")
        # conveniences / micro reviews as dept hints
        conv = base.get("conveniences") or []
        out["conveniences"] = conv
    if hp and isinstance(hp.get("repr"), dict):
        out["homepage"] = hp["repr"].get("url") or hp["repr"].get("landingUrl")
    hint, raw = format_hours(nb)
    out["hours_hint"] = hint
    out["hours_raw"] = raw
    # closed markers in HTML near panel
    if base and CLOSED_MARK.search(html[html.find("PlaceDetailBase") : html.find("PlaceDetailBase") + 5000] if "PlaceDetailBase" in html else ""):
        out["closed_hint"] = True
    if re.search(r"이\s*장소는\s*폐업|폐업한\s*장소|영업중단", html):
        out["closed_hint"] = True
    return out


def dept_keywords(text: str) -> list[str]:
    keys = []
    for k in ["내과", "외과", "치과", "안과", "피부", "영상", "재활", "한방", "야간", "응급", "중성화", "슬개골", "고양이"]:
        if k in (text or ""):
            keys.append(k)
    return keys


def enrich_one(t: dict) -> dict:
    name = t["name"]
    sigungu = t.get("sigungu") or ""
    addr = t.get("address") or ""
    phone = t.get("phone")
    search_url = t.get("place_search_url") or ""

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

    # LARGE_ANIMAL by name
    if LARGE_ANIMAL.search(name) or LARGE_ANIMAL.search(addr):
        row["place_status"] = "LARGE_ANIMAL_ONLY_EXCLUDE"
        row["place_notes"] = "시설명/주소 대동물·축협·가축·수산·약품 계열"
        row["place_phone"] = phone
        return row

    # Build queries: specific first
    queries = []
    if sigungu:
        queries.append(f"{name} {sigungu}")
    # street token
    m = re.search(r"([가-힣]+(?:로|길)\d*(?:번길)?)", addr)
    if m:
        queries.append(f"{name} {m.group(1)}")
    if phone:
        queries.append(f"{name} {phone}")
    queries.append(f"{name} 경기도")
    # dedupe
    seen_q = set()
    uniq_q = []
    for q in queries:
        if q not in seen_q:
            seen_q.add(q)
            uniq_q.append(q)

    naver_hit = None
    naver_html = ""
    for q in uniq_q[:3]:
        naver_html = naver_search_html(q)
        parsed = parse_naver_place(naver_html)
        if not parsed.get("name"):
            time.sleep(0.4)
            continue
        # match quality
        p_addr = parsed.get("address") or ""
        p_phone = parsed.get("phone") or parsed.get("landline")
        name_ok = name.replace(" ", "") in (parsed.get("name") or "").replace(" ", "") or (
            parsed.get("name") or ""
        ).replace(" ", "") in name.replace(" ", "")
        phone_ok = phones_equal(phone, p_phone) or phones_equal(phone, parsed.get("landline"))
        addr_ok = addr_overlap(addr, p_addr) or (sigungu and sigungu.replace(" ", "")[:2] in p_addr.replace(" ", ""))
        gy_ok = region_is_gyeonggi(p_addr) or ("경기" in p_addr)

        if parsed.get("closed_hint") and (phone_ok or addr_ok or name_ok):
            row["place_status"] = "CLOSED_EXCLUDE"
            row["place_phone"] = p_phone or phone
            row["place_notes"] = f"{sigungu} Place 폐업 표기"
            return row

        if not gy_ok and not phone_ok:
            # other region dominating
            time.sleep(0.35)
            continue

        if phone_ok or (name_ok and addr_ok) or (name_ok and gy_ok and addr_ok):
            naver_hit = parsed
            break
        if name_ok and gy_ok and (phone_ok or addr_ok or not phone):
            naver_hit = parsed
            break
        time.sleep(0.35)

    # Kakao / Daum Map
    kakao_places = []
    for q in uniq_q[:2]:
        kakao_places = kakao_search(q)
        if kakao_places:
            break
        time.sleep(0.25)

    kakao_match = None
    kakao_gy = []
    for p in kakao_places:
        p_addr = p.get("new_address") or p.get("address") or ""
        p_tel = p.get("tel") or ""
        p_name = p.get("name") or ""
        phone_ok = phones_equal(phone, p_tel)
        addr_ok = addr_overlap(addr, p_addr) or (sigungu and sigungu[:2] in p_addr)
        name_ok = name.replace(" ", "") in p_name.replace(" ", "") or p_name.replace(" ", "") in name.replace(" ", "")
        gy_ok = region_is_gyeonggi(p_addr) or "경기" in p_addr
        if gy_ok and (phone_ok or (name_ok and addr_ok) or (name_ok and gy_ok)):
            kakao_gy.append(p)
            if phone_ok or (name_ok and addr_ok):
                kakao_match = p
                break
    if not kakao_match and len(kakao_gy) == 1:
        kakao_match = kakao_gy[0]
    elif not kakao_match and len(kakao_gy) > 1:
        # try phone
        for p in kakao_gy:
            if phones_equal(phone, p.get("tel")):
                kakao_match = p
                break

    # Merge decision
    if naver_hit or kakao_match:
        notes_bits = []
        match_bits = []
        homepage = None
        out_phone = None
        hours_hint = None
        hours_raw = None

        if naver_hit:
            out_phone = naver_hit.get("phone") or naver_hit.get("landline")
            homepage = accept_homepage(naver_hit.get("homepage"))
            hours_hint = naver_hit.get("hours_hint")
            hours_raw = naver_hit.get("hours_raw")
            p_addr = naver_hit.get("address") or ""
            if phones_equal(phone, out_phone) or phones_equal(phone, naver_hit.get("landline")):
                match_bits.append("전화일치")
            if addr_overlap(addr, p_addr):
                match_bits.append("주소일치")
            match_bits.append("이름유사")
            notes_bits.append(f"{sigungu} Place hit({ '·'.join(match_bits) })")
            if homepage:
                notes_bits.append("홈확인")
            else:
                notes_bits.append("홈없음/제외")
            if hours_raw:
                notes_bits.append("영업시간확인")
            else:
                notes_bits.append("영업시간미노출")

        if kakao_match:
            k_tel = kakao_match.get("tel") or ""
            k_hp = accept_homepage(kakao_match.get("homepage") or None)
            k_addr = kakao_match.get("new_address") or kakao_match.get("address") or ""
            if not out_phone and k_tel:
                out_phone = k_tel
            if not homepage and k_hp:
                homepage = k_hp
                if "홈확인" not in " ".join(notes_bits):
                    notes_bits.append("Daum홈확인")
            if not naver_hit:
                mb = []
                if phones_equal(phone, k_tel):
                    mb.append("전화일치")
                if addr_overlap(addr, k_addr):
                    mb.append("주소일치")
                mb.append("이름유사")
                notes_bits.append(f"{sigungu} Daum Map hit({ '·'.join(mb) })")
                if homepage:
                    notes_bits.append("홈확인")
                else:
                    notes_bits.append("홈없음/제외")
                notes_bits.append("영업시간미노출")

        # ambiguous: multiple same-name in gyeonggi without phone/addr lock
        if not naver_hit and kakao_match is None and len(kakao_gy) > 1:
            row["place_status"] = "ambiguous"
            row["place_notes"] = f"{sigungu} 동명이 다수·전화/주소 불일치"
            row["place_phone"] = phone
            return row

        row["place_status"] = "hit"
        row["place_phone"] = out_phone or phone
        row["place_homepage"] = homepage
        row["place_hours_hint"] = hours_hint
        row["place_hours_raw"] = hours_raw
        row["place_dept_keywords"] = dept_keywords(
            " ".join(
                [
                    str(naver_hit.get("conveniences") if naver_hit else ""),
                    hours_raw or "",
                ]
            )
        )
        row["place_notes"] = "; ".join(notes_bits)
        return row

    # CLOSED only on explicit "(폐업)" adjacent to this hospital name (not a "폐업" query).
    blob = naver_html or ""
    if re.search(rf"{re.escape(name)}\s*\(폐업\)|{re.escape(name)}\(폐업\)", blob):
        row["place_status"] = "CLOSED_EXCLUDE"
        row["place_phone"] = phone
        row["place_notes"] = f"{sigungu} 검색결과 이름옆 폐업 표기 → CLOSED_EXCLUDE"
        return row

    # other region dominates in kakao first results
    if kakao_places and not kakao_gy:
        top = kakao_places[0]
        taddr = top.get("new_address") or top.get("address") or ""
        if taddr and not region_is_gyeonggi(taddr) and "경기" not in taddr:
            row["place_status"] = "no_hit"
            row["place_phone"] = phone
            row["place_notes"] = f"{sigungu} Place 미노출; 타지역({taddr.split()[0] if taddr else '?'}) 우세 → no_hit"
            return row

    row["place_status"] = "no_hit"
    row["place_phone"] = phone
    row["place_notes"] = f"{sigungu} Place/Daum 패널 미확보 → no_hit"
    return row


def main():
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--start", type=int, default=0)
    ap.add_argument("--end", type=int, default=None)
    ap.add_argument("--targets", default="data/hospitals/place-neigh-gyeonggi-wave4-targets.json")
    ap.add_argument("--out", default="data/hospitals/place-neigh-gyeonggi-wave4.jsonl")
    args = ap.parse_args()

    targets = json.load(open(args.targets))["targets"]
    end = args.end if args.end is not None else len(targets)
    out_path = Path(args.out)

    existing: dict[str, dict] = {}
    order: list[str] = [t["id"] for t in targets]
    if out_path.exists():
        for line in out_path.read_text().splitlines():
            if not line.strip():
                continue
            r = json.loads(line)
            existing[r["id"]] = r

    for i in range(args.start, end):
        t = targets[i]
        if t["id"] in existing and existing[t["id"]].get("place_status"):
            print(f"[{i}] skip {t['name']}")
            continue
        print(f"[{i}] enrich {t['sigungu']} {t['name']} ...", flush=True)
        row = enrich_one(t)
        existing[t["id"]] = row
        print(f"    -> {row['place_status']} phone={row['place_phone']} hours={bool(row['place_hours_raw'])} hp={row['place_homepage']}", flush=True)
        # rewrite full file in target order for checkpoint safety
        with out_path.open("w", encoding="utf-8") as f:
            for tid in order:
                if tid in existing:
                    f.write(json.dumps(existing[tid], ensure_ascii=False) + "\n")
        time.sleep(0.55)

    # final rewrite
    with out_path.open("w", encoding="utf-8") as f:
        for tid in order:
            if tid in existing:
                f.write(json.dumps(existing[tid], ensure_ascii=False) + "\n")

    from collections import Counter

    statuses = Counter(existing[tid]["place_status"] for tid in order if tid in existing)
    print("DONE", len(existing), dict(statuses))


if __name__ == "__main__":
    main()
