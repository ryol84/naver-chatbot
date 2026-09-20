#!/usr/bin/env python3
"""Enrich place-neigh-final-wave1 targets via Kakao Map search + Naver Place panel."""
from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
TARGETS = ROOT / "data/hospitals/place-neigh-final-wave1-targets.json"
OUT = ROOT / "data/hospitals/place-neigh-final-wave1.jsonl"

UA = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    )
}

AGGREGATOR_HOSTS = (
    "instagram.com",
    "facebook.com",
    "pf.kakao.com",
    "smartstore.naver.com",
    "booking.naver.com",
    "map.naver.com",
    "place.map.kakao.com",
    "modoo.at",
    "blog.naver.com/PostView",
    "cafe.naver.com",
    "youtube.com",
    "youtu.be",
    "tistory.com",
    "linktr.ee",
    "daum.net",
    "kakao.com/channel",
    "mypetlife.co.kr",
    "petfriends.co.kr",
    "animal.go.kr",
    "fah.purpleo",
    "onkorea.co.kr",
    "sungyesa.com",
    "bemypet",
    "saramin",
    "jobkorea",
)

LARGE_ANIMAL_RE = re.compile(
    r"(축협|가축|축산|수산|양돈|피그|대동물|한우|낙농|말병원|마필|우마)"
)
CLOSED_RE = re.compile(r"(폐업|영업중단|휴업중|닫았|폐쇄)")

DEPT_KEYS = [
    ("24시", ["24시", "24시간", "연중무휴"]),
    ("고양이", ["고양이", "캣", "cat"]),
    ("피부", ["피부"]),
    ("치과", ["치과"]),
    ("외과", ["외과"]),
    ("내과", ["내과"]),
    ("안과", ["안과"]),
    ("특수동물", ["특수동물", "이구아나", "햄스터", "토끼", "조류"]),
    ("중성화", ["중성화"]),
    ("심장", ["심장"]),
    ("양돈", ["양돈", "피그", "돼지"]),
    ("대동물", ["대동물", "가축", "한우", "축산"]),
]


def fetch(url: str, referer: str, timeout: float = 35) -> bytes:
    req = urllib.request.Request(
        url,
        headers={**UA, "Referer": referer, "Accept-Language": "ko-KR,ko;q=0.9"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def kakao_search(q: str) -> list[dict[str, Any]]:
    url = "https://search.map.kakao.com/mapsearch/map.daum?" + urllib.parse.urlencode(
        {"q": q, "msFlag": "S", "sort": "0"}
    )
    try:
        data = json.loads(fetch(url, "https://map.kakao.com/"))
    except Exception as e:
        print(f"  kakao err: {e}")
        return []
    return data.get("place") or []


def naver_html(q: str) -> str:
    url = "https://search.naver.com/search.naver?" + urllib.parse.urlencode({"query": q})
    try:
        return fetch(url, "https://www.naver.com/").decode("utf-8", "ignore")
    except Exception as e:
        print(f"  naver err: {e}")
        return ""


def norm_phone(p: str | None) -> str:
    if not p:
        return ""
    d = re.sub(r"\D", "", p)
    if d.startswith("82"):
        d = "0" + d[2:]
    return d


def phones_equal(a: str | None, b: str | None) -> bool:
    na, nb = norm_phone(a), norm_phone(b)
    if not na or not nb:
        return False
    if na == nb:
        return True
    # last 8 digits often enough for local
    return len(na) >= 8 and len(nb) >= 8 and na[-8:] == nb[-8:]


def normalize_name(n: str) -> str:
    n = n.lower().replace(" ", "")
    n = n.replace("종합", "").replace("동물메디컬센터", "동물병원").replace("동물병원", "동물병원")
    n = re.sub(r"[()\[\]·./\-]", "", n)
    return n


def core_name(n: str) -> str:
    """Strip hospital suffix for comparison, keep distinctive stem."""
    n = normalize_name(n)
    n = re.sub(r"동물병원$", "", n)
    n = re.sub(r"동물메디컬(센터)?$", "", n)
    return n


def name_similar(a: str, b: str) -> bool:
    """Strict-ish name match: exact core, or one contains the other without large-animal extras."""
    ca, cb = core_name(a), core_name(b)
    if not ca or not cb:
        return False
    if ca == cb:
        return True
    # Allow minor prefix/suffix like '24시X' / 'X본점'
    for x, y in ((ca, cb), (cb, ca)):
        if y.endswith(x) or y.startswith(x):
            extra = y[len(x) :] if y.startswith(x) else y[: -len(x)]
            # reject if extra adds livestock/co-op branding or another brand
            if LARGE_ANIMAL_RE.search(extra):
                return False
            if len(extra) <= 4 and not re.search(r"축협|농협|가축|수의|클리닉|센터", extra):
                return True
    # containment only when lengths close (avoid 경산 ⊂ 경산축산농협)
    if ca in cb or cb in ca:
        shorter, longer = (ca, cb) if len(ca) <= len(cb) else (cb, ca)
        if len(longer) - len(shorter) <= 2:
            return True
    return False


def region_tokens(t: dict[str, Any]) -> set[str]:
    toks = set()
    for key in ("sido", "sigungu"):
        v = (t.get(key) or "").strip()
        if not v:
            continue
        toks.add(v)
        # shorten: 경기도->경기, 인천광역시->인천, 창녕군->창녕
        short = re.sub(r"(특별자치|광역|특별)?(시|도|군|구)$", "", v)
        short = short.replace("특별자치", "").replace("광역시", "").replace("특별시", "")
        if short:
            toks.add(short)
    addr = t.get("address") or ""
    for m in re.findall(r"([가-힣]+(?:시|군|구|읍|면|동))", addr):
        toks.add(m)
        toks.add(re.sub(r"(시|군|구|읍|면|동)$", "", m))
    return {x for x in toks if len(x) >= 2}


def addr_region_match(place_addr: str, t: dict[str, Any]) -> bool:
    if not place_addr:
        return False
    toks = region_tokens(t)
    # require sigungu or strong sido+dong match
    sig = (t.get("sigungu") or "").strip()
    sig_short = re.sub(r"(시|군|구)$", "", sig) if sig else ""
    if sig and sig in place_addr:
        return True
    if sig_short and len(sig_short) >= 2 and sig_short in place_addr:
        return True
    # road number fragment from target address
    addr = t.get("address") or ""
    roads = re.findall(r"([가-힣0-9]+(?:로|길))\s*(\d+)", addr)
    for road, num in roads:
        if road in place_addr and num in place_addr:
            return True
    sido = (t.get("sido") or "").strip()
    sido_short = (
        sido.replace("특별자치도", "")
        .replace("광역시", "")
        .replace("특별시", "")
        .replace("도", "")
        .replace("특별자치시", "")
    )
    # cross-region: if place clearly in different metro, reject
    metros = ["서울", "부산", "대구", "인천", "광주", "대전", "울산", "세종", "제주"]
    place_metro = next((m for m in metros if m in place_addr[:8]), None)
    target_metro = next((m for m in metros if m in (sido or "") or m in (addr[:6])), None)
    if place_metro and target_metro and place_metro != target_metro:
        return False
    # weak: sido short present
    if sido_short and sido_short in place_addr:
        # also need some local token
        local = [x for x in toks if x not in (sido, sido_short) and len(x) >= 2]
        if any(x in place_addr for x in local[:8]):
            return True
    return False


def is_allowed_homepage(url: str | None) -> str | None:
    if not url:
        return None
    u = url.strip().replace("\\u002F", "/").replace("\\/", "/")
    if not u.startswith("http"):
        u = "https://" + u
    low = u.lower()
    # hospital blog.naver.com OK
    if "blog.naver.com" in low:
        # reject generic post viewers without blog id path depth
        if re.search(r"blog\.naver\.com/[a-zA-Z0-9_.\-]+/?$", low) or re.search(
            r"blog\.naver\.com/[a-zA-Z0-9_.\-]+", low
        ):
            # strip tracking
            return u.split("?")[0].rstrip("/")
        return None
    for bad in AGGREGATOR_HOSTS:
        if bad in low:
            return None
    # allow hospital own domains lightly
    if any(x in low for x in (".co.kr", ".com", ".kr", ".net")):
        # still reject map/search aggregators already covered
        return u.split("?")[0]
    return None


def format_hours_from_chunk(chunk: str) -> tuple[str | None, str | None]:
    """Return (hours_raw, hours_hint) from a newBusinessHours JSON chunk."""
    # status description
    status_m = re.search(
        r'"businessStatusDescription":\{[^}]*?"description":(?:null|"([^"]*)")',
        chunk,
    )
    status_desc = status_m.group(1) if status_m and status_m.group(1) else None

    day_blocks = re.findall(
        r'\{\s*"__typename":"WorkingHoursInfo","day":"([^"]+)",'
        r'"businessHours":(null|\{[^}]+\}),'
        r'"breakHours":(null|\[[^\]]*\]),'
        r'"description":(null|"[^"]*")',
        chunk,
    )
    parts: list[str] = []
    sunday_closed = False
    has_lunch = False
    has_daytime = False
    is_24 = False

    for day, bh, brk, desc in day_blocks:
        desc_s = None if desc == "null" else desc.strip('"')
        day_clean = re.sub(r"\([^)]*\)", "", day).strip()
        if bh == "null":
            if desc_s:
                parts.append(f"{day} {desc_s}")
                if "휴무" in desc_s or "휴진" in desc_s:
                    if day_clean.startswith("일"):
                        sunday_closed = True
            continue
        st = re.search(r'"start":"([^"]+)","end":"([^"]+)"', bh)
        if not st:
            continue
        start, end = st.group(1), st.group(2)
        if start in ("00:00", "0:00") and end in ("24:00", "23:59"):
            is_24 = True
        has_daytime = True
        s = f"{day} {start}-{end}"
        breaks = re.findall(r'"start":"([^"]+)","end":"([^"]+)"', brk if brk != "null" else "")
        if breaks:
            has_lunch = True
            s += f" (휴게 {breaks[0][0]}-{breaks[0][1]})"
        if desc_s:
            s += f" {desc_s}"
        parts.append(s)
        if day_clean.startswith("일") and desc_s and ("휴무" in desc_s or "휴진" in desc_s):
            sunday_closed = True

    # lastOrder times optional — skip to keep compact
    if not parts and status_desc:
        parts.append(status_desc)

    # freeText
    ft = re.search(r'"freeText":"([^"]*)"', chunk)
    if ft and ft.group(1):
        parts.append(ft.group(1))

    raw = " | ".join(parts) if parts else None
    if raw:
        raw = raw.replace("\\u002F", "/")

    hint = None
    if is_24 or (raw and re.search(r"00:00\s*[-~]\s*24:00|매일\s*00:00", raw)):
        hint = "24h_or_always"
    elif sunday_closed and has_lunch:
        hint = "sunday_closed+daytime_with_lunch"
    elif sunday_closed and has_daytime:
        hint = "sunday_closed+daytime"
    elif sunday_closed or (status_desc and "일요일" in status_desc and "휴무" in status_desc):
        hint = "sunday_closed"
    elif has_daytime:
        hint = "daytime"

    # 24h only if literal
    if hint and "24" in (hint or "") and raw:
        if not re.search(r"24|00:00\s*[-~]\s*24:00|연중무휴", raw):
            # don't invent
            pass

    return raw, hint


def extract_naver_panel(html: str, name: str) -> dict[str, Any]:
    out: dict[str, Any] = {}
    if not html:
        return out

    # closed markers near name
    if CLOSED_RE.search(html[:8000]) and name[:4] in html:
        # weak signal only — confirm later
        pass

    # Find PlaceDetailBase with matching name
    place_ids = []
    for m in re.finditer(
        r'"__typename":"PlaceDetailBase","id":"(\d+)","name":"([^"]+)"', html
    ):
        pid, pname = m.group(1), unescape_json(m.group(2))
        if name_similar(name, pname):
            place_ids.append((pid, pname, m.start()))
    if place_ids:
        out["place_id"] = place_ids[0][0]
        out["place_name"] = place_ids[0][1]

    # newBusinessHours — prefer chunk containing our name
    for m in re.finditer(r'"newBusinessHours":(\[)', html):
        start = m.start()
        chunk = html[start : start + 6000]
        # check name proximity
        nm = re.search(r'"name":"([^"]+)"', chunk)
        pname = unescape_json(nm.group(1)) if nm else ""
        if pname and not name_similar(name, pname) and out.get("place_name"):
            if not name_similar(name, pname):
                continue
        if pname and not name_similar(name, pname):
            continue
        raw, hint = format_hours_from_chunk(chunk)
        if raw:
            out["hours_raw"] = raw
            out["hours_hint"] = hint
            out["hours_name"] = pname
            break

    # homepage near place
    for m in re.finditer(
        r'"homepages":\{"__typename":"Homepage".*?"url":"([^"]+)"', html
    ):
        # check nearby name
        ctx = html[max(0, m.start() - 800) : m.start() + 200]
        if name_similar(name, re.search(r'"name":"([^"]+)"', ctx).group(1)) if re.search(
            r'"name":"([^"]+)"', ctx
        ) else False:
            out["homepage"] = unescape_json(m.group(1))
            break
    if "homepage" not in out:
        # fallback: blog near place id
        if out.get("place_id"):
            blogs = re.findall(r"https?://blog\.naver\.com/[a-zA-Z0-9_.\-]+", html)
            # too noisy — skip unless only one near PlaceDetailBase
            pass

    # phone: look for patterns near place name in JSON
    # virtualPhone / phone fields near PlaceDetailBase
    if out.get("place_id"):
        pid = out["place_id"]
        idx = html.find(f'"id":"{pid}"')
        if idx >= 0:
            window = html[idx : idx + 4000]
            for key in ("virtualPhone", "phone", "roadAddress", "address"):
                mm = re.search(rf'"{key}":(?:null|"([^"]*)")', window)
                if mm and mm.group(1):
                    out[key] = unescape_json(mm.group(1))

    # visible tel links near name
    if "phone" not in out or not out.get("phone"):
        # from kakao we usually get phone; naver often null for virtual
        pass

    # description / keywords
    if out.get("place_id"):
        idx = html.find(f'"id":"{out["place_id"]}"')
        if idx >= 0:
            window = html[idx : idx + 5000]
            dm = re.search(r'"description":"([^"]{0,400})"', window)
            if dm:
                out["description"] = unescape_json(dm.group(1))

    # closed
    if re.search(r"폐업", html) and name[:3] in html:
        # check place status texts
        if re.search(rf"{re.escape(name[:4])}[^{{]{{0,200}}폐업", html):
            out["closed_hint"] = True

    return out


def unescape_json(s: str) -> str:
    return (
        s.replace("\\u002F", "/")
        .replace("\\/", "/")
        .replace("\\n", "\n")
        .replace('\\"', '"')
    )


def extract_depts(*texts: str | None) -> list[str]:
    blob = " ".join(t for t in texts if t)
    found = []
    for key, patterns in DEPT_KEYS:
        if any(p.lower() in blob.lower() for p in patterns):
            found.append(key)
    return found


def score_kakao_place(p: dict[str, Any], t: dict[str, Any]) -> tuple[int, list[str]]:
    reasons = []
    score = 0
    pname = p.get("name") or ""
    addr = (p.get("new_address") or "") + " " + (p.get("address") or "")
    tel = p.get("tel") or ""
    cate = p.get("last_cate_name") or ""

    if name_similar(t["name"], pname):
        score += 50
        reasons.append("name")
    else:
        return 0, ["name_mismatch"]

    if addr_region_match(addr, t):
        score += 40
        reasons.append("addr")
    else:
        # cross-region hard fail if different metro clearly
        return 0, ["region_mismatch"]

    if t.get("phone") and phones_equal(t.get("phone"), tel):
        score += 25
        reasons.append("phone")
    elif tel:
        score += 5
        reasons.append("phone_place")

    if "동물" in cate or "병원" in cate or "반려동물" in cate:
        score += 10
        reasons.append(f"cat({cate})")

    return score, reasons


def pick_kakao(places: list[dict[str, Any]], t: dict[str, Any]) -> tuple[dict | None, str]:
    scored = []
    for p in places:
        sc, reasons = score_kakao_place(p, t)
        if sc >= 90:  # name+addr minimum
            scored.append((sc, reasons, p))
        elif sc >= 50 and "addr" in reasons:
            scored.append((sc, reasons, p))
    if not scored:
        return None, "no_match"
    scored.sort(key=lambda x: -x[0])
    # ambiguity: two strong matches different phones/addrs
    top = scored[0]
    if len(scored) > 1:
        a, b = scored[0][2], scored[1][2]
        if not phones_equal(a.get("tel"), b.get("tel")) and (
            (a.get("new_address") or a.get("address"))
            != (b.get("new_address") or b.get("address"))
        ):
            # if top clearly better by phone match keep it
            if "phone" in scored[0][1] and "phone" not in scored[1][1]:
                return top[2], "ok:" + "+".join(top[1])
            return None, "ambiguous"
    return top[2], "ok:" + "+".join(top[1])


def build_search_url(t: dict[str, Any]) -> str:
    if t.get("place_search_url"):
        return t["place_search_url"]
    q = f"{t['name']} {t.get('sido') or ''}".strip()
    return "https://search.naver.com/search.naver?" + urllib.parse.urlencode({"query": q})


def enrich_one(t: dict[str, Any]) -> dict[str, Any]:
    name = t["name"]
    queries = [
        f"{name} {t.get('sigungu') or ''}".strip(),
        f"{name} {t.get('sido') or ''}".strip(),
    ]
    # address road hint
    addr = t.get("address") or ""
    roads = re.findall(r"([가-힣0-9]+(?:로|길))\s*\d+", addr)
    if roads:
        queries.append(f"{name} {roads[0]}")
    if t.get("phone"):
        queries.append(t["phone"])

    # dedupe
    seen_q = set()
    qs = []
    for q in queries:
        if q and q not in seen_q:
            seen_q.add(q)
            qs.append(q)

    # Large animal from name alone
    if LARGE_ANIMAL_RE.search(name) and not re.search(r"반려동물|애완|고양이|강아지", name):
        # still verify via place; may be companion despite name
        pass

    all_places: list[dict[str, Any]] = []
    for q in qs:
        places = kakao_search(q)
        time.sleep(0.35)
        for p in places:
            pid = p.get("confirmid")
            if pid and any(x.get("confirmid") == pid for x in all_places):
                continue
            all_places.append(p)

    place, how = pick_kakao(all_places, t)

    # Naver panel for hours / closed / homepage
    nq = qs[0]
    html = naver_html(nq)
    time.sleep(0.45)
    panel = extract_naver_panel(html, name)

    # If kakao miss, try broader name-only but require region match
    if place is None and how != "ambiguous":
        places = kakao_search(name)
        time.sleep(0.35)
        place, how = pick_kakao(places, t)
        all_places.extend(places)

    notes_parts: list[str] = []
    status = "no_hit"
    phone = None
    homepage = None
    hours_raw = None
    hours_hint = None
    depts: list[str] = []

    # CLOSED check
    closed = False
    if place:
        # openoff_status sometimes
        blob = json.dumps(place, ensure_ascii=False) + (html[:20000] if html else "")
        if CLOSED_RE.search(blob) and name[:3] in blob:
            # check directories / notes saying 폐업 near this hospital
            if re.search(r"폐업", html or "") and (
                panel.get("closed_hint")
                or re.search(rf"{re.escape(name[:3])}[^.]{{0,80}}폐업", html or "")
            ):
                closed = True
    if panel.get("closed_hint") and place is None:
        # directory closed without place
        pass

    # LARGE_ANIMAL
    large = False
    check_text = name + " " + (panel.get("description") or "")
    if place:
        check_text += " " + (place.get("name") or "") + " " + (place.get("last_cate_name") or "")
    if LARGE_ANIMAL_RE.search(check_text):
        # exclude if clearly livestock-only (축협 etc) without companion markers
        if re.search(r"축협|가축병원|양돈|피그클리닉|수산질병", check_text):
            if not re.search(r"반려동물|개\s*고양이|소동물", check_text):
                large = True

    if how == "ambiguous":
        status = "ambiguous"
        notes_parts.append("동명이호 다수·주소/전화 불일치 → ambiguous")
        # still attach any shared phone if unique? no
    elif place is None:
        status = "no_hit"
        # cross-region only hits?
        foreign = [
            p
            for p in all_places
            if name_similar(name, p.get("name") or "")
            and not addr_region_match(
                (p.get("new_address") or "") + " " + (p.get("address") or ""), t
            )
        ]
        if foreign:
            notes_parts.append(
                f"타지역 동명만 노출({foreign[0].get('new_address') or foreign[0].get('address')}) → no_hit"
            )
        else:
            notes_parts.append("Place/Kakao 활성 매칭 없음 → no_hit")
    else:
        status = "hit"
        phone = (place.get("tel") or "").strip() or None
        addr = place.get("new_address") or place.get("address") or ""
        hp = is_allowed_homepage(place.get("homepage"))
        if not hp and panel.get("homepage"):
            hp = is_allowed_homepage(panel.get("homepage"))
        homepage = hp
        hours_raw = panel.get("hours_raw")
        hours_hint = panel.get("hours_hint")
        # 24h only literal from place
        if hours_raw and re.search(r"24시|00:00\s*[-~]\s*24:00|연중무휴\s*24", hours_raw):
            if not hours_hint:
                hours_hint = "24h_or_always"
        elif name and "24시" in name and not hours_raw:
            # mutual name literal only — note but don't invent full hours unless place says
            hours_hint = "hours_24h"
            hours_raw = "24시 표기(상호)"
        depts = extract_depts(
            name, panel.get("description"), place.get("name"), hours_raw
        )
        notes_parts.append(
            f"{t.get('sigungu')} Kakao/Place hit({how}); addr={addr}"
        )
        if phone and t.get("phone") and not phones_equal(phone, t.get("phone")):
            notes_parts.append(f"타깃전화({t.get('phone')})≠Place({phone})")
        if homepage:
            notes_parts.append(f"홈={homepage}")
        else:
            notes_parts.append("홈없음/제외")
        if hours_raw:
            notes_parts.append("영업시간 Place panel")
        else:
            notes_parts.append("영업시간미노출")

    if closed:
        status = "CLOSED_EXCLUDE"
        notes_parts.append("폐업 표기 → CLOSED_EXCLUDE")
        if place and place.get("tel"):
            phone = place.get("tel")
    if large:
        status = "LARGE_ANIMAL_ONLY_EXCLUDE"
        notes_parts.append("축협/가축/수산/양돈 → LARGE_ANIMAL_ONLY_EXCLUDE")
        if place and place.get("tel"):
            phone = place.get("tel")
        depts = extract_depts(check_text)

    # If hit but phone empty, try panel
    if status == "hit" and not phone:
        phone = panel.get("virtualPhone") or panel.get("phone") or None

    return {
        "id": t["id"],
        "name": name,
        "place_status": status,
        "place_homepage": homepage,
        "place_phone": phone,
        "place_hours_hint": hours_hint if status == "hit" else None,
        "place_hours_raw": hours_raw if status == "hit" else None,
        "place_dept_keywords": depts if status in ("hit", "LARGE_ANIMAL_ONLY_EXCLUDE") else [],
        "place_notes": "; ".join(notes_parts)[:300],
        "place_search_url": build_search_url(t),
    }


def load_done() -> dict[str, dict]:
    done = {}
    if OUT.exists():
        for line in OUT.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            done[row["id"]] = row
    return done


def write_all(rows: list[dict], order: list[str]) -> None:
    by_id = {r["id"]: r for r in rows}
    with OUT.open("w", encoding="utf-8") as f:
        for i in order:
            f.write(json.dumps(by_id[i], ensure_ascii=False) + "\n")


def main() -> None:
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--start", type=int, default=0)
    ap.add_argument("--limit", type=int, default=25)
    args = ap.parse_args()

    data = json.loads(TARGETS.read_text(encoding="utf-8"))
    targets = data["targets"]
    order = [t["id"] for t in targets]
    done = load_done()

    chunk = targets[args.start : args.start + args.limit]
    print(f"Processing {args.start}:{args.start+len(chunk)} ({len(chunk)} targets)")

    for i, t in enumerate(chunk):
        idx = args.start + i
        if t["id"] in done:
            print(f"[{idx:03d}] SKIP {t['id']} {t['name']}")
            continue
        print(f"[{idx:03d}] {t['id']} {t['name']} ({t.get('sigungu')})")
        try:
            row = enrich_one(t)
        except Exception as e:
            print(f"  FAIL {e}")
            row = {
                "id": t["id"],
                "name": t["name"],
                "place_status": "no_hit",
                "place_homepage": None,
                "place_phone": None,
                "place_hours_hint": None,
                "place_hours_raw": None,
                "place_dept_keywords": [],
                "place_notes": f"enrich error: {e}",
                "place_search_url": build_search_url(t),
            }
        done[t["id"]] = row
        print(
            f"  -> {row['place_status']} phone={row['place_phone']} "
            f"hours={'Y' if row['place_hours_raw'] else 'N'} hp={row['place_homepage']}"
        )
        # checkpoint write after each
        rows = [done[i] for i in order if i in done]
        write_all(rows, [i for i in order if i in done])

    # summary for this run
    statuses = {}
    for t in chunk:
        s = done[t["id"]]["place_status"]
        statuses[s] = statuses.get(s, 0) + 1
    print("chunk status counts:", statuses)
    print("total done:", len(done))


if __name__ == "__main__":
    main()
