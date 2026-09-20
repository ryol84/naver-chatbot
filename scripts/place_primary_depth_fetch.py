#!/usr/bin/env python3
"""Fetch Naver Place search results for primary hospitals missing hours; write depth jsonl."""
from __future__ import annotations

import json
import os
import re
import subprocess
import time
import urllib.parse
from html import unescape
from pathlib import Path

ROOT = Path("/workspace")
TARGETS = ROOT / "data/hospitals/place-primary-depth-targets.json"
OUT = ROOT / "data/hospitals/place-primary-depth.jsonl"
FETCH_DIR = Path("/tmp/place-fetch/pages")
FETCH_DIR.mkdir(parents=True, exist_ok=True)

DEPT_KEYS = [
    "내과",
    "외과",
    "안과",
    "치과",
    "피부",
    "응급",
    "영상",
    "CT",
    "MRI",
    "재활",
    "고양이",
    "종양",
    "심장",
    "신경",
]

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


def curl_fetch(url: str, path: Path, timeout: int = 25) -> str:
    cmd = [
        "curl",
        "-sL",
        "-A",
        UA,
        "-H",
        "Accept-Language: ko-KR,ko;q=0.9",
        "--max-time",
        str(timeout),
        "-o",
        str(path),
        "-w",
        "%{http_code}",
        url,
    ]
    p = subprocess.run(cmd, capture_output=True, text=True)
    return p.stdout.strip()


def html_to_text(html: str) -> list[str]:
    html = re.sub(r"<script[\s\S]*?</script>", " ", html, flags=re.I)
    html = re.sub(r"<style[\s\S]*?</style>", " ", html, flags=re.I)
    text = re.sub(r"<[^>]+>", "\n", html)
    text = unescape(text)
    lines = [re.sub(r"\s+", " ", l).strip() for l in text.split("\n")]
    return [l for l in lines if l]


def norm_phone(p: str | None) -> str | None:
    d = re.sub(r"\D", "", p or "")
    if not d:
        return None
    if d.startswith("0507") and len(d) >= 11:
        return f"{d[:4]}-{d[4:8]}-{d[8:12]}"
    if d.startswith("02"):
        if len(d) == 9:
            return f"02-{d[2:5]}-{d[5:]}"
        if len(d) >= 10:
            return f"02-{d[2:6]}-{d[6:10]}"
    if len(d) == 10:
        return f"{d[:3]}-{d[3:6]}-{d[6:]}"
    if len(d) >= 11:
        return f"{d[:3]}-{d[3:7]}-{d[7:11]}"
    return p


def phones_in(s: str) -> list[str]:
    found = re.findall(r"0\d{1,3}[-\s]?\d{3,4}[-\s]?\d{4}", s)
    out = []
    for p in found:
        n = norm_phone(p)
        if n and n not in out:
            out.append(n)
    return out


def is_good_homepage(url: str) -> bool:
    if not url:
        return False
    u = url.lower().strip()
    reject = [
        "instagram.",
        "saramin.",
        "jobkorea.",
        "wanted.",
        "facebook.",
        "youtube.",
        "map.naver",
        "search.naver",
        "place.naver",
        "section.blog",
        "cafe.naver",
        "kin.naver",
        "shopping.naver",
        "smartstore",
        "coupang",
        "animaldoctor",
        "fitpet",
        "yakfact",
        "hansangsoo",
        "daangn",
        "114.co.kr",
        "sori114",
        "bemypet",
        "ban-life",
        "purpleo",
        "mustarddata",
        "petgo.",
        "animal.hospitalk",
        "mypet-119",
        "kimgoon",
        "open-maru",
        "duli.co",
        "bowwow.",
        "petcaremap",
        "powerlink",
        "adcr.naver",
        "pf.kakao",
        "twitter.",
        "tistory.com/",  # allow root clinic blogs only if clearly official — keep strict
    ]
    # allow tistory root later via explicit place homepage label only
    if any(r in u for r in reject if r != "tistory.com/"):
        return False
    if "blog.naver.com" in u:
        if re.search(r"PostView|postView|Redirect", url, re.I):
            return False
        if re.search(r"blog\.naver\.com/[A-Za-z0-9_\-]+/\d+", url):
            return False
        return bool(re.search(r"blog\.naver\.com/[A-Za-z0-9_\-]+", u))
    if "tistory.com" in u and re.search(r"tistory\.com/.+/entry", u):
        return False
    return u.startswith("http")


def normalize_hp(url: str) -> str:
    url = url.strip().replace("\\u002F", "/").replace("\\/", "/")
    if url.startswith("//"):
        url = "https:" + url
    if not url.startswith("http"):
        url = "https://" + url
    m = re.match(r"(https?://(?:m\.)?blog\.naver\.com/[A-Za-z0-9_\-]+)", url)
    if m:
        return m.group(1).replace("://m.blog", "://blog")
    return url.rstrip("/")


def area_tokens(target: dict) -> list[str]:
    toks = []
    for t in [target.get("sigungu"), target.get("sido")]:
        if not t:
            continue
        toks.append(t)
        for s in [
            t.replace("특별자치도", "")
            .replace("광역시", "")
            .replace("특별시", "")
            .replace("도", ""),
            t[:2],
        ]:
            if s and s not in toks:
                toks.append(s)
    addr = target.get("address") or ""
    for part in re.split(r"\s+", addr):
        if part.endswith(("동", "읍", "면")) and part not in toks:
            toks.append(part)
    return [x for x in toks if x and len(x) >= 2]


def area_ok(blob: str, target: dict) -> bool:
    if not blob:
        return False
    b = blob.replace(" ", "")
    return any(t.replace(" ", "") in b for t in area_tokens(target))


def extract_hours(blob: str) -> tuple[str | None, str | None]:
    if not blob:
        return None, None
    hint = None
    raw = None
    if re.search(r"연중무휴|24시간\s*영업|24시간\s*진료|매일\s*00\s*:\s*00", blob):
        hint = "always_open"
    if re.search(r"매주\s*일요일\s*휴무|일요일\s*휴무|일요휴진|일요일은\s*휴무", blob):
        hint = hint or "sunday_closed"
    pats = re.findall(
        r"(?:평일|주중|토요일|일요일|공휴일|매일|월[\s~\-–]금|월-금)"
        r"[^\n]{0,8}\d{1,2}\s*[:：]\s*\d{2}\s*[-~～]\s*\d{1,2}\s*[:：]\s*\d{2}",
        blob,
    )
    if pats:
        raw = " | ".join(dict.fromkeys(pats))
        hint = hint or raw
    # name-based 24시 only if also confirmed in hours section (caller decides)
    return hint, raw


def find_place_card(lines: list[str], name: str) -> tuple[list[str] | None, str]:
    n = name.replace(" ", "")
    candidates = []
    for i, l in enumerate(lines):
        lr = l.replace(" ", "")
        if n not in lr or len(l) > len(name) + 20:
            continue
        # skip title/search chrome
        if "검색" in l or "네이버" in l:
            continue
        window = lines[i : i + 50]
        wtext = "\n".join(window)
        if any(x in wtext[:80] for x in ["파워링크", "사이트검색광고"]):
            continue
        has_addr = bool(
            re.search(
                r"(서울|부산|대구|인천|광주|대전|울산|세종|경기|강원|충북|충남|전북|전남|경북|경남|제주|충청|전라|경상)",
                wtext,
            )
        )
        has_tel = "전화번호" in wtext or bool(re.search(r"0\d{1,3}-\d{3,4}-\d{4}", wtext))
        has_hours = "영업시간" in wtext
        has_hp = "홈페이지" in wtext
        score = (
            (3 if has_addr else 0)
            + (3 if has_tel else 0)
            + (2 if has_hours else 0)
            + (1 if has_hp else 0)
        )
        if has_addr or has_tel:
            candidates.append((score, -i, window, wtext))
    if not candidates:
        return None, ""
    candidates.sort(reverse=True)
    return candidates[0][2], candidates[0][3]


def extract_depts_safe(html: str, name: str, card: str) -> list[str]:
    depts: list[str] = []
    # animaldoctor structured line for this hospital
    for m in re.finditer(
        r"병원이름\s*[:：]\s*" + re.escape(name) + r".{0,300}", html, re.S
    ):
        chunk = m.group(0)
        dm = re.search(r"진료과목\s*[:：]\s*([^<\n]+)", chunk)
        if dm:
            for k in DEPT_KEYS:
                if k in dm.group(1) and k not in depts:
                    depts.append(k)
    # Place description / 소개 near card only — avoid ads
    if card:
        # ignore card convenience chips; look for 진료 keywords only if not from ads block
        pass
    return depts


def parse_search(html: str, target: dict, source_url: str) -> dict:
    lines = html_to_text(html)
    name = target["name"]
    card_lines, card = find_place_card(lines, name)
    rec = {
        "id": target["id"],
        "name": name,
        "place_homepage": None,
        "place_phone": None,
        "place_hours_hint": None,
        "place_hours_raw": None,
        "place_dept_keywords": [],
        "place_notes": "",
        "place_status": "no_hit",
        "place_search_url": source_url,
    }
    addr = None
    if card:
        m = re.search(
            r"주소\n([^\n]+)\n",
            card,
        )
        if m:
            addr = m.group(1).strip()
        if not addr:
            m = re.search(
                r"((?:서울|부산|대구|인천|광주|대전|울산|세종|경기|강원|충북|충남|전북|전남|경북|경남|제주|충청|전라|경상)[^\n]{3,55})",
                card,
            )
            if m:
                addr = m.group(1).strip()
                addr = re.sub(
                    r"(지도|거리뷰|영업시간|전화번호|홈페이지|길찾기).*$", "", addr
                ).strip()

        m = re.search(r"전화번호\n([0-9\-]+)", card)
        if m:
            rec["place_phone"] = norm_phone(m.group(1))
        else:
            ph = phones_in(card)
            listed = target.get("phone")
            if listed:
                ld = re.sub(r"\D", "", listed)
                for p in ph:
                    if re.sub(r"\D", "", p)[-8:] == ld[-8:]:
                        rec["place_phone"] = p
                        break
            if not rec["place_phone"] and ph:
                # prefer 0507 virtual tel from Place
                for p in ph:
                    if p.startswith("0507"):
                        rec["place_phone"] = p
                        break
                if not rec["place_phone"]:
                    rec["place_phone"] = ph[0]

        m = re.search(r"홈페이지\n([^\n]+)", card)
        if m and is_good_homepage(m.group(1)):
            rec["place_homepage"] = normalize_hp(m.group(1))

        hint, raw = extract_hours(card)
        # 24시 in hospital name as soft hint only if Place says 연중무휴/24시간 OR name starts with 24시 and card hit
        if not hint and name.startswith("24시") and card:
            if re.search(r"24시간|연중무휴|24시", card):
                hint = "always_open"
            elif "24시" in name:
                hint = "always_open"  # Place card for a 24시-named clinic
        rec["place_hours_hint"] = hint
        rec["place_hours_raw"] = raw

    # homepage from JSON repr near place
    if not rec["place_homepage"]:
        for m in re.finditer(r'"repr"\s*:\s*"(https?:[^"]+)"', html):
            u = m.group(1).replace("\\u002F", "/").replace("\\/", "/")
            if "\\u" in u:
                try:
                    u = u.encode("utf-8").decode("unicode_escape")
                except Exception:
                    pass
            if is_good_homepage(u):
                pos = m.start()
                if name[:4] in html[max(0, pos - 2500) : pos + 200]:
                    rec["place_homepage"] = normalize_hp(u)
                    break

    rec["place_dept_keywords"] = extract_depts_safe(html, name, card)

    listed = target.get("phone")
    phone_match = False
    if listed and rec["place_phone"]:
        phone_match = (
            re.sub(r"\D", "", rec["place_phone"])[-8:]
            == re.sub(r"\D", "", listed)[-8:]
        )
    elif listed and listed in html and name in html:
        phone_match = True
        if not rec["place_phone"]:
            rec["place_phone"] = listed

    region_match = area_ok(addr or "", target) or area_ok(card or "", target)
    name_in_card = bool(card and name.replace(" ", "") in card.replace(" ", ""))

    # Wrong-region Place card (e.g. listed Taean but Place is Incheon)
    if name_in_card and addr and not area_ok(addr, target):
        rec["place_status"] = "ambiguous"
        notes = [f"listed {target.get('sigungu')} but Place {addr[:50]}"]
        if rec["place_hours_hint"]:
            notes.append(str(rec["place_hours_hint"]))
        if phone_match:
            notes.append("phone matches Place (region data mismatch)")
        if rec["place_homepage"]:
            notes.append("official channel")
        rec["place_notes"] = "; ".join(notes)[:200]
        return rec

    if name_in_card and (region_match or phone_match):
        rec["place_status"] = "hit"
    elif phone_match and region_match:
        rec["place_status"] = "hit"
    elif name in html and region_match:
        rec["place_status"] = "hit"
        if not rec["place_phone"] and listed:
            rec["place_phone"] = listed
        if not rec["place_hours_hint"]:
            for m in re.finditer(
                re.escape(name) + r".{0,150}(평일[^.]{0,50}|일요일 휴무|매주 일요일[^.]{0,30})",
                html,
            ):
                h, r = extract_hours(m.group(0))
                if h:
                    rec["place_hours_hint"] = h
                    rec["place_hours_raw"] = r
                    break
    elif name_in_card:
        rec["place_status"] = "ambiguous"
    elif name in html and not region_match:
        rec["place_status"] = "ambiguous"
    else:
        rec["place_status"] = "no_hit"

    notes = []
    if addr:
        notes.append(addr[:50])
    if rec["place_status"] == "hit":
        notes.append("Place/dir hit")
    elif rec["place_status"] == "ambiguous":
        notes.append("ambiguous")
    if rec["place_hours_hint"]:
        notes.append(str(rec["place_hours_hint"])[:70])
    if rec["place_homepage"]:
        notes.append("official channel")
    elif rec["place_status"] == "hit":
        notes.append("no official homepage")
    rec["place_notes"] = "; ".join(notes)[:200]
    return rec


def search_url(name: str, area: str) -> str:
    q = urllib.parse.quote(f"{name} {area}")
    return f"https://search.naver.com/search.naver?query={q}"


def extra_area_guesses(target: dict) -> list[str]:
    """Extra query areas when listed region may be wrong (phone area code)."""
    phone = re.sub(r"\D", "", target.get("phone") or "")
    extras = []
    # common mismatches
    if phone.startswith("032"):
        extras += ["인천", "인천 서구", "인천 계양구", "인천 부평구", "인천 남동구"]
    if phone.startswith("02"):
        extras += ["서울"]
    if phone.startswith("051"):
        extras += ["부산"]
    if phone.startswith("053"):
        extras += ["대구"]
    if phone.startswith("062"):
        extras += ["광주"]
    # always try name + first address token
    addr = target.get("address") or ""
    m = re.search(r"([가-힣]+[동읍면])", addr)
    if m:
        extras.append(m.group(1))
    return extras


def process_one(target: dict, sleep_s: float = 1.2) -> dict:
    urls = [
        target["place_search_url"],
        search_url(target["name"], target.get("sigungu") or ""),
        search_url(target["name"], target.get("sido") or ""),
    ]
    for area in extra_area_guesses(target):
        urls.append(search_url(target["name"], area))
    # dedupe
    seen = set()
    uniq = []
    for u in urls:
        if u not in seen:
            seen.add(u)
            uniq.append(u)
    # Cap extra fetches
    uniq = uniq[:5]

    best = None

    def rank(r):
        st = r["place_status"]
        return (
            2 if st == "hit" else (1 if st == "ambiguous" else 0),
            1 if r.get("place_hours_hint") else 0,
            1 if r.get("place_homepage") else 0,
            1 if r.get("place_phone") else 0,
            1 if r.get("place_dept_keywords") else 0,
        )

    for i, url in enumerate(uniq):
        path = FETCH_DIR / f"{target['id']}_{i}.html"
        code = curl_fetch(url, path)
        time.sleep(sleep_s)
        if code != "200" or not path.exists() or path.stat().st_size < 2000:
            continue
        html = path.read_text(encoding="utf-8", errors="ignore")
        rec = parse_search(html, target, url)
        if best is None or rank(rec) > rank(best):
            best = rec
        if rec["place_status"] == "hit" and rec.get("place_hours_hint"):
            break
        # stop early on solid hit after primary+sigungu tries
        if rec["place_status"] == "hit" and i >= 1 and rec.get("place_phone"):
            if rec.get("place_hours_hint") or rec.get("place_homepage"):
                break
    if best is None:
        best = {
            "id": target["id"],
            "name": target["name"],
            "place_homepage": None,
            "place_phone": target.get("phone"),
            "place_hours_hint": None,
            "place_hours_raw": None,
            "place_dept_keywords": [],
            "place_notes": "fetch failed",
            "place_status": "no_hit",
            "place_search_url": target["place_search_url"],
        }
    return best


def main():
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--start", type=int, default=0)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--sleep", type=float, default=1.3)
    ap.add_argument("--resume", action="store_true")
    args = ap.parse_args()

    data = json.loads(TARGETS.read_text())
    targets = data["targets"]
    if args.limit:
        targets = targets[args.start : args.start + args.limit]
    else:
        targets = targets[args.start :]

    done = set()
    if args.resume and OUT.exists():
        for line in OUT.read_text().splitlines():
            if not line.strip():
                continue
            try:
                done.add(json.loads(line)["id"])
            except Exception:
                pass

    mode = "a" if args.resume else "w"
    with OUT.open(mode, encoding="utf-8") as f:
        for i, t in enumerate(targets):
            if t["id"] in done:
                print(f"skip {t['id']} {t['name']}")
                continue
            print(f"[{args.start + i + 1}/{args.start + len(targets)}] {t['name']} {t.get('sigungu')}")
            rec = process_one(t, sleep_s=args.sleep)
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            f.flush()
            print(
                " ->",
                rec["place_status"],
                rec.get("place_hours_hint"),
                rec.get("place_phone"),
                rec.get("place_homepage"),
            )


if __name__ == "__main__":
    main()
