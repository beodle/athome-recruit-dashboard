"""
YouTube 팟캐스트(홈레코딩) 성과 수집 → index.html __BAKED_DATA__ 머지

⚠️ 비밀값은 환경변수에서만: YOUTUBE_API_KEY  (선택) YOUTUBE_CHANNEL_ID
수집: 채널 구독자(현재값) + 홈레코딩 시리즈 영상별 조회·좋아요·댓글 (전체 시리즈, 조회순)
사용: python3 youtube_fetch.py [--dry]
"""
import os, re, sys, json, pathlib
import requests

API = "https://www.googleapis.com/youtube/v3"
CHANNEL = os.environ.get("YOUTUBE_CHANNEL_ID", "UCfRWcGQK-952YXBIaHFcsNA")
PODCAST_RE = re.compile(r"홈레코딩|Track")  # 홈레코딩 시리즈 판별


def _key():
    k = os.environ.get("YOUTUBE_API_KEY")
    if not k:
        raise SystemExit("❌ 환경변수 YOUTUBE_API_KEY 없음")
    return k


def get(url):
    r = requests.get(url, timeout=30)
    if r.status_code >= 400:
        raise RuntimeError(f"YouTube {r.status_code}: {r.text[:300]}")
    return r.json()


def main():
    dry = "--dry" in sys.argv
    key = _key()

    ch = get(f"{API}/channels?part=statistics&id={CHANNEL}&key={key}")
    if not ch.get("items"):
        raise SystemExit("❌ 채널 조회 실패")
    subs = int(ch["items"][0]["statistics"].get("subscriberCount") or 0)

    # 업로드 재생목록 → 영상 ID 전부
    uploads = "UU" + CHANNEL[2:]
    ids, page = [], ""
    while True:
        url = f"{API}/playlistItems?part=contentDetails&playlistId={uploads}&maxResults=50&key={key}"
        if page:
            url += f"&pageToken={page}"
        d = get(url)
        ids += [x["contentDetails"]["videoId"] for x in d.get("items", [])]
        page = d.get("nextPageToken")
        if not page:
            break

    # 영상 통계 (50개씩) → 홈레코딩만
    vids = []
    for i in range(0, len(ids), 50):
        d = get(f"{API}/videos?part=snippet,statistics&id={','.join(ids[i:i+50])}&key={key}")
        for v in d.get("items", []):
            sn, s = v["snippet"], v["statistics"]
            if not PODCAST_RE.search(sn["title"]):
                continue
            vids.append({
                "date": sn["publishedAt"][:10],
                "title": sn["title"],
                "views": int(s.get("viewCount") or 0),
                "likes": int(s.get("likeCount") or 0),
                "comments": int(s.get("commentCount") or 0),
            })
    vids.sort(key=lambda x: x["views"], reverse=True)

    html = pathlib.Path(__file__).with_name("index.html")
    src = html.read_text()
    m = re.search(r'(const __BAKED_DATA__ = )(\{.*?\});', src, re.DOTALL)
    baked = json.loads(m.group(2))
    baked["__yt_subscribers__"] = subs
    baked["__yt_videos__"] = vids

    print(f"📺 구독자 {subs} / 홈레코딩 영상 {len(vids)}건")
    for v in vids[:5]:
        print(f"   조회 {v['views']:>5} | {v['title'][:34]}")
    if dry:
        print("🔸 --dry: index.html 미수정")
        return
    src = src[:m.start(2)] + json.dumps(baked, ensure_ascii=False) + src[m.end(2):]
    html.write_text(src)
    print("✅ index.html __BAKED_DATA__ 머지 완료")


if __name__ == "__main__":
    main()
