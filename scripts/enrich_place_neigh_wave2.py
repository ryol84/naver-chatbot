#!/usr/bin/env python3
"""Enrich neighborhood hospital targets via Naver Place (mobile Apollo state)."""
from __future__ import annotations

import json
import re
import ssl
import time
import urllib.parse
import urllib.request
from pathlib import Path

UA = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1"
)
UA_PC = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
)
CTX = ssl.create_default_context()

REJECT_HOME_HOSTS = (
    "instagram.com",
    "facebook.com",
    "fb.com",
    "youtube.com",
    "youtu.be",
    "twitter.com",
    "x.com",
    "tiktok.com",
    "pf.kakao.com",
    "open.kakao.com",
    "smartstore.naver.com",
    "shopping.naver.com",
    "store.naver.com",
    "booking.naver.com",
    "map.naver.com",
    "place.naver.com",
    "bemypet.kr",
    "petgo.kr",
    "yakfact.kr",
    "animal.hospitalk.net",
    "ah.mamama.kr",
    "duli.co.kr",
    "pet.kimgoon.kr",
    "mypet-119.com",
    "hancome.kr",
    "114.co.kr",
    "sori114.com",
    "kr-vet.com",
    "linktr.ee",
    "litt.ly",
    "bit.ly",
    "naver.me",
    "band.us",
    "threads.net",
)


def fetch(url: str, ua: str = UA, timeout: int = 30) -> str:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": ua,
            "Accept-Language": "ko-KR,ko;q=0.9",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout, context=CTX) as r:
        return r.read().decode("utf-8", errors="replace")


def search_place_ids(query: str) -> tuple[list[str], str | None]:
    url = "https://search.naver.com/search.naver?query=" + urllib.parse.quote(query)
    try:
        html = fetch(url, ua=UA_PC)
    except Exception as e:  # noqa: BLE001
        return [], str(e)
    ids: list[str] = []
    for pat in (
        r"(?:map\.naver\.com/p/entry/place/|place\.naver\.com/(?:place|hospital)/|"
        r"m\.place\.naver\.com/place/)(\d{5,})",
        r"place%2F(\d{5,})",
        r'"placeId":"(\d{5,})"',
        r'"id":"(\d{5,})"[^}]{0,80}동물병원',
    ):
        for m in re.finditer(pat, html):
            if m.group(1) not in ids:
                ids.append(m.group(1))
    return ids, None


def parse_apollo(html: str) -> dict | None:
    start = html.find("window.__APOLLO_STATE__ = ")
    if start < 0:
        return None
    i = start + len("window.__APOLLO_STATE__ = ")
    try:
        obj, _ = json.JSONDecoder().raw_decode(html, i)
        return obj
    except Exception:  # noqa: BLE001
        return None


def resolve_ref(obj: dict, node, depth: int = 0):
    if depth > 6:
        return node
    if isinstance(node, dict):
        if set(node.keys()) == {"__ref"}:
            return resolve_ref(obj, obj.get(node["__ref"]), depth + 1)
        return {k: resolve_ref(obj, v, depth + 1) for k, v in node.items()}
    if isinstance(node, list):
        return [resolve_ref(obj, x, depth + 1) for x in node]
    return node


def get_place_detail(pid: str) -> tuple[dict | None, str | None, str]:
    url = f"https://m.place.naver.com/place/{pid}/home"
    html = fetch(url)
    state = parse_apollo(html)
    if not state:
        return None, "no apollo", html
    root = state.get("ROOT_QUERY", {})
    pd_key = next((k for k in root if k.startswith("placeDetail(")), None)
    base = state.get(f"PlaceDetailBase:{pid}") or {}
    if not pd_key:
        return (
            {
                "base": base,
                "newBusinessHours": None,
                "homepages": None,
                "description": "",
                "petMedicalService": None,
            },
            None,
            html,
        )
    pd = resolve_ref(state, root[pd_key])
    base2 = pd.get("base") or base
    if isinstance(base2, dict) and "__ref" in base2:
        base2 = state.get(base2["__ref"], base2)
    return (
        {
            "base": base2,
            "newBusinessHours": pd.get("newBusinessHours"),
            "homepages": pd.get("homepages"),
            "description": pd.get("description") or "",
            "petMedicalService": pd.get("petMedicalService"),
            "petNote": pd.get("petNote"),
        },
        None,
        html,
    )


def format_hours(nbh) -> tuple[str | None, str | None]:
    if not nbh:
        return None, None
    block = next((b for b in nbh if b.get("name") == "기본"), nbh[0])
    parts: list[str] = []
    sunday_closed = False
    has_lunch = False
    literal_24h = False
    for dayinfo in block.get("businessHours") or []:
        day = dayinfo.get("day")
        desc = dayinfo.get("description") or ""
        bh = dayinfo.get("businessHours")
        br = dayinfo.get("breakHours")
        if "휴무" in desc or "휴진" in desc:
            parts.append(f"{day} {desc}")
            if day == "일":
                sunday_closed = True
            continue
        if not bh:
            if desc:
                parts.append(f"{day} {desc}")
            elif day == "일":
                sunday_closed = True
                parts.append(f"{day} 정기휴무")
            continue
        start, end = bh.get("start"), bh.get("end")
        seg = f"{day} {start}-{end}"
        if br:
            has_lunch = True
            if isinstance(br, list):
                br0 = br[0] if br and isinstance(br[0], dict) else None
            elif isinstance(br, dict):
                br0 = br
            else:
                br0 = None
            if br0:
                seg += f" (휴게 {br0.get('start')}-{br0.get('end')})"
        if desc:
            seg += f" {desc}"
        parts.append(seg)
        if day == "일" and ("휴무" in desc or "휴진" in desc):
            sunday_closed = True
    full = json.dumps(block, ensure_ascii=False)
    # 24h only when Place literally says so
    if re.search(r"24\s*시간|24시\s*진료|24시\s*영업", full):
        literal_24h = True
    status_desc = (block.get("businessStatusDescription") or {}).get("description") or ""
    raw = " | ".join(parts) if parts else (f"Place: {status_desc}" if status_desc else None)
    hints: list[str] = []
    if sunday_closed:
        hints.append("sunday_closed")
    if has_lunch:
        hints.append("daytime_with_lunch")
    if literal_24h:
        hints.append("24h")
    return ("+".join(hints) if hints else None), raw


def pick_homepage(homepages, target_homepage=None) -> str | None:
    cands: list[str] = []
    if isinstance(homepages, dict):
        repr_u = homepages.get("repr")
        if isinstance(repr_u, dict):
            cands.append(repr_u.get("url") or repr_u.get("link") or "")
        elif isinstance(repr_u, str):
            cands.append(repr_u)
        for x in homepages.get("etc") or []:
            if isinstance(x, dict):
                cands.append(x.get("url") or x.get("link") or "")
            elif isinstance(x, str):
                cands.append(x)
        for x in homepages.get("subLinks") or []:
            if isinstance(x, dict):
                cands.append(x.get("url") or x.get("link") or "")
            elif isinstance(x, str):
                cands.append(x)
    if target_homepage:
        cands.append(target_homepage)
    for c in cands:
        if not c or not isinstance(c, str):
            continue
        url = c.strip()
        low = url.lower()
        if not low.startswith("http"):
            continue
        if any(h in low for h in REJECT_HOME_HOSTS):
            continue
        return url
    return None


def normalize_addr(a: str) -> str:
    if not a:
        return ""
    a = a.replace("경상남도", "경남").replace("부산광역시", "부산").replace("·", "")
    return re.sub(r"\s+", "", a)


def road_key(s: str) -> str:
    m = re.search(r"([가-힣A-Za-z0-9]+(?:로|길)\d*(?:번길)?)", normalize_addr(s))
    return m.group(1) if m else ""


def road_base(s: str) -> str:
    """Strip trailing house numbers / 번길 digits for soft compare."""
    rk = road_key(s)
    if not rk:
        return ""
    return re.sub(r"\d+(?:번길)?$", "", rk) or rk


def addr_overlap(target_addr: str, place_road: str, place_jibun: str):
    pr = normalize_addr(place_road)
    pj = normalize_addr(place_jibun)
    combined = pr + pj
    tk = road_key(target_addr)
    tb = road_base(target_addr)
    if tk and len(tk) >= 3 and (tk in pr or tk in pj):
        return True
    if tb and len(tb) >= 3 and tb in combined:
        # road name match without number (화전로, 재반로 vs 재반로84번길)
        sigungu_tokens = re.findall(r"[가-힣]+(?:시|군|구)", target_addr or "")
        if not sigungu_tokens or any(tok in (place_road or "") or tok in combined for tok in sigungu_tokens):
            return True
    sigungu_tokens = re.findall(r"[가-힣]+(?:시|군|구)", target_addr or "")
    dong_tokens = re.findall(r"[가-힣0-9]+(?:동|면|읍)", target_addr or "")
    has_sigungu = any(tok in combined or tok in (place_road or "") for tok in sigungu_tokens)
    has_dong = any(tok in combined for tok in dong_tokens)
    if has_sigungu and has_dong:
        if tb and tb in combined:
            return True
        return "soft"
    if has_sigungu and tb and tb in combined:
        return "soft"
    return False


def norm_name(n: str) -> str:
    return re.sub(r"[^0-9A-Za-z가-힣]", "", n or "").lower()


def names_match(a: str, b: str) -> bool:
    na, nb = norm_name(a), norm_name(b)
    if not na or not nb:
        return False
    if na == nb or na in nb or nb in na:
        return True
    # BS조은 vs 조은, O.K vs OK
    if na.replace("bs", "") == nb.replace("bs", "") and len(na) > 4:
        return True
    return False


def is_large_animal(name: str, category: str, description: str, extra: str = "") -> bool:
    text = " ".join([name or "", category or "", description or "", extra or ""])
    needles = ("축협", "가축병원", "가축약품", "수산동물", "수산병원", "대동물전용", "한우병원")
    return any(x in text for x in needles)


def place_page_closed(html: str, pname: str) -> bool:
    if "폐업" in (pname or ""):
        return True
    # Place UI sometimes marks closed near status
    if re.search(r'"(?:status|businessStatus)"\s*:\s*"[^"]*폐업', html):
        return True
    if re.search(r"이\s*장소는\s*폐업|폐업한\s*가게|폐업\s*신고", html):
        return True
    return False


def dept_keywords(detail: dict | None, name: str) -> list[str]:
    text = json.dumps(detail, ensure_ascii=False) if detail else ""
    text += " " + (name or "")
    mapping = [
        ("내과", "내과"),
        ("외과", "외과"),
        ("치과", "치과"),
        ("안과", "안과"),
        ("피부", "피부"),
        ("영상", "영상"),
        ("CT", "영상"),
        ("MRI", "영상"),
        ("응급", "응급"),
        ("고양이", "고양이"),
        ("특수동물", "특수동물"),
        ("파충류", "특수동물"),
        ("예방접종", "예방접종"),
        ("중성화", "중성화"),
        ("심장", "심장"),
        ("재활", "재활"),
        ("한방", "한방"),
    ]
    out: list[str] = []
    seen: set[str] = set()
    for needle, kw in mapping:
        if needle in text and kw not in seen:
            out.append(kw)
            seen.add(kw)
    return out


def enrich_one(t: dict) -> dict:
    name = t["name"]
    sigungu = t.get("sigungu") or ""
    sido = t.get("sido") or ""
    address = t.get("address") or ""
    search_url = t.get("place_search_url") or (
        "https://search.naver.com/search.naver?query=" + urllib.parse.quote(f"{name} {sigungu}")
    )

    road = ""
    m = re.search(r"([가-힣A-Za-z0-9]+(?:로|길)(?:\d+번길)?)", address)
    if m:
        road = m.group(1)
    dong = ""
    md = re.search(r"\(([가-힣0-9]+(?:동|면|읍))\)", address)
    if md:
        dong = md.group(1)
    else:
        md = re.search(r"([가-힣0-9]+(?:동|면|읍))", address)
        if md:
            dong = md.group(1)

    queries: list[str] = []
    # Alternate display names seen on Place / public dirs
    alt_names = [name]
    if name == "오션시티동물병원":
        alt_names.append("명지오션시티동물병원")
    if name == "OK동물병원":
        alt_names.extend(["O.K 동물병원", "O.K동물병원"])
    if name.startswith("BS"):
        alt_names.append(name.replace("BS", "").strip())
    for nm in alt_names:
        for q in (
            f"{nm} {sigungu} {dong}".strip(),
            f"{nm} {sigungu}".strip(),
            f"{nm} {road}".strip() if road else "",
            f"{nm} {sido} {sigungu}".strip(),
            f"{nm} {address[:50]}".strip(),
        ):
            if q and q not in queries:
                queries.append(q)
    if t.get("phone"):
        queries.append(f"{name} {t['phone']}")
        queries.append(t["phone"])

    candidates: list[tuple[str, str]] = []
    last_err = None
    for q in queries[:8]:
        ids, err = search_place_ids(q)
        last_err = err
        time.sleep(0.35)
        for pid in ids[:6]:
            if pid not in [c[0] for c in candidates]:
                candidates.append((pid, q))
        if len(candidates) >= 3:
            break

    if not candidates:
        # Directory-level 폐업 signal when Place panel missing
        closed_dir = False
        try:
            q = f"{name} {sigungu} {dong or road}".strip()
            html = fetch(
                "https://search.naver.com/search.naver?query=" + urllib.parse.quote(q),
                ua=UA_PC,
            )
            time.sleep(0.3)
            if re.search(rf"{re.escape(name)}\(폐업\)|{re.escape(name)}.{{0,12}}폐업|폐업.{{0,40}}{re.escape(name)}", html):
                if (dong and dong in html) or (road and road[:4] in html) or (sigungu and sigungu in html):
                    closed_dir = True
        except Exception:  # noqa: BLE001
            pass
        if closed_dir:
            return {
                "id": t["id"],
                "name": name,
                "place_status": "CLOSED_EXCLUDE",
                "place_homepage": None,
                "place_phone": t.get("phone"),
                "place_hours_hint": None,
                "place_hours_raw": None,
                "place_dept_keywords": [],
                "place_notes": f"{sigungu} Place 미노출·디렉터리 폐업({address})",
                "place_search_url": search_url,
            }
        return {
            "id": t["id"],
            "name": name,
            "place_status": "no_hit",
            "place_homepage": None,
            "place_phone": None,
            "place_hours_hint": None,
            "place_hours_raw": None,
            "place_dept_keywords": [],
            "place_notes": f"{sigungu} Place 미노출"
            + (f"; search_err={last_err}" if last_err else ""),
            "place_search_url": search_url,
        }

    hits = []
    fetch_notes: list[str] = []
    for pid, q in candidates[:6]:
        try:
            detail, derr, html = get_place_detail(pid)
            time.sleep(0.45)
        except Exception as e:  # noqa: BLE001
            fetch_notes.append(f"{pid}:{e}")
            continue
        if not detail:
            fetch_notes.append(f"{pid}:{derr}")
            continue
        base = detail["base"] or {}
        pname = base.get("name") or ""
        road_a = base.get("roadAddress") or ""
        jibun = base.get("address") or ""
        phone = base.get("phone") or base.get("virtualPhone")
        cat = base.get("category") or ""
        ov = addr_overlap(address, road_a, jibun)
        name_match = names_match(name, pname)
        phone_match = False
        if t.get("phone") and phone:
            phone_match = re.sub(r"\D", "", t["phone"])[-8:] == re.sub(r"\D", "", phone)[-8:]
        score = 0
        if name_match:
            score += 3
        if ov is True:
            score += 4
        elif ov == "soft":
            score += 2
        if phone_match:
            score += 3
        if "동물" in cat:
            score += 1
        # region collision guard
        region_conflict = False
        place_region = (road_a or "") + " " + (jibun or "")
        target_sido = sido or ""
        if any(x in target_sido for x in ("경남", "경상남")):
            if not any(x in place_region for x in ("경남", "경상남", "창원", "김해", "진주", "양산", "거제", "통영", "사천", "밀양", "거창", "함안", "함양", "고성", "남해", "하동", "산청", "의령", "창녕", "합천")):
                region_conflict = True
                score -= 6
            if any(x in place_region for x in ("부산", "울산", "충북", "충남", "경기", "서울", "대구", "광주", "전북", "전남", "강원", "제주", "인천", "대전")) and not any(
                x in place_region for x in ("경남", "경상남")
            ):
                region_conflict = True
                score -= 6
        if "부산" in target_sido:
            if "부산" not in place_region:
                region_conflict = True
                score -= 6
            if any(x in place_region for x in ("경남", "경상남", "울산")) and "부산" not in place_region:
                region_conflict = True
                score -= 6
        # sigungu must agree when both present
        if sigungu and sigungu not in place_region and score >= 3:
            # soften only if phone+name strong and road matches; else penalize
            if not (phone_match and ov is True):
                score -= 2
                if not phone_match:
                    region_conflict = True
                    score -= 3
        hits.append(
            {
                "pid": pid,
                "q": q,
                "detail": detail,
                "html": html,
                "score": score,
                "ov": ov,
                "name_match": name_match,
                "phone_match": phone_match,
                "pname": pname,
                "road_a": road_a,
                "phone": phone,
                "cat": cat,
                "region_conflict": region_conflict,
            }
        )

    if not hits:
        return {
            "id": t["id"],
            "name": name,
            "place_status": "no_hit",
            "place_homepage": None,
            "place_phone": None,
            "place_hours_hint": None,
            "place_hours_raw": None,
            "place_dept_keywords": [],
            "place_notes": f"{sigungu} Place 상세 미파싱; {';'.join(fetch_notes[:3])}",
            "place_search_url": search_url,
        }

    hits.sort(key=lambda x: -x["score"])
    best = hits[0]
    desc = (best["detail"].get("description") or "") + " " + best["pname"]

    if is_large_animal(name, best["cat"], desc, best["road_a"]):
        return {
            "id": t["id"],
            "name": name,
            "place_status": "LARGE_ANIMAL_ONLY_EXCLUDE",
            "place_homepage": None,
            "place_phone": best["phone"],
            "place_hours_hint": None,
            "place_hours_raw": None,
            "place_dept_keywords": [],
            "place_notes": f"{sigungu} 대동물/축산·수산; Place={best['pname']} {best['road_a']}",
            "place_search_url": search_url,
        }

    if place_page_closed(best["html"], best["pname"]):
        return {
            "id": t["id"],
            "name": name,
            "place_status": "CLOSED_EXCLUDE",
            "place_homepage": None,
            "place_phone": best["phone"],
            "place_hours_hint": None,
            "place_hours_raw": None,
            "place_dept_keywords": [],
            "place_notes": f"{sigungu} Place 폐업; {best['pname']} {best['road_a']}",
            "place_search_url": search_url,
        }

    # ambiguous: multiple strong different-location candidates
    strong = [h for h in hits if h["score"] >= 5 and not h["region_conflict"]]
    if len(strong) >= 2:
        a, b = strong[0], strong[1]
        if a["road_a"] != b["road_a"] and abs(a["score"] - b["score"]) <= 2:
            if not (a["phone_match"] or a["ov"] is True):
                alts = "; ".join(f"{h['pname']}/{h['road_a']}" for h in strong[:3])
                return {
                    "id": t["id"],
                    "name": name,
                    "place_status": "ambiguous",
                    "place_homepage": None,
                    "place_phone": None,
                    "place_hours_hint": None,
                    "place_hours_raw": None,
                    "place_dept_keywords": [],
                    "place_notes": f"{sigungu} 동명·주소 혼재: {alts}",
                    "place_search_url": search_url,
                }

    if best["score"] < 3 or best["region_conflict"]:
        # try next non-conflict
        alt = next((h for h in hits if not h["region_conflict"] and h["score"] >= 3), None)
        if alt:
            best = alt
        else:
            # Directory 폐업 fallback
            try:
                q = f"{name} {sigungu} {dong or road}".strip()
                html = fetch(
                    "https://search.naver.com/search.naver?query=" + urllib.parse.quote(q),
                    ua=UA_PC,
                )
                time.sleep(0.3)
                if re.search(
                    rf"{re.escape(name)}\(폐업\)|{re.escape(name)}.{{0,12}}폐업",
                    html,
                ) and (
                    (dong and dong in html)
                    or (road and road[:4] in html)
                    or (sigungu and sigungu in html)
                ):
                    return {
                        "id": t["id"],
                        "name": name,
                        "place_status": "CLOSED_EXCLUDE",
                        "place_homepage": None,
                        "place_phone": t.get("phone"),
                        "place_hours_hint": None,
                        "place_hours_raw": None,
                        "place_dept_keywords": [],
                        "place_notes": f"{sigungu} Place 부재·디렉터리 폐업({address})",
                        "place_search_url": search_url,
                    }
            except Exception:  # noqa: BLE001
                pass
            return {
                "id": t["id"],
                "name": name,
                "place_status": "no_hit" if best["score"] < 2 else "ambiguous",
                "place_homepage": None,
                "place_phone": None,
                "place_hours_hint": None,
                "place_hours_raw": None,
                "place_dept_keywords": [],
                "place_notes": (
                    f"{sigungu} 매칭 약함/지역충돌; 상위 {best['pname']}({best['road_a']}) "
                    f"score={best['score']}"
                ),
                "place_search_url": search_url,
            }

    hint, raw = format_hours(best["detail"].get("newBusinessHours"))
    hp = pick_homepage(best["detail"].get("homepages"), t.get("homepage"))

    note_bits = [f"{sigungu} Place hit"]
    if best["phone_match"]:
        note_bits.append("전화일치")
    if best["ov"] is True:
        note_bits.append("주소일치")
    elif best["ov"] == "soft":
        note_bits.append("지역일치")
    note_bits.append(best["road_a"] or (best["detail"]["base"] or {}).get("address") or "")
    # flag target vs Place address drift (same phone)
    if best["phone_match"] and best["ov"] is False and best["road_a"]:
        note_bits.append(f"타깃주소와 Place주소 상이(타깃:{address})")
    if hp:
        note_bits.append(f"홈={hp}")
    else:
        if t.get("homepage") and pick_homepage(None, t.get("homepage")) is None:
            note_bits.append("공식홈거부(SNS/수집)")
        else:
            note_bits.append("홈없음")
    if not raw:
        note_bits.append("영업시간 미확인")

    depts = dept_keywords(best["detail"], name)
    return {
        "id": t["id"],
        "name": name,
        "place_status": "hit",
        "place_homepage": hp,
        "place_phone": best["phone"] or t.get("phone"),
        "place_hours_hint": hint,
        "place_hours_raw": raw,
        "place_dept_keywords": depts,
        "place_notes": "; ".join([b for b in note_bits if b]),
        "place_search_url": search_url,
    }


def run_file(targets_path: Path, out_path: Path) -> dict:
    data = json.loads(targets_path.read_text(encoding="utf-8"))
    targets = data["targets"]
    rows = []
    for i, t in enumerate(targets, 1):
        print(f"[{i}/{len(targets)}] {t['name']} ({t.get('sigungu')})", flush=True)
        try:
            row = enrich_one(t)
        except Exception as e:  # noqa: BLE001
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
                "place_search_url": t.get("place_search_url"),
            }
        rows.append(row)
        print(f"  -> {row['place_status']} phone={row.get('place_phone')} hours={bool(row.get('place_hours_raw'))}", flush=True)
        # incremental write
        out_path.write_text(
            "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n",
            encoding="utf-8",
        )
    from collections import Counter

    c = Counter(r["place_status"] for r in rows)
    return {"n": len(rows), "status": dict(c), "hours": sum(1 for r in rows if r.get("place_hours_raw")), "homepage": sum(1 for r in rows if r.get("place_homepage"))}


def main():
    root = Path("data/hospitals")
    jobs = [
        (root / "place-neigh-busan-wave2-targets.json", root / "place-neigh-busan-wave2.jsonl"),
        (root / "place-neigh-gyeongnam-wave2-targets.json", root / "place-neigh-gyeongnam-wave2.jsonl"),
    ]
    summary = {}
    for src, dst in jobs:
        print(f"\n=== {src.name} -> {dst.name} ===", flush=True)
        summary[dst.name] = run_file(src, dst)
    print("\nSUMMARY", json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
