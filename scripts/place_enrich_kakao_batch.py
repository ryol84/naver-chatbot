#!/usr/bin/env python3
"""Batch-fetch Kakao m.map search hits for neighborhood place enrichment."""
from __future__ import annotations

import json
import re
import subprocess
import time
import urllib.parse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGETS = ROOT / "data/hospitals/place-neigh-final-wave2-targets.json"
OUT_RAW = ROOT / "data/hospitals/_place-neigh-final-wave2-kakao-raw.json"

UA = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1"
)


def curl_get(url: str) -> str:
    r = subprocess.run(
        [
            "curl",
            "-sL",
            "-A",
            UA,
            "--max-time",
            "20",
            url,
        ],
        capture_output=True,
        encoding="utf-8",
        errors="replace",
    )
    return r.stdout or ""


PLACE_RE = re.compile(
    r"dataList\.push\(\{(.*?)\}\);",
    re.S,
)


def parse_places(html: str) -> list[dict]:
    places = []
    for m in PLACE_RE.finditer(html):
        block = m.group(1)
        def decode_js(s: str) -> str:
            if "\\u" in s or "\\x" in s:
                try:
                    return s.encode("utf-8").decode("unicode_escape")
                except Exception:
                    return s
            return s

        def field(key: str):
            mm = re.search(rf"{key}\s*:\s*'((?:\\'|[^'])*)'", block)
            if not mm:
                mm = re.search(rf'{key}\s*:\s*"((?:\\"|[^"])*)"', block)
            if not mm:
                return None
            return decode_js(mm.group(1))

        name = field("name")
        if not name:
            continue
        # category depth3
        cat = None
        cm = re.search(r"depth3:\s*'((?:\\'|[^'])*)'", block)
        if cm:
            cat = decode_js(cm.group(1))
        places.append(
            {
                "id": field("id"),
                "name": name,
                "phone": field("phoneNum") or None,
                "category": cat,
            }
        )
    # also try to get addresses from surrounding HTML if present
    return places


def addr_tokens(address: str | None) -> list[str]:
    if not address:
        return []
    # keep meaningful road/number fragments
    parts = re.split(r"[\s,()]+", address)
    out = []
    for p in parts:
        if len(p) >= 2 and not p.endswith(("광역시", "특별시", "도", "시", "군", "구")):
            out.append(p)
    return out


def main() -> None:
    data = json.loads(TARGETS.read_text())
    targets = data["targets"]
    results = []
    for i, t in enumerate(targets):
        # Prefer name + road fragment for common names
        road = ""
        if t.get("address"):
            m = re.search(r"([가-힣0-9]+(?:로|길|대로)\s*\d*[-\d]*)", t["address"])
            if m:
                road = m.group(1)
        q = f"{t['name']} {road or t.get('sigungu') or t.get('sido') or ''}".strip()
        url = "https://m.map.kakao.com/actions/searchView?q=" + urllib.parse.quote(q)
        html = curl_get(url)
        places = parse_places(html)
        # If empty, retry with sigungu
        if not places and road:
            q2 = f"{t['name']} {t.get('sigungu') or ''}".strip()
            url = "https://m.map.kakao.com/actions/searchView?q=" + urllib.parse.quote(q2)
            html = curl_get(url)
            places = parse_places(html)
            q = q2
        # score matches
        scored = []
        phone = (t.get("phone") or "").replace(" ", "")
        name_n = t["name"].replace(" ", "")
        for p in places:
            score = 0
            notes = []
            pn = (p.get("name") or "").replace(" ", "")
            if pn and (pn == name_n or name_n in pn or pn in name_n):
                score += 5
                notes.append("name")
            if phone and p.get("phone") and phone == p["phone"].replace(" ", ""):
                score += 10
                notes.append("phone")
            if p.get("category") == "동물병원":
                score += 1
                notes.append("cat")
            scored.append({**p, "score": score, "match_notes": notes})
        scored.sort(key=lambda x: -x["score"])
        results.append(
            {
                "id": t["id"],
                "name": t["name"],
                "sido": t.get("sido"),
                "sigungu": t.get("sigungu"),
                "address": t.get("address"),
                "phone": t.get("phone"),
                "homepage": t.get("homepage"),
                "hours_raw": t.get("hours_raw"),
                "place_search_url": t.get("place_search_url"),
                "query": q,
                "kakao_top": scored[:8],
                "kakao_n": len(scored),
            }
        )
        print(f"[{i+1:03d}/100] {t['name']} → {len(scored)} places; top={scored[0] if scored else None}")
        time.sleep(0.35)
    OUT_RAW.write_text(json.dumps(results, ensure_ascii=False, indent=2))
    print("wrote", OUT_RAW)


if __name__ == "__main__":
    main()
