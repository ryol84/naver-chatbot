#!/usr/bin/env python3
"""Collect every public field on Maruvet hospital detail pages.

One request at a time, with a pause between pages. Does not call /api/.
Resumes from data/hospitals/sources/maruvet-details.jsonl.
"""

from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.request
from html import unescape
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LISTING = ROOT / "data/hospitals/sources/maruvet-hospitals.jsonl"
OUT = ROOT / "data/hospitals/sources/maruvet-details.jsonl"
FAIL = ROOT / "data/hospitals/sources/maruvet-details-failures.jsonl"
LOG = Path("/tmp/maru_detail.log")

UA = "Mozilla/5.0 (compatible; hospital-directory; polite; one-page-at-a-time)"
DELAY_S = 1.2
TIMEOUT_S = 40


def log(msg: str) -> None:
    line = f"{time.strftime('%H:%M:%S')} {msg}"
    print(line, flush=True)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def done_ids() -> set[str]:
    ids: set[str] = set()
    if not OUT.exists():
        return ids
    for line in OUT.open(encoding="utf-8"):
        line = line.strip()
        if not line:
            continue
        try:
            ids.add(json.loads(line)["license_id"])
        except (json.JSONDecodeError, KeyError):
            continue
    return ids


def fetch(url: str) -> tuple[int, str]:
    req = urllib.request.Request(
        url,
        headers={"User-Agent": UA, "Accept": "text/html"},
    )
    with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resp:
        raw = resp.read()
        charset = resp.headers.get_content_charset() or "utf-8"
        return resp.status, raw.decode(charset, errors="replace")


def ld_place(html: str) -> dict:
    for blob in re.findall(
        r'<script type="application/ld\+json">(.*?)</script>', html, re.S
    ):
        try:
            data = json.loads(blob)
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict) and data.get("@type") == "VeterinaryCare":
            return data
    return {}


def text_of(fragment: str) -> str:
    fragment = re.sub(r"<[^>]+>", " ", fragment)
    return re.sub(r"\s+", " ", unescape(fragment)).strip()


def section(html: str, start_marker: str, end_markers: tuple[str, ...]) -> str:
    i = html.find(start_marker)
    if i < 0:
        return ""
    end = len(html)
    for marker in end_markers:
        j = html.find(marker, i + len(start_marker))
        if j > 0:
            end = min(end, j)
    return html[i:end]


def pills(fragment: str) -> list[dict]:
    items = []
    for href, inner in re.findall(r'<a class="pill" href="([^"]*)"[^>]*>(.*?)</a>', fragment, re.S):
        cat = ""
        cat_m = re.search(r'class="pcat">([^<]*)', inner)
        if cat_m:
            cat = unescape(cat_m.group(1)).strip()
        dist = ""
        dist_m = re.search(r'class="pdist">\s*·?\s*([^<]*)', inner)
        if dist_m:
            dist = unescape(dist_m.group(1)).strip()
        name = text_of(re.sub(r"<span[\s\S]*?</span>", "", inner))
        items.append({"name": name, "category": cat, "distance": dist, "href": unescape(href)})
    return items


def info_dl(html: str) -> dict:
    block = section(html, '<dl class="info">', ("</dl>",))
    out: dict[str, str] = {}
    for dt, dd in re.findall(r"<dt[^>]*>(.*?)</dt>\s*<dd[^>]*>(.*?)</dd>", block, re.S):
        key = text_of(dt)
        if key == "전화":
            tel = re.search(r'href="tel:([^"]+)"', dd)
            out[key] = unescape(tel.group(1)) if tel else text_of(dd)
        else:
            out[key] = text_of(dd)
    return out


def channels(html: str) -> list[dict]:
    block = section(html, "<h2>병원 공식 채널</h2>", ("</section>",))
    found = []
    for href, inner in re.findall(r'<a href="([^"]+)"[^>]*>(.*?)</a>', block, re.S):
        label = text_of(inner)
        if label:
            found.append({"label": label, "url": unescape(href)})
    return found


def about_items(html: str) -> list[dict]:
    block = section(html, 'class="aiabout"', ("</section>",))
    items = []
    for label, body, src in re.findall(
        r'class="ail">([^<]*)</b>\s*<span class="ait">([^<]*)</span>(?:\s*<span class="aisrc">\s*·\s*<a href="([^"]*)")?',
        block,
    ):
        items.append(
            {
                "label": unescape(label).strip(),
                "text": unescape(body).strip(),
                "source_url": unescape(src) if src else "",
            }
        )
    return items


def facilities(html: str) -> list[dict]:
    block = section(html, "<dt>시설·장비</dt>", ("</dd>",))
    groups = []
    for chunk in re.findall(r'class="facg">(.*?)</div>', block, re.S):
        label_m = re.search(r'class="facl">([^<]*)', chunk)
        names = [unescape(n).strip() for n in re.findall(r'class="bdg[^"]*">([^<]+)', chunk)]
        if label_m or names:
            groups.append(
                {
                    "group": unescape(label_m.group(1)).strip() if label_m else "",
                    "items": names,
                }
            )
    return groups


def parking_note(html: str) -> str:
    m = re.search(r"<dt>주차</dt>\s*<dd>(.*?)</dd>", html, re.S)
    return text_of(m.group(1)) if m else ""


def blog_block(html: str) -> dict:
    block = section(html, 'class="blogs"', ("</section>",))
    count = None
    cm = re.search(r"최근 1년\s*<b>(\d+)건</b>", block)
    if cm:
        count = int(cm.group(1))
    themes = [unescape(t).strip() for t in re.findall(r'class="bdg bk">([^<]+)', block)]
    posts = []
    for inner in re.findall(r'<ul class="blist">([\s\S]*?)</ul>', block):
        for url, title in re.findall(r'<a href="([^"]+)"[^>]*>(.*?)</a>', inner, re.S):
            posts.append({"title": text_of(title), "url": unescape(url)})
    return {"count_1y": count, "themes": themes, "posts": posts}


def hours_json(html: str):
    m = re.search(r'class="nowc"[^>]*data-h="([^"]+)"', html)
    if not m:
        return None
    raw = unescape(m.group(1))
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return raw


def parse_page(html: str, listing: dict) -> dict:
    place = ld_place(html)
    address = place.get("address") or {}
    geo = place.get("geo") or {}
    info = info_dl(html)
    amenities = []
    for item in place.get("amenityFeature") or []:
        if isinstance(item, dict) and item.get("name"):
            amenities.append({"name": item.get("name"), "value": item.get("value")})
    hours_spec = []
    for item in place.get("openingHoursSpecification") or []:
        if isinstance(item, dict):
            hours_spec.append(
                {
                    "day": item.get("dayOfWeek"),
                    "opens": item.get("opens"),
                    "closes": item.get("closes"),
                }
            )
    same_as = place.get("sameAs") or []
    if isinstance(same_as, str):
        same_as = [same_as]
    pharm = section(html, 'class="pharm"', ("</section>",))
    near = section(html, ">주변 반려 시설", ("</section>",))
    return {
        "source": "maruvet-detail",
        "license_id": listing["license_id"],
        "name": place.get("name") or listing.get("name") or "",
        "sido_short": listing.get("sido_short") or "",
        "sigungu": listing.get("sigungu") or "",
        "address_region": address.get("addressRegion") or "",
        "address_locality": address.get("addressLocality") or "",
        "road_address": info.get("도로명") or address.get("streetAddress") or listing.get("address") or "",
        "jibun_address": info.get("지번") or "",
        "phone": info.get("전화") or place.get("telephone") or listing.get("phone") or "",
        "opened": info.get("개원(등록)") or "",
        "lat": geo.get("latitude", listing.get("lat")),
        "lng": geo.get("longitude", listing.get("lng")),
        "hours_24h": listing.get("hours_24h"),
        "hours": hours_json(html) or listing.get("hours"),
        "opening_hours_spec": hours_spec,
        "specialties": place.get("medicalSpecialty") or [],
        "amenities": amenities,
        "facility_groups": facilities(html),
        "parking": parking_note(html),
        "about": about_items(html),
        "official_channels": channels(html),
        "same_as": same_as,
        "blog": blog_block(html),
        "blog_mentions_listing": listing.get("blog_mentions"),
        "nearby_pharmacies": pills(pharm),
        "nearby_pet_places": pills(near),
        "url": listing.get("url") or place.get("url") or "",
    }


def main() -> None:
    listings = []
    for line in LISTING.open(encoding="utf-8"):
        if line.strip():
            listings.append(json.loads(line))
    seen = done_ids()
    todo = [row for row in listings if row["license_id"] not in seen]
    log(f"listings={len(listings)} done={len(seen)} todo={len(todo)}")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    consecutive_fail = 0
    for n, row in enumerate(todo, 1):
        url = row["url"]
        if not url.startswith("http"):
            url = "https://www.maruvet.com" + url
        try:
            status, html = fetch(url)
            if "VeterinaryCare" not in html and "병원" not in html[:2000]:
                raise RuntimeError(f"unexpected page status={status} len={len(html)}")
            record = parse_page(html, row)
            with OUT.open("a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
            consecutive_fail = 0
            if n % 25 == 0 or n == 1:
                log(f"{n}/{len(todo)} {record['name']} specs={len(record['specialties'])} channels={len(record['official_channels'])}")
        except Exception as exc:
            consecutive_fail += 1
            err = {"license_id": row.get("license_id"), "url": url, "error": str(exc)}
            with FAIL.open("a", encoding="utf-8") as f:
                f.write(json.dumps(err, ensure_ascii=False) + "\n")
            log(f"FAIL {n}/{len(todo)} {row.get('license_id')} {exc}")
            if isinstance(exc, urllib.error.HTTPError) and exc.code in (429, 503):
                time.sleep(45)
            if consecutive_fail >= 12:
                log("stopping after 12 consecutive failures")
                break
        time.sleep(DELAY_S)
    log(f"finished out_lines={sum(1 for _ in OUT.open(encoding='utf-8')) if OUT.exists() else 0}")


if __name__ == "__main__":
    main()
