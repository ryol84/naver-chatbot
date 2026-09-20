#!/usr/bin/env python3
"""Enrich Gyeongbuk wave2 neighborhood hospitals via Naver Place (mobile map/place)."""

from __future__ import annotations

import json
import re
import ssl
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

UA = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1"
)
CTX = ssl.create_default_context()

ROOT = Path(__file__).resolve().parents[1]
TARGETS = ROOT / "data/hospitals/place-neigh-gyeongbuk-wave2-targets.json"
OUT = ROOT / "data/hospitals/place-neigh-gyeongbuk-wave2.jsonl"

SNS_OR_AGG = (
    "instagram.com",
    "facebook.com",
    "pf.kakao.com",
    "youtube.com",
    "twitter.com",
    "x.com",
    "linktr.ee",
    "bit.ly",
    "smartstore.naver.com",
    "booking.naver.com",
    "map.naver.com",
    "place.map.kakao.com",
    "m.place.naver.com",
    "pcmap.place.naver.com",
    "animal.hospitalk.net",
    "bemypet.kr",
    "fah.purpleo",
    "onkorea.co.kr",
    "mypet-119",
    "sungyesa.com",
    "daangn.com",
    "fitpetmall.com",
)

LARGE_ANIMAL_NAME = ("축협", "가축", "수산")


def is_large_animal_label(text: str) -> bool:
    if not text:
        return False
    if any(k in text for k in LARGE_ANIMAL_NAME):
        return True
    # "한우" but not companion brand "한우리"
    if "한우" in text and "한우리" not in text:
        return True
    return False


def fetch(url: str, retries: int = 3) -> str:
    last: Exception | None = None
    for i in range(retries):
        try:
            req = urllib.request.Request(
                url,
                headers={"User-Agent": UA, "Accept-Language": "ko-KR,ko;q=0.9"},
            )
            with urllib.request.urlopen(req, context=CTX, timeout=35) as r:
                return r.read().decode("utf-8", "replace")
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(1.2 * (i + 1))
    assert last is not None
    raise last


def search_places(query: str) -> list[dict[str, Any]]:
    q = urllib.parse.quote(query)
    url = f"https://m.map.naver.com/search2/search.naver?query={q}&sm=hty&style=v5"
    html = fetch(url)
    items: list[dict[str, Any]] = []
    for m in re.finditer(
        r"window\.__RQ_STREAMING_STATE__\.push\((\{.*?\})\)\s*;?\s*</script>",
        html,
        re.S,
    ):
        try:
            blob = json.loads(m.group(1))
        except json.JSONDecodeError:
            continue
        for qobj in blob.get("queries", []):
            data = qobj.get("state", {}).get("data")
            if isinstance(data, dict) and isinstance(data.get("items"), list):
                items.extend(data["items"])
    if not items:
        m = re.search(r'"items":(\[\{.*?\}\])(?=,"|})', html)
        if m:
            try:
                items = json.loads(m.group(1))
            except json.JSONDecodeError:
                pass
    # dedupe
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for it in items:
        pid = str(it.get("id", ""))
        if not pid or pid in seen:
            continue
        seen.add(pid)
        out.append(it)
    return out


def _resolve_ref(state: dict, obj: Any) -> Any:
    if isinstance(obj, dict) and "__ref" in obj:
        return state.get(obj["__ref"], {})
    return obj


def place_detail(pid: str | int) -> dict[str, Any]:
    html = fetch(f"https://m.place.naver.com/place/{pid}/home")
    out: dict[str, Any] = {
        "id": str(pid),
        "name": None,
        "phone": None,
        "roadAddress": None,
        "address": None,
        "category": None,
        "homepage": None,
        "bizhourInfo": None,
        "hours_bits": [],
        "closed": False,
        "source": "place",
    }

    # Prefer regex extraction from Apollo blob (more robust than full JSON parse)
    # Find PlaceDetailBase-like block near this id
    closed_markers = (
        r'"statusText":"[^"]*폐업',
        r'"businessStatus":"[^"]*폐업',
        r"이 장소는 폐업",
        r'"isClosed":true',
        r"폐업한 업체",
    )
    if any(re.search(p, html) for p in closed_markers):
        out["closed"] = True

    # name + category near place id
    m = re.search(
        rf'"id":"{pid}".{{0,400}}?"name":"([^"]+)".{{0,200}}?"category":"([^"]*)"',
        html,
    )
    if not m:
        m = re.search(
            rf'"name":"([^"]+)".{{0,120}}?"category":"([^"]*)".{{0,400}}?"id":"{pid}"',
            html,
        )
    if m:
        out["name"], out["category"] = m.group(1), m.group(2)

    road = re.search(r'"roadAddress":"([^"]*)"', html)
    addr = re.search(r'"address":"([^"]*)"', html)
    if road:
        out["roadAddress"] = road.group(1)
    if addr:
        out["address"] = addr.group(1)

    phone = re.search(r'"phone":"([0-9\-]+)"', html)
    vphone = re.search(r'"virtualPhone":"([0-9\-]+)"', html)
    if phone:
        out["phone"] = phone.group(1)
    elif vphone:
        out["phone"] = vphone.group(1)

    # homepage: prefer hospital-owned; reject SNS/aggregators later
    hm = re.search(r'"homepages":\{[^}]*?"repr":(?:"([^"]+)"|null)', html)
    if hm and hm.group(1):
        out["homepage"] = hm.group(1)
    else:
        # blog.naver.com sometimes in naverBlog / etc / raw html
        blog = re.search(r'(https?://blog\.naver\.com/[A-Za-z0-9_\-]+)', html)
        if blog:
            out["homepage"] = blog.group(1)
        else:
            etc = re.search(
                r'"homepages":\{[^}]*?"etc":\[(.*?)\]',
                html,
            )
            if etc:
                urls = re.findall(r'https?://[^"\\]+', etc.group(1))
                if urls:
                    out["homepage"] = urls[0]

    biz = re.search(r'"bizhourInfo":"([^"]*)"', html)
    if biz and biz.group(1):
        out["bizhourInfo"] = biz.group(1).replace("\\n", "; ")

    # newBusinessHours descriptions (literal only)
    hours_bits: list[str] = []
    for desc in re.findall(
        r'"__typename":"BusinessHour".{0,300}?"description":"([^"]*)"',
        html,
    ):
        d = desc.strip()
        if d and d not in hours_bits:
            hours_bits.append(d)
    # also day+status patterns
    for day, status in re.findall(
        r'"day":"([^"]+)".{0,80}?"status":"([^"]*)"',
        html,
    ):
        bit = f"{day} {status}".strip()
        if bit and bit not in hours_bits and any(
            x in bit for x in ("휴무", "영업", "시", ":", "정보")
        ):
            hours_bits.append(bit)
    out["hours_bits"] = hours_bits[:12]
    return out


def norm_phone(p: str | None) -> str:
    if not p:
        return ""
    return re.sub(r"[^0-9]", "", p)


def addr_overlap(target_addr: str, cand: str | None) -> bool:
    if not cand:
        return False
    c = cand.replace(" ", "")
    # Prefer road-name evidence
    roads = re.findall(r"[가-힣0-9\-]+(?:로|길)", target_addr)
    road_hits = [r for r in roads if len(r) >= 3 and r.replace(" ", "") in c]
    if road_hits:
        nums = re.findall(r"\d+(?:-\d+)?", target_addr)
        num_hit = any(n in c for n in nums)
        region = re.findall(r"[가-힣]+(?:시|군|구|읍|면)", target_addr)
        region_hit = any(r in c for r in region if len(r) >= 2)
        return num_hit or region_hit
    # No road token: require 읍/면/동/리 + street number (not city alone)
    dongs = re.findall(r"[가-힣]+(?:읍|면|동|리)", target_addr)
    nums = re.findall(r"\d+(?:-\d+)?", target_addr)
    dong_hits = [d for d in dongs if d in c]
    num_hits = [n for n in nums if n in c]
    return len(dong_hits) >= 1 and len(num_hits) >= 1


def sigungu_in(text: str | None, sigungu: str) -> bool:
    if not text:
        return False
    sg = sigungu.replace("경상북도 ", "").replace("경북 ", "")
    return sg in text


def reject_homepage(url: str | None) -> str | None:
    if not url:
        return None
    u = url.strip()
    low = u.lower()
    if any(x in low for x in SNS_OR_AGG):
        # hospital blog.naver.com is OK
        if "blog.naver.com" in low:
            return u
        return None
    return u


def hours_hint_from(raw: str | None, bits: list[str]) -> str | None:
    text = " ".join([raw or ""] + bits)
    if not text.strip():
        return None
    if "24시" in text or "24시간" in text:
        # only literal
        if re.search(r"24\s*시|24시간", text):
            return "24h"
    if "일요일 휴무" in text or "매주 일요일 휴무" in text or "일 휴무" in text:
        return "sunday_closed"
    if "연중무휴" in text:
        return "no_holiday"
    return None


def format_hours_raw(biz: str | None, bits: list[str]) -> str | None:
    parts: list[str] = []
    if biz:
        parts.append(biz)
    for b in bits:
        if b and b not in parts:
            parts.append(b)
    if not parts:
        return None
    return "Place: " + "; ".join(parts[:8])


def names_compatible(target_name: str, place_name: str) -> bool:
    """Require same core hospital name (avoid picking nearby differently-named clinics)."""
    a = target_name.replace(" ", "")
    b = (place_name or "").replace(" ", "")
    if not b:
        return False
    if a == b:
        return True
    # one contains the other only if both still look like the same hospital label
    if a in b or b in a:
        shorter, longer = (a, b) if len(a) <= len(b) else (b, a)
        if len(shorter) >= 5:
            return True
    suffixes = (
        "동물메디컬센터",
        "동물의료센터",
        "동물병원",
        "수의과병원",
        "씨앤씨",
        "C&C",
        "병원",
        "센터",
    )

    def core(n: str) -> str:
        for s in suffixes:
            if n.endswith(s) and len(n) > len(s) + 1:
                return n[: -len(s)]
        return n

    ca, cb = core(a), core(b)
    if not ca or not cb:
        return False
    # Reject short geo cores (경주/경산/구미) equating different hospitals
    if ca == cb and len(ca) >= 3:
        return True
    return False


def classify_match(target: dict, items: list[dict], details: dict[str, dict]) -> dict:
    name = target["name"]
    addr = target["address"]
    phone = target.get("phone")
    sigungu = target.get("sigungu") or ""
    tphone = norm_phone(phone)

    # LARGE_ANIMAL by name
    if is_large_animal_label(name):
        return {
            "place_status": "LARGE_ANIMAL_ONLY_EXCLUDE",
            "place_homepage": None,
            "place_phone": phone,
            "place_hours_hint": None,
            "place_hours_raw": None,
            "place_dept_keywords": [],
            "place_notes": f"명칭에 축협/가축/한우/수산 계열 → LARGE_ANIMAL_ONLY_EXCLUDE; 타깃주소 {addr}",
            "match": None,
        }

    scored: list[tuple[int, dict, dict]] = []
    for it in items:
        det = details.get(str(it["id"]), {})
        score = 0
        it_name = it.get("name") or det.get("name") or ""
        it_road = it.get("roadAddress") or det.get("roadAddress") or ""
        it_addr = it.get("address") or det.get("address") or ""
        it_tel = it.get("tel") or it.get("virtualTel") or det.get("phone") or ""
        it_cat = it.get("category") or det.get("category") or ""

        name_ok = names_compatible(name, it_name)
        if not name_ok:
            # still record very low score for debug; never auto-hit without name
            score -= 10
        else:
            score += 8
        if addr_overlap(addr, it_road) or addr_overlap(addr, it_addr):
            score += 5
        if sigungu_in(it_road, sigungu) or sigungu_in(it_addr, sigungu):
            score += 2
        if tphone and norm_phone(it_tel) == tphone:
            score += 6
        if "동물" in it_cat or "수의" in it_cat or "병원" in it_cat:
            score += 1
        blob = f"{it_name} {it_cat}"
        if is_large_animal_label(blob):
            score -= 4
        scored.append((score, it, det))

    scored.sort(key=lambda x: -x[0])
    # Only name-compatible candidates can be hits
    named = [s for s in scored if names_compatible(name, s[1].get("name") or (s[2].get("name") or ""))]
    strong = [s for s in named if s[0] >= 10]
    mid = [s for s in named if s[0] >= 8]

    if not named or (named and named[0][0] < 8):
        notes = f"타깃 {sigungu} {addr}; "
        if items:
            top = items[0]
            notes += (
                f"Place에 동명 미노출(검색상위 {top.get('name')} {top.get('roadAddress') or top.get('address')}) "
                f"→ no_hit"
            )
        else:
            notes += "Place 검색 결과 없음 → no_hit"
        return {
            "place_status": "no_hit",
            "place_homepage": None,
            "place_phone": None,
            "place_hours_hint": None,
            "place_hours_raw": None,
            "place_dept_keywords": [],
            "place_notes": notes,
            "match": None,
        }

    # ambiguous: multiple strong matches in different locations
    if len(strong) >= 2:
        locs = []
        for sc, it, det in strong[:3]:
            locs.append(it.get("roadAddress") or it.get("address") or "?")
        unique_sig = set()
        for sc, it, det in strong:
            text = (it.get("roadAddress") or "") + (it.get("address") or "")
            for sg in (
                "상주",
                "경주",
                "경산",
                "포항",
                "구미",
                "영천",
                "영주",
                "청도",
                "칠곡",
                "문경",
                "의성",
                "고령",
                "예천",
                "대구",
                "창원",
                "부산",
            ):
                if sg in text:
                    unique_sig.add(sg)
        if len(unique_sig) >= 2 and not (
            tphone and any(norm_phone(s[1].get("tel") or "") == tphone for s in strong)
        ):
            return {
                "place_status": "ambiguous",
                "place_homepage": None,
                "place_phone": None,
                "place_hours_hint": None,
                "place_hours_raw": None,
                "place_dept_keywords": [],
                "place_notes": f"동명 다수 강매칭({', '.join(locs)}) → ambiguous",
                "match": None,
            }

    sc, it, det = (strong or mid or named)[0]
    it_name = it.get("name") or det.get("name") or name
    it_road = it.get("roadAddress") or det.get("roadAddress") or ""
    it_addr = it.get("address") or det.get("address") or ""
    it_tel = it.get("tel") or it.get("virtualTel") or det.get("phone")
    it_cat = it.get("category") or det.get("category") or ""

    phone_ok = bool(tphone and it_tel and norm_phone(it_tel) == tphone)
    addr_ok = addr_overlap(addr, it_road) or addr_overlap(addr, it_addr)

    # Name-only match in same city but different street → no_hit (possible relocate/other branch)
    if not phone_ok and not addr_ok:
        return {
            "place_status": "no_hit",
            "place_homepage": None,
            "place_phone": None,
            "place_hours_hint": None,
            "place_hours_raw": None,
            "place_dept_keywords": [],
            "place_notes": (
                f"타깃 {sigungu} {addr}; 동명 Place는 {it_road or it_addr or '(주소미표시)'} "
                f"(전화·주소 불일치) → no_hit"
            ),
            "match": it,
        }

    # large animal only
    if is_large_animal_label(it_name) or is_large_animal_label(it_cat):
        return {
            "place_status": "LARGE_ANIMAL_ONLY_EXCLUDE",
            "place_homepage": None,
            "place_phone": it_tel,
            "place_hours_hint": None,
            "place_hours_raw": None,
            "place_dept_keywords": [],
            "place_notes": f"Place '{it_name}'/{it_cat} 대동물·축협 계열({it_road}) → LARGE_ANIMAL_ONLY_EXCLUDE",
            "match": it,
        }

    if det.get("closed"):
        return {
            "place_status": "CLOSED_EXCLUDE",
            "place_homepage": None,
            "place_phone": it_tel,
            "place_hours_hint": None,
            "place_hours_raw": None,
            "place_dept_keywords": [],
            "place_notes": f"{it_road or it_addr} Place 폐업 표기 → CLOSED_EXCLUDE",
            "match": it,
        }

    # region collision: matched but wrong sido-ish (대구/경남)
    loc = it_road + " " + it_addr
    if any(x in loc for x in ("대구", "경상남도", "경남 ", "울산", "부산")) and "경상북" not in loc and "경북" not in loc:
        return {
            "place_status": "no_hit",
            "place_homepage": None,
            "place_phone": None,
            "place_hours_hint": None,
            "place_hours_raw": None,
            "place_dept_keywords": [],
            "place_notes": f"타깃 경북 {sigungu}이나 Place는 타지역({it_road}) → no_hit",
            "match": it,
        }

    hp = reject_homepage(det.get("homepage"))
    hours_raw = format_hours_raw(det.get("bizhourInfo"), det.get("hours_bits") or [])
    hint = hours_hint_from(det.get("bizhourInfo"), det.get("hours_bits") or [])

    phone_note = ""
    if tphone and it_tel and norm_phone(it_tel) != tphone:
        phone_note = f"; Place전화{it_tel}(타깃{phone})"
    elif tphone and it_tel and norm_phone(it_tel) == tphone:
        phone_note = "(전화일치)"
    elif addr_overlap(addr, it_road) or addr_overlap(addr, it_addr):
        phone_note = "(주소일치)"

    home_note = "; 홈없음" if not hp else f"; 홈={hp}"
    hours_note = ""
    if hint == "sunday_closed":
        hours_note = "; 일휴무"
    elif hours_raw is None:
        hours_note = "; 영업시간 미표시"

    notes = f"{it_road or it_addr} Place panel hit{phone_note}{home_note}{hours_note}"

    return {
        "place_status": "hit",
        "place_homepage": hp,
        "place_phone": it_tel or phone,
        "place_hours_hint": hint,
        "place_hours_raw": hours_raw,
        "place_dept_keywords": [],
        "place_notes": notes,
        "match": it,
    }


def build_query(t: dict) -> str:
    # Prefer name + sigungu + distinctive address token
    addr = t["address"]
    tokens = re.findall(r"[가-힣0-9\-]+(?:로|길)\d*[가-힣0-9\-]*|[가-힣]+(?:읍|면|동)", addr)
    extra = " ".join(tokens[:2])
    return f"{t['name']} {t['sigungu']} {extra}".strip()


def enrich_one(t: dict) -> dict:
    query = build_query(t)
    items = search_places(query)
    # if empty, try name+sigungu only
    if not items:
        time.sleep(0.3)
        items = search_places(f"{t['name']} {t['sigungu']}")
    # if still empty / weak, try name+phone
    if (not items or len(items) > 8) and t.get("phone"):
        time.sleep(0.3)
        items2 = search_places(f"{t['name']} {t['phone']}")
        if items2:
            items = items2

    details: dict[str, dict] = {}
    # Prefer name-compatible candidates for detail fetch
    named_items = [
        it for it in items if names_compatible(t["name"], it.get("name") or "")
    ]
    fetch_list = (named_items or items)[:3]
    for it in fetch_list:
        try:
            details[str(it["id"])] = place_detail(it["id"])
            time.sleep(0.35)
        except Exception as e:  # noqa: BLE001
            details[str(it["id"])] = {"id": str(it["id"]), "error": str(e)}

    result = classify_match(t, items, details)
    search_url = t.get("place_search_url") or (
        "https://search.naver.com/search.naver?query="
        + urllib.parse.quote(f"{t['name']} 경상북도")
    )
    return {
        "id": t["id"],
        "name": t["name"],
        "place_status": result["place_status"],
        "place_homepage": result["place_homepage"],
        "place_phone": result["place_phone"],
        "place_hours_hint": result["place_hours_hint"],
        "place_hours_raw": result["place_hours_raw"],
        "place_dept_keywords": result["place_dept_keywords"],
        "place_notes": result["place_notes"],
        "place_search_url": search_url,
        "_debug": {
            "query": query,
            "n_items": len(items),
            "top": [
                {
                    "id": it.get("id"),
                    "name": it.get("name"),
                    "road": it.get("roadAddress"),
                    "tel": it.get("tel"),
                }
                for it in items[:3]
            ],
        },
    }


def load_done_ids(path: Path) -> set[str]:
    if not path.exists():
        return set()
    ids: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            ids.add(json.loads(line)["id"])
        except Exception:  # noqa: BLE001
            pass
    return ids


def main() -> None:
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--offset", type=int, default=0)
    ap.add_argument("--ids", type=str, default="")
    ap.add_argument("--rewrite", action="store_true")
    args = ap.parse_args()

    data = json.loads(TARGETS.read_text(encoding="utf-8"))
    targets = data["targets"]
    if args.ids:
        want = set(args.ids.split(","))
        targets = [t for t in targets if t["id"] in want]
    else:
        targets = targets[args.offset :]
        if args.limit:
            targets = targets[: args.limit]

    done = set() if args.rewrite else load_done_ids(OUT)
    mode = "w" if args.rewrite and args.offset == 0 and not args.ids else "a"
    # if appending and rewrite specific, filter
    n_new = 0
    with OUT.open(mode, encoding="utf-8") as f:
        for t in targets:
            if t["id"] in done and not args.rewrite:
                print(f"skip {t['id']} {t['name']}")
                continue
            print(f"enrich {t['id']} {t['name']} {t['sigungu']} ...", flush=True)
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
            # strip debug for output file
            debug = row.pop("_debug", None)
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
            f.flush()
            n_new += 1
            print(
                f"  -> {row['place_status']} | {row.get('place_phone')} | {row.get('place_notes')[:80]}",
                flush=True,
            )
            if debug:
                print(f"     debug {debug}", flush=True)
            time.sleep(0.45)
    print(f"wrote {n_new} rows -> {OUT}")


if __name__ == "__main__":
    main()
