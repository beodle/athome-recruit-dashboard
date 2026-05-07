#!/bin/bash
# GA4 채용 페이지 + 블로그 데이터 갱신 → 대시보드 베이크 → 커밋·푸시
# 사용법:
#   ./update.sh                    # 최근 4주 자동
#   ./update.sh 2026-W16 2026-W17  # 특정 주차 지정

set -euo pipefail
cd "$(dirname "$0")"

# ── 1. 갱신할 주차 결정 ─────────────────────────────────────
if [ $# -gt 0 ]; then
  WEEKS_STR="$*"
else
  WEEKS_STR=$(python3 -c "
from datetime import date, timedelta
out=[]
for off in [3,2,1,0]:
    d = date.today() - timedelta(weeks=off)
    y, w, _ = d.isocalendar()
    out.append(f'{y}-W{w:02d}')
print(' '.join(out))")
fi
echo "→ 갱신 대상: $WEEKS_STR"

# ── 2. GA4 추출 + 베이크 + 마지막 갱신일 갱신 ───────────────
export WEEKS="$WEEKS_STR"
GOOGLE_APPLICATION_CREDENTIALS="/Users/jangmyeongseong/Desktop/claude code/clauide-mcp-c1d375c27ae7.json" \
python3 << 'PYEOF'
import os, re, json
from datetime import date, timedelta
from pathlib import Path
from google.analytics.data_v1beta import BetaAnalyticsDataClient
from google.analytics.data_v1beta.types import (
    RunReportRequest, Dimension, Metric, DateRange, FilterExpression, Filter, OrderBy
)

RECRUIT_PROP = 'properties/525199871'
BLOG_PROP    = 'properties/529085962'
WEEKS = os.environ['WEEKS'].split()
c = BetaAnalyticsDataClient()
MT = Filter.StringFilter.MatchType

def week_range(year, week):
    jan4 = date(year, 1, 4)
    s = jan4 - timedelta(days=jan4.isoweekday()-1) + timedelta(weeks=week-1)
    return s.isoformat(), (s + timedelta(days=6)).isoformat()

def totals(prop, s, e):
    r = c.run_report(RunReportRequest(
        property=prop, date_ranges=[DateRange(start_date=s, end_date=e)],
        metrics=[Metric(name=m) for m in ['activeUsers','sessions','screenPageViews','newUsers']]))
    if not r.rows: return {'users':0,'sessions':0,'pageviews':0,'newUsers':0}
    v = r.rows[0].metric_values
    return {'users':int(v[0].value),'sessions':int(v[1].value),'pageviews':int(v[2].value),'newUsers':int(v[3].value)}

def pv(prop, s, e, value, match):
    f = FilterExpression(filter=Filter(field_name='pagePath',
        string_filter=Filter.StringFilter(value=value, match_type=match)))
    r = c.run_report(RunReportRequest(
        property=prop, date_ranges=[DateRange(start_date=s, end_date=e)],
        metrics=[Metric(name='screenPageViews')], dimension_filter=f))
    return int(r.rows[0].metric_values[0].value) if r.rows else 0

def blog_eng(s, e):
    """블로그 전체 userEngagementDuration 합계 (초)"""
    r = c.run_report(RunReportRequest(
        property=BLOG_PROP, date_ranges=[DateRange(start_date=s, end_date=e)],
        metrics=[Metric(name='userEngagementDuration')]))
    return int(float(r.rows[0].metric_values[0].value)) if r.rows else 0

def blog_channels(s, e):
    r = c.run_report(RunReportRequest(
        property=BLOG_PROP, date_ranges=[DateRange(start_date=s, end_date=e)],
        dimensions=[Dimension(name='sessionDefaultChannelGroup')],
        metrics=[Metric(name='sessions')]))
    out = {'organic':0,'social':0,'direct':0,'referral':0,'other':0}
    for row in r.rows:
        ch = row.dimension_values[0].value
        sess = int(row.metric_values[0].value)
        if ch == 'Organic Search': out['organic'] += sess
        elif ch == 'Direct':       out['direct']  += sess
        elif ch == 'Referral':     out['referral']+= sess
        elif 'Social' in ch:       out['social']  += sess
        else:                       out['other']   += sess
    return out

def blog_posts(s, e, limit=20):
    r = c.run_report(RunReportRequest(
        property=BLOG_PROP, date_ranges=[DateRange(start_date=s, end_date=e)],
        dimensions=[Dimension(name='pagePath'), Dimension(name='pageTitle')],
        metrics=[Metric(name='screenPageViews'), Metric(name='userEngagementDuration')],
        order_bys=[OrderBy(metric=OrderBy.MetricOrderBy(metric_name='screenPageViews'), desc=True)],
        limit=limit))
    return [{
        'title': row.dimension_values[1].value,
        'path':  row.dimension_values[0].value,
        'pageviews': int(row.metric_values[0].value),
        'engTime':   int(float(row.metric_values[1].value)),
        'ctaClicks': 0,
    } for row in r.rows]

new_data = {}
for wk in WEEKS:
    y, w = wk.split('-W'); s, e = week_range(int(y), int(w))
    print(f'  {wk}  {s} ~ {e}')
    # 채용
    d = totals(RECRUIT_PROP, s, e)
    d['recruit_pv'] = pv(RECRUIT_PROP, s, e, '/recruit',     MT.BEGINS_WITH)
    d['detail_pv']  = pv(RECRUIT_PROP, s, e, '/job_posting', MT.BEGINS_WITH)
    d['apply_pv']   = pv(RECRUIT_PROP, s, e, '/apply',       MT.ENDS_WITH)
    d['confirm_pv'] = pv(RECRUIT_PROP, s, e, '/confirm',     MT.ENDS_WITH)
    # 블로그
    bt = totals(BLOG_PROP, s, e)
    d['blog_pageviews'] = bt['pageviews']
    d['blog_users']     = bt['users']
    d['blog_engTime']   = blog_eng(s, e)
    d['blog_ctaClicks'] = 0
    d['blog_channels']  = blog_channels(s, e)
    d['blog_posts']     = blog_posts(s, e)
    new_data[wk] = d
    print(f'    채용 users={d["users"]} confirm={d["confirm_pv"]} | 블로그 PV={d["blog_pageviews"]} users={d["blog_users"]}')

p = Path('index.html')
src = p.read_text()
m = re.search(r'(const __BAKED_DATA__ = )(\{.*?\});', src, re.DOTALL)
baked = json.loads(m.group(2))
for wk, fields in new_data.items():
    if wk not in baked: baked[wk] = {'posts': []}
    baked[wk].update(fields)
src = src[:m.start(2)] + json.dumps(baked, ensure_ascii=False) + src[m.end(2):]

today = date.today()
src = re.sub(r'const __LAST_UPDATED__ = "[^"]*";',
             f'const __LAST_UPDATED__ = "{today.year}년 {today.month}월 {today.day}일";', src)
p.write_text(src)
print(f'→ {len(new_data)}주 머지 완료')
PYEOF

# ── 3. 커밋·푸시 ──────────────────────────────────────────
if git diff --quiet index.html; then
  echo "→ 변경 없음, 종료"
  exit 0
fi
git add index.html
git commit -m "Refresh recruit + blog GA4 data ($WEEKS_STR) — $(date +%Y-%m-%d)"
git push origin main
echo "✅ 푸시 완료. 1~2분 후 https://beodle.github.io/athome-recruit-dashboard/ 반영"
