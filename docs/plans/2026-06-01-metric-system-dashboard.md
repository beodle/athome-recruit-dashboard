# 지표 체계 대시보드 구현 계획 (Implementation Plan)

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 채용 콘텐츠 대시보드(`dashboard-v2.html`)를 "성과 스코어카드 + 근거 3섹션" 지표 체계로 완성하고, 평균 참여 시간을 파이프라인 계산값으로 바꾼다.

**Architecture:** 기존 `dashboard-v2.html`(단일 페이지·범위필터 네이티브)을 베이스로, 맨 위 스코어카드 신설 / 퍼널 제거 / 품질 지표를 GA4 정의에 일치. 데이터 파이프라인(`update.sh`)에 `blog_avg_engagement` 계산을 추가. `__BAKED_DATA__` 마커·export·python 호환 전부 보존.

**Tech Stack:** 순수 HTML/CSS/JS 단일 파일, Chart.js·PapaParse·XLSX(CDN), Python GA4 파이프라인(`update.sh`), 검증은 `node --check`·grep·python 시뮬·브라우저.

**테스트 전략(주의):** 이 프로젝트엔 유닛 테스트 하니스가 없다. 각 태스크의 "검증"은 (a) `node --check`로 JS 구문, (b) `grep`으로 마커/요소 보존, (c) python으로 지표 계산 시뮬, (d) 브라우저 육안 확인으로 갈음한다.

**작업 디렉토리:** `채용-인프라/대시보드/채용성과/`
**대상 파일:** `dashboard-v2.html`, `update.sh`

---

### Task 1: update.sh — 블로그 평균 참여 시간 계산 추가

**Files:** Modify: `update.sh` (블로그 추출 PYEOF 블록)

**Step 1:** `update.sh`의 블로그 totals 처리부에서, 주차별 dict `d`에 다음을 추가한다(이미 `blog_engTime`=userEngagementDuration 합, `blog_users`=활성 사용자가 있으므로 그걸로 계산):
```python
d['blog_avg_engagement'] = round(d['blog_engTime'] / d['blog_users']) if d['blog_users'] else 0  # GA4 '평균 참여 시간'(초) = 총 참여시간 / 활성 사용자
```
(blog_engTime·blog_users 라인 직후에 삽입)

**Step 2 (검증):** 구문 확인 — `python3 -c "import ast; ast.parse(open('update.sh').read().split('PYEOF')[1])"` 또는 `bash -n update.sh`. 기대: 에러 없음.

**Step 3 (dry-run, 선택):** `bash update.sh 2026-W20 2026-W21` 실행 후 `grep -o 'blog_avg_engagement\":[0-9]*' index.html | head`. 기대: 값 존재. (네트워크/크레덴셜 필요 — 불가 시 Step 2로 갈음)

**Step 4 (commit):**
```bash
git add update.sh
git commit -m "feat(pipeline): bake blog_avg_engagement (GA4 평균 참여 시간)"
```

---

### Task 2: dashboard-v2 — 품질 지표를 평균 참여 시간으로 교체

**Files:** Modify: `dashboard-v2.html` (`renderConversion`의 유입 품질 계산)

**Step 1:** 현재 `curAvg=curPV?curET/curPV:0`(조회당 체류)를 GA4 정의로 교체. `blog_avg_engagement`(파이프라인 값)가 있으면 그 주차 평균의 가중평균, 없으면 `blog_engTime ÷ blog_users` 폴백:
```js
function avgEngage(weeks){
  const et=sum(weeks,'blog_engTime'), u=sum(weeks,'blog_users');
  return u ? et/u : 0;   // = GA4 평균 참여 시간(초)
}
```
유입 품질 렌더에서 `curAvg=avgEngage(weeks)`, `prevAvg=R.prevWeeks.length?avgEngage(R.prevWeeks):null`로 바꾸고 분(分):초 표기 유지.

**Step 2 (검증):** `node --check`(스크립트 추출). python 시뮬로 한 주 값이 GA4 정의(et/u)와 일치하는지 확인.

**Step 3 (commit):** `git commit -am "fix(quality): 평균 참여 시간 = 참여시간/활성사용자 (GA4 일치)"`

---

### Task 3: dashboard-v2 — 퍼널 카드 제거

**Files:** Modify: `dashboard-v2.html` (③ 섹션 마크업 + `renderConversion`의 funnel 부분 + `#funnel` 컨테이너)

**Step 1:** ③ 섹션에서 채용 퍼널 카드(`<div class="card pad">…채용 퍼널…<div id="funnel"></div></div>`) 마크업 삭제.
**Step 2:** `renderConversion`에서 funnel 계산·`$('#funnel').innerHTML=…` 블록 삭제. 품질·유입 렌더만 남긴다.
**Step 3 (검증):** `grep -c 'id="funnel"' dashboard-v2.html` → 0. `node --check` 통과. div 균형 재확인.
**Step 4 (commit):** `git commit -am "refactor: 채용 퍼널 카드 제거 (스코프 아웃)"`

---

### Task 4: dashboard-v2 — 성과 스코어카드 마크업 + 렌더

**Files:** Modify: `dashboard-v2.html` (① 인지 섹션 위에 스코어카드 블록 신설 + `renderScorecard()` + `render()`에 호출)

**Step 1 (마크업):** `<main class="wrap">` 바로 안, ① 섹션 앞에 삽입:
```html
<section class="sec" id="secScore" style="margin-top:24px">
  <div class="kpis" id="scoreTiles"></div>
  <div id="scoreInsight" style="margin-top:12px;font-size:13px;color:var(--text-2);line-height:1.6"></div>
</section>
```
(6타일이므로 `.kpis`를 `grid-template-columns:repeat(6,1fr)`로 둘 변형 클래스 `.kpis--6`를 CSS에 추가하거나 기존 4열 유지 후 2줄 허용)

**Step 2 (렌더):** `renderScorecard(R)` 작성 — 타일 6개(팔로워·노출·방문·블로그조회·발행수·평균참여시간), 각 `kpi(label,val,sub,cur,prev,sparkField,spk)` 재사용. 발행수는 캘린더에서 기간 내 항목 수(채널 분해), 평균참여시간은 `avgEngage`. 하단 `scoreInsight`는 변동률 상위 1~2개 자동 문장.
**Step 3:** `render()`에 `renderScorecard(R)` 추가(맨 앞).
**Step 4 (검증):** `node --check`. 브라우저: 타일 6개 + 한 줄 요약 렌더, 범위 토글 시 직전기간 비교 갱신.
**Step 5 (commit):** `git commit -am "feat: 성과 스코어카드(헤드라인 6 + 핵심 변화)"`

---

### Task 5: dashboard-v2 — 섹션 재정렬·라벨 정리

**Files:** Modify: `dashboard-v2.html` (③ 섹션 제목 "전환·품질"→"품질·유입", 유입 출처 카드를 ③ 안으로 정렬)

**Step 1:** ③ `sec-title`을 "품질 · 유입"으로, `sec-desc` "트래픽의 결과 유입처"로. 평균 참여 시간 + 신규 방문 비율 + 유입 출처(도넛·아코디언)만 남도록 순서 정리.
**Step 2 (검증):** `node --check`, 브라우저 3섹션(인지/콘텐츠/품질·유입) 확인.
**Step 3 (commit):** `git commit -am "refactor: 근거 3섹션 정렬(인지/콘텐츠/품질·유입)"`

---

### Task 6: 디자인 원칙 회귀 검수 + 전체 검증

**Step 1:** `grep -c 'font-style:italic' dashboard-v2.html` → 0. 액센트(#FF5D00) 사용처가 버튼·팔로워선·S/A 등급에 한정되는지 확인.
**Step 2:** `node --check`(스크립트 추출) 통과 / 마커 4종·`const __BAKED_DATA__ = {` 1개 보존 grep / div·table 태그 균형 python 카운트.
**Step 3:** 브라우저: 스코어카드 → 인지 → 콘텐츠 → 품질·유입 순, 범위 프리셋(4·8·12·전체·사용자지정·←→), 아코디언, 직전기간 비교 동작.
**Step 4 (commit):** `git commit -am "test: 지표 체계 대시보드 검증 통과"`

---

### Task 7: 승격·배포 (사용자 확인 후)

**Step 1:** 사용자 확인을 받으면 `dashboard-v2.html` → `index.html` 승격(현재 `index.html`은 `index.legacy.html`로 이미 백업). baked 데이터 블록은 현 index.html에서 이식.
**Step 2:** `update.sh`로 최신 데이터 1회 갱신(평균참여 필드 포함) → 커밋 → push.
**Step 3 (검증):** 배포 후 https://beodle.github.io/athome-recruit-dashboard/ 에서 스코어카드·평균참여 시간·퍼널 부재 확인.

---

## 참고
- 설계 근거: `docs/plans/2026-06-01-metric-system-design.md`
- 디자인 원칙(보더·여백 위계, 그레이스케일+제한적 액센트, 한국어 행간·이탤릭 금지)은 모든 신규 요소에 동일 적용.
- LinkedIn 시트 미공유 시 게시물 등급/훅·S/A 요약은 graceful 숨김(설계대로).
