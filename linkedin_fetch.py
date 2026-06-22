"""
LinkedIn 조직 성과 수집 → index.html __BAKED_DATA__ 머지 (대시보드용)

⚠️ 비밀값은 전부 환경변수에서만 읽음 (이 파일/repo에 하드코딩 금지 — public repo):
    LINKEDIN_CLIENT_ID, LINKEDIN_CLIENT_SECRET, LINKEDIN_REFRESH_TOKEN, LINKEDIN_ORG_URN
    (선택) LINKEDIN_VERSION (기본 202606)

수집:
  - 게시물 목록 + 게시물별 통계 → 발행 주차별 노출 합(impressions) + 게시물 TOP(__li_posts__)
  - networkSizes → 현재 누적 팔로워 → 최신 주차 followers 스냅샷, newFollowers=직전주 대비 증감

사용:  python3 linkedin_fetch.py [--dry]
  --dry : index.html 수정 없이 머지 결과만 출력
"""
import os, re, sys, json, datetime, urllib.parse, pathlib
import requests

VERSION = os.environ.get("LINKEDIN_VERSION", "202606")
BASE = "https://api.linkedin.com/rest"
KST = datetime.timezone(datetime.timedelta(hours=9))


def _env(k):
    v = os.environ.get(k)
    if not v:
        raise SystemExit(f"❌ 환경변수 {k} 없음 (LinkedIn 비밀값은 env/Secret로 주입)")
    return v


def access_token():
    r = requests.post("https://www.linkedin.com/oauth/v2/accessToken", data={
        "grant_type": "refresh_token",
        "refresh_token": _env("LINKEDIN_REFRESH_TOKEN"),
        "client_id": _env("LINKEDIN_CLIENT_ID"),
        "client_secret": _env("LINKEDIN_CLIENT_SECRET"),
    }, timeout=30)
    if r.status_code >= 400:
        raise SystemExit(f"❌ 토큰 갱신 실패 {r.status_code}: {r.text[:200]}")
    return r.json()["access_token"]


def _headers(tok):
    return {"Authorization": f"Bearer {tok}", "X-Restli-Protocol-Version": "2.0.0",
            "Linkedin-Version": VERSION, "Content-Type": "application/json"}


def _get(url, h, extra=None):
    hh = dict(h)
    if extra:
        hh.update(extra)
    r = requests.get(url, headers=hh, timeout=30)
    if r.status_code >= 400:
        raise RuntimeError(f"LinkedIn {r.status_code}: {r.text[:300]}\n{url}")
    return r.json()


def iso_week(ms):
    d = datetime.datetime.fromtimestamp(ms / 1000, KST).date()
    y, w, _ = d.isocalendar()
    return f"{y}-W{w:02d}", d.isoformat()


def list_posts(org, h, maxp=120):
    enc = urllib.parse.quote(org, safe="")
    posts, start, cnt = [], 0, 50
    while len(posts) < maxp:
        url = f"{BASE}/posts?q=author&author={enc}&count={cnt}&start={start}&sortBy=CREATED"
        els = _get(url, h, {"X-RestLi-Method": "FINDER"}).get("elements", [])
        if not els:
            break
        for p in els:
            posts.append({"urn": p.get("id", ""), "commentary": p.get("commentary", "") or "",
                          "published_at": p.get("publishedAt") or p.get("createdAt")})
        if len(els) < cnt:
            break
        start += cnt
    return posts[:maxp]


def share_stats(org, urns, h):
    enc_org = urllib.parse.quote(org, safe="")
    res = {}

    def batch(l, n=20):
        for i in range(0, len(l), n):
            yield l[i:i + n]

    for typ, key, param in [(":share:", "share", "shares"), (":ugcPost:", "ugcPost", "ugcPosts")]:
        for ch in batch([u for u in urns if typ in u]):
            enc = ",".join(urllib.parse.quote(u, safe="") for u in ch)
            url = (f"{BASE}/organizationalEntityShareStatistics?q=organizationalEntity"
                   f"&organizationalEntity={enc_org}&{param}=List({enc})")
            for e in _get(url, h).get("elements", []):
                k = e.get(key)
                if k:
                    res[k] = e.get("totalShareStatistics", {})
    return res


def network_size(org, h):
    enc = urllib.parse.quote(org, safe="")
    d = _get(f"{BASE}/networkSizes/{enc}?edgeType=COMPANY_FOLLOWED_BY_MEMBER", h)
    return int(d.get("firstDegreeSize") or 0)


def main():
    dry = "--dry" in sys.argv
    org = _env("LINKEDIN_ORG_URN")
    h = _headers(access_token())

    posts = list_posts(org, h)
    stats = share_stats(org, [p["urn"] for p in posts], h)
    followers = network_size(org, h)

    week_imp, li_posts = {}, []
    for p in posts:
        s = stats.get(p["urn"], {})
        imp = int(s.get("impressionCount") or 0)
        if imp == 0:
            continue  # 통계 없음(12개월 초과/광고만) → 제외
        wk, date = iso_week(p["published_at"])
        week_imp[wk] = week_imp.get(wk, 0) + imp
        li_posts.append({
            "date": date,
            "title": re.sub(r'\\([<>*_~\[\]()])', r'\1', p["commentary"].strip().split("\n")[0])[:80],
            "impressions": imp,
            "reactions": int(s.get("likeCount") or 0),
            "comments": int(s.get("commentCount") or 0),
            "clicks": int(s.get("clickCount") or 0),
        })
    li_posts.sort(key=lambda x: x["impressions"], reverse=True)

    html = pathlib.Path(__file__).with_name("index.html")
    src = html.read_text()
    m = re.search(r'(const __BAKED_DATA__ = )(\{.*?\});', src, re.DOTALL)
    baked = json.loads(m.group(2))

    for wk, imp in week_imp.items():
        baked.setdefault(wk, {})["impressions"] = imp

    weeks = sorted(k for k in baked if re.match(r"\d{4}-W\d{2}$", k))
    if weeks:
        latest = weeks[-1]
        prev_total = next((baked[w]["followers"] for w in reversed(weeks[:-1])
                           if baked[w].get("followers")), 0)
        baked[latest]["followers"] = followers
        baked[latest]["newFollowers"] = max(0, followers - prev_total) if prev_total else 0

    baked["__li_posts__"] = li_posts

    print(f"📊 주차별 노출 {len(week_imp)}개 / 게시물(노출>0) {len(li_posts)}건 / 누적 팔로워 {followers}")
    for wk in sorted(week_imp)[-6:]:
        print(f"   {wk}: 노출 {week_imp[wk]}")
    print("   게시물 TOP3:", [(x["title"][:18], x["impressions"]) for x in li_posts[:3]])
    if weeks:
        print(f"   최신주 {latest}: followers={followers} newFollowers={baked[latest]['newFollowers']}")

    if dry:
        print("🔸 --dry: index.html 미수정")
        return
    src = src[:m.start(2)] + json.dumps(baked, ensure_ascii=False) + src[m.end(2):]
    html.write_text(src)
    print("✅ index.html __BAKED_DATA__ 머지 완료")


if __name__ == "__main__":
    main()
