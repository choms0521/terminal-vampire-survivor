# Phase 0 — 렌더 처리량 스파이크 (feasibility gate)

작성일: 2026-06-23
대상 레포: `terminal-vampire-survivor`
상위 문서: `docs/plan/2026-06-23/work-plan-v1.md` (마스터 계획서 v1) §3.2 / §3.3 / §3.6 / §4 / §10
상태: **상세개발 계획 (Phase 0)** — 본 문서의 측정 결과가 하류 phase의 핵심 수치를 규정한다.

> Phase 0는 타당성의 관문이다. 이 문서는 측정 방법론과 측정표 양식, 작동점 결정 절차를 정의한다.
> 측정표의 결과 수치는 이 문서에서 미리 못 박지 않는다. 실제 터미널에서 하네스를 돌려 채워 넣고,
> 그렇게 채워진 표로부터 결정 규칙을 적용해 `(N, TPS, 뷰포트)` 작동점을 확정한다.

---

## 0. 핵심 원칙 (이 문서를 읽는 법)

이 문서는 다음 세 가지를 산출한다. 이 셋이 Phase 0의 전부다.

1. **스트레스 하네스 스크립트 설계** — 실제 터미널에서 "이동 글리프 N개"를 지속 렌더하며
   처리량을 측정하는 도구. 측정 변수(렌더 방식, 색 변경 빈도, 뷰포트, N)를 토글한다.
2. **빈 측정 매트릭스** — 측정 변수를 축으로, 종속 변수(지속 FPS, 프레임당 출력 바이트,
   프레임 시간 p50/p95)를 열로 가지는 **빈 양식**. 측정 Day에 셀을 채운다.
3. **작동점 결정 규칙** — 채워진 표로부터 `(N=엔티티 캡, TPS, 뷰포트 W×H)`를 도출하는
   **규칙**. 결과 수치가 아니라 규칙이 본 문서의 산출물이다. 도출된 작동점은
   `config/tuning.toml`의 초기값으로 확정된다.

> **측정값은 하류의 placeholder다.** 마스터 §3.3에 따라 병목은 파이썬 연산이 아니라
> 터미널 I/O 처리량(프레임당 바이트)일 공산이 크다. 따라서 본 문서의 1차 측정 지표는
> FPS가 아니라 **프레임당 출력 바이트**이며, FPS는 그 결과다.

---

## 1. 개요

### Goal

`blessed`로 위치를 지정해 그리는 **이동 글리프를 한 틱에 몇 개까지 지속(sustained) 렌더 가능한지**
실제 터미널에서 측정하고, 그 결과로 `(엔티티 캡 N, 시뮬레이션 TPS, 뷰포트 W×H)` 작동점을
숫자로 확정한다. 부드러운 동작이 불가하다고 판정되면 fallback 경로(뷰포트/엔티티 축소,
접근 재검토)를 가동한다.

### Scope

**In scope**

- 스트레스 하네스 스크립트(`bench/render_spike.py` 가칭) 설계 및 구현 명세.
- full-frame 재출력 vs diff 렌더(바뀐 셀만 출력) 처리량 비교.
- 트루컬러 escape 시퀀스 변경 빈도(색 변경 빈도)가 처리량에 주는 영향 측정.
- 뷰포트 크기 변화에 따른 처리량 측정.
- 측정 매트릭스 양식 정의 및 채움.
- 측정 환경 변수(로컬 vs SSH, 에뮬레이터 종류) 기록 및 재현 절차.
- 작동점 결정 규칙 적용 → `config/tuning.toml` 초기값 확정.
- 헤드리스 `--selftest`(로직 스모크, exit 0)와 실제 TTY 측정 모드의 분리.

**Out of scope**

- 실제 게임 로직(시뮬레이션 틱 파이프라인 §5.4, 무기/적/충돌). Phase 1 이후.
- 입력 처리(이동 키맵). 하네스의 글리프 이동은 스크립트가 결정적으로 구동한다.
- `config.py`의 완전한 스키마 검증 로직(Phase 1). 본 phase는 `tuning.toml`에
  측정으로 확정된 키를 **기입**하는 데까지만 다룬다.
- 종횡비 보정의 게임플레이 적용(§3.1). 측정은 셀 단위로 수행한다.

### Key Deliverables

| # | 산출물 | 형식 | 위치(가칭) |
| --- | --- | --- | --- |
| K1 | 스트레스 하네스 스크립트 | Python 단일 파일 | `bench/render_spike.py` |
| K2 | 빈 측정 매트릭스 양식 | Markdown 표 / CSV | 본 문서 §2 Day 2, 캡처는 `bench/results/` |
| K3 | 채워진 측정표 + 환경 메타 | CSV + Markdown 요약 | `bench/results/<host>-<emulator>.csv` |
| K4 | 작동점 결정 기록 | `tuning.toml` 초기값 + 결정 근거 메모 | `config/tuning.toml`, `bench/results/decision.md` |
| K5 | 헤드리스 selftest 스모크 | 하네스 `--selftest` 경로 | `bench/render_spike.py --selftest` |

### Dependencies

- **Entry**: Phase 0는 프로젝트 시작점이다. 외부 phase 의존 없음.
- **런타임**: Python 3.11+ (표준 `tomllib`, `time.monotonic`, `time.perf_counter`).
- **라이브러리**: `blessed>=1.20` (`requirements.txt` 기재됨, 미설치 상태 → Day 0 설치).
- **측정 환경**: 실제 TTY(터미널 에뮬레이터). 측정은 파이프/리다이렉트 불가(§아키텍처 노트 4).

### Effort

| Day | 내용 | 예상 소요 |
| --- | --- | --- |
| Day 0 | 환경 셋업 · 하네스 골격 · selftest 분리 | 0.5일 |
| Day 1 | full-frame / diff 렌더 / 색 변경 토글 구현 · 계측 코드 | 1일 |
| Day 2 | 측정 매트릭스 양식 확정 · 측정 실행 · 표 채움 | 1일 |
| Day 3 | 작동점 결정 규칙 적용 · `tuning.toml` 기입 · fallback 판정 | 0.5일 |

> 소규모 스파이크이므로 2.5~3일 규모. Day 0/Day 3은 반일 단위.

---

## 2. Day-by-Day Work Package

### Day 0 — 환경 셋업 · 하네스 골격 · selftest 분리

**목표**: `blessed`를 설치하고, 측정 모드와 헤드리스 selftest 모드가 분리된 하네스 골격을 세운다.

**산출물**

- `bench/render_spike.py` 골격: argparse 인자(`--glyphs N`, `--mode full|diff`,
  `--color-freq F`, `--viewport WxH`, `--duration S`, `--target-fps T`, `--selftest`).
- `--selftest` 경로: blessed의 실제 출력 없이(또는 `term` 없이) 프레임 합성/diff 계산
  로직만 돌려 자기검사하고 exit 0. CI/헤드리스 안전.
- 실제 TTY 측정 경로: `term.fullscreen()` + `term.hidden_cursor()` 컨텍스트 진입.

**OMC 위임**: `executor` (model=sonnet) — 골격/argparse/모드 분기 구현.

**예상 소요**: 0.5일

**기술 노트**

- `blessed`는 출력이 TTY가 아니면(파이프/리다이렉트) escape 시퀀스를 떨군다. 따라서
  타이밍 측정은 반드시 실제 TTY에서, selftest는 TTY 없이 로직만. 두 경로를 코드에서 분리한다.
- 글리프 이동 모델: 각 글리프는 매 프레임 약 1셀씩 결정적으로 이동(난수 시드 고정,
  `random.Random(seed)` 주입). 화면 경계에서 반사. 이렇게 해야 diff 렌더의 "바뀐 셀 수"가
  실제 게임의 이동 패턴을 대표한다.

**측정 가능한 종료 조건**

- `python bench/render_spike.py --selftest` → **exit code 0** (`echo $?` == 0).
- `python bench/render_spike.py --selftest | cat` (파이프) 에서도 예외 없이 **exit code 0**.
- `python bench/render_spike.py --help` 가 `--glyphs --mode --color-freq --viewport
  --duration --target-fps --selftest` 인자를 모두 노출 → `grep -E -- '--glyphs.*--mode'`
  대신 `--help` 출력에 각 플래그 문자열 7개가 **모두 존재**(7/7).
- `grep -E 'def .*selftest' bench/render_spike.py` 매치 **1건 이상**.

---

### Day 1 — 렌더 방식·색 변경 토글 구현 · 계측 코드

**목표**: full-frame 재출력과 diff 렌더 두 방식, 색 변경 빈도 토글, 프레임당 바이트·프레임
시간 계측을 구현한다.

**산출물**

- `render_full(term, buf)`: 전체 뷰포트 버퍼를 `term.home` 후 한 문자열로 1회 출력
  (전체 clear 금지, 고정폭 패딩 — 마스터 §3.6).
- `render_diff(term, prev, cur)`: 이전/현재 셀 버퍼를 비교해 바뀐 셀만 커서 이동 후 출력.
- 색 변경 빈도 토글: `--color-freq F` (예: 0.0=단색, 0.5=절반 글리프가 매 프레임 색 변경,
  1.0=전 글리프 매 프레임 트루컬러 escape). escape 시퀀스 비용 영향 측정용.
- 계측: 매 프레임 **출력 문자열 길이(바이트)** 를 `len(frame_str.encode())`로 집계,
  프레임 시간을 `perf_counter`로 기록. duration 동안 누적 후 p50/p95/평균/지속 FPS 산출.

**OMC 위임**: `executor` (model=sonnet) — 렌더 두 경로 + 계측. 계측 정확성은 Day 2에서
`verifier`가 점검.

**예상 소요**: 1일

**기술 노트**

- **1차 지표는 프레임당 바이트**다(마스터 §3.3: 병목은 한 프레임에 쓸 수 있는 바이트량).
  FPS는 종속 결과로 함께 기록한다.
- diff 렌더는 밀도 의존적이다. 바뀐 셀 수 ≈ 2N(글리프가 이전 칸을 비우고 새 칸을 채움)인
  반면 full-frame은 항상 뷰포트 W×H 셀. 따라서 **N이 W×H보다 훨씬 작을 때 diff가 크게
  유리**하고, 밀도가 오르면 full-frame 쪽으로 수렴한다. 이 관계를 측정으로 확인한다.
- 색 변경은 셀마다 트루컬러 SGR escape(`\x1b[38;2;r;g;bm`, 약 19바이트)를 더한다.
  같은 색을 연속 출력할 때는 escape를 생략(직전 색 캐싱)해 비용을 줄이는 경로도 측정 토글에 둔다.
- 지속(sustained) 측정: 단발 피크가 아니라 고정 duration(기본 10초) 동안의 분포를 본다.

**측정 가능한 종료 조건**

- `render_full`과 `render_diff` 두 함수가 **모두 존재** → `grep -E 'def render_(full|diff)'
  bench/render_spike.py` 매치 **2건**.
- `python bench/render_spike.py --glyphs 100 --mode full --duration 3` 실행 시
  stdout/결과 파일에 `bytes_per_frame`, `fps_sustained`, `frame_ms_p50`, `frame_ms_p95`
  4개 지표가 **모두 출력**(4/4 키 존재, `grep -E 'bytes_per_frame|fps_sustained|frame_ms_p(50|95)'`).
- 동일 N·duration으로 `--mode full`과 `--mode diff`를 각각 실행했을 때, 결과의
  `bytes_per_frame` 값이 **서로 다르게 산출**된다(두 경로가 실제로 다른 출력을 냄;
  diff 모드의 N=낮음에서 full 대비 `bytes_per_frame`이 더 작음을 1건 이상 관측).
- `--color-freq 0.0`과 `--color-freq 1.0` 실행 결과의 `bytes_per_frame`이 **단조 증가**
  (1.0 ≥ 0.0) → 측정 1쌍에서 확인.

---

### Day 2 — 측정 매트릭스 · 측정 실행 · 표 채움

**목표**: 측정 변수 격자(N × 렌더 방식 × 색 변경 빈도 × 뷰포트)를 정의하고, 재현 가능한
명령으로 측정을 실행해 빈 표를 채운다. 측정 환경 메타를 함께 기록한다.

**산출물**

- 측정 매트릭스 양식(§아래 표). 빈 셀을 측정으로 채운 `bench/results/<host>-<emulator>.csv`.
- 측정 환경 메타: 호스트, 터미널 에뮬레이터/버전, 로컬 vs SSH, 컬럼×행, `$TERM`,
  `COLORTERM`, 측정 일시.
- 재현 절차(아래 "측정 절차").

**OMC 위임**: `scientist` (측정 실행·데이터 수집·표 채움) + `verifier` (계측 정확성·재현성 점검).

**예상 소요**: 1일

**기술 노트**

- 측정은 **여러 환경**에서 반복한다. 마스터 §3.3은 SSH/원격에서 처리량이 크게 달라질 수
  있음을 지적한다. 최소: (a) 로컬 터미널 1종, (b) SSH 원격 1종. 가능하면 에뮬레이터 2종 이상.
- 각 셀은 고정 duration(기본 10초) 측정. 워밍업 1초는 통계에서 제외.
- 노이즈 통제: 측정 중 다른 부하 최소화, 같은 창 크기 고정, 백그라운드 로깅 비활성.

#### 측정 매트릭스 양식 (빈 템플릿 — Day 2에 채움)

독립 변수(축): `N` ∈ {50, 100, 200, 400, 800}, `mode` ∈ {full, diff},
`color-freq` ∈ {0.0, 0.5, 1.0}, `viewport` ∈ {80x24, 100x30, 120x40}.
종속 변수(열): 지속 FPS, 프레임당 바이트, 프레임 시간 p50, p95.

| env | viewport | mode | color-freq | N | fps_sustained | bytes_per_frame | frame_ms_p50 | frame_ms_p95 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| (측정) | 100x30 | full | 0.0 | 50 |  |  |  |  |
| (측정) | 100x30 | full | 0.0 | 100 |  |  |  |  |
| (측정) | 100x30 | full | 0.0 | 200 |  |  |  |  |
| (측정) | 100x30 | full | 0.0 | 400 |  |  |  |  |
| (측정) | 100x30 | full | 0.0 | 800 |  |  |  |  |
| (측정) | 100x30 | diff | 0.0 | 50 |  |  |  |  |
| (측정) | 100x30 | diff | 0.0 | 100 |  |  |  |  |
| (측정) | 100x30 | diff | 0.0 | 200 |  |  |  |  |
| (측정) | 100x30 | diff | 0.0 | 400 |  |  |  |  |
| (측정) | 100x30 | diff | 0.0 | 800 |  |  |  |  |
| (측정) | 100x30 | full | 1.0 | 200 |  |  |  |  |
| (측정) | 100x30 | diff | 1.0 | 200 |  |  |  |  |
| (측정) | 80x24 | diff | 0.0 | 200 |  |  |  |  |
| (측정) | 120x40 | diff | 0.0 | 200 |  |  |  |  |
| ... | ... | ... | ... | ... |  |  |  |  |

> 위 표는 양식이다. 전체 격자(5 N × 2 mode × 3 color-freq × 3 viewport = 90행)를 환경마다
> 반복하면 과대하므로, 측정 절차는 **1차 전수 축소격자**(색·뷰포트 고정, N×mode 스윕)로
> 곡선을 잡고, 변곡 구간만 색·뷰포트를 추가 스윕한다. CSV에는 전 측정 행을 기록한다.

#### 측정 절차 (재현 가능한 명령)

```
# 0) 설치 (Day 0)
python -m pip install -r requirements.txt        # blessed>=1.20

# 1) 헤드리스 스모크 (TTY 불필요, CI 안전)
python bench/render_spike.py --selftest ; echo "exit=$?"

# 2) 1차 스윕: full vs diff, 단색, 100x30, N 스윕 (실제 TTY에서)
for N in 50 100 200 400 800 ; do
  for M in full diff ; do
    python bench/render_spike.py --glyphs $N --mode $M \
      --color-freq 0.0 --viewport 100x30 --duration 10 \
      --out bench/results/$(hostname)-$TERM.csv
  done
done

# 3) 색 변경 영향: 변곡 N에서 color-freq 0.0/0.5/1.0
python bench/render_spike.py --glyphs 200 --mode diff --color-freq 0.5 ...

# 4) 뷰포트 영향: 변곡 N에서 80x24 / 100x30 / 120x40
python bench/render_spike.py --glyphs 200 --mode diff --viewport 80x24 ...

# 5) 원격 반복: 동일 명령을 SSH 세션에서 재실행 → 별도 CSV
```

**측정 가능한 종료 조건**

- `bench/results/` 아래 측정 CSV가 **2개 이상**(로컬 1 + SSH/원격 1) 존재 →
  `ls bench/results/*.csv | wc -l` ≥ 2.
- 1차 축소격자(5 N × 2 mode = 10행)가 각 환경에서 **빈 셀 0건** →
  CSV에서 `fps_sustained`, `bytes_per_frame`, `frame_ms_p50`, `frame_ms_p95` 열에
  공란/NaN 행 **0건**(`grep -c ',,' bench/results/*.csv` == 0).
- 각 CSV에 환경 메타 헤더(host, emulator, term, colorterm, mode=local|ssh, cols×rows,
  timestamp)가 **모두 기재** → 메타 7개 필드 존재.
- N에 대한 `bytes_per_frame`이 full 모드에서 **단조 비감소** 곡선으로 관측(측정 일관성 검사).

---

### Day 3 — 작동점 결정 · `tuning.toml` 기입 · fallback 판정

**목표**: 채워진 측정표에 결정 규칙을 적용해 `(N, TPS, 뷰포트)`를 도출하고
`config/tuning.toml` 초기값으로 기입한다. 불가 판정 시 fallback 경로를 가동·기록한다.

**산출물**

- `config/tuning.toml`: `sim_tps`, `viewport_w`, `viewport_h`, `entity_cap`,
  `render_mode`, `poll_timeout`, `max_catchup`, `aspect_x_compress` 등 키 기입.
- `bench/results/decision.md`: 결정 규칙 적용 과정과 채택 근거, fallback 판정 결과.

**OMC 위임**: `scientist` (표→작동점 도출) + `critic` (결정 규칙 일관성·fallback 타당성 검토).

**예상 소요**: 0.5일

**기술 노트**

- 결정 규칙은 §아키텍처 노트의 "작동점 결정 절차"를 그대로 적용한다.
- TPS는 측정된 프레임 시간 분포로부터, 렌더가 시뮬레이션을 따라잡을 수 있는 상한으로 정한다.
- 목표 FPS 하한(아래 §아키텍처 노트에서 후보 제시)은 **측정 후 합의 대상**이다. Day 3에서
  실제 분포를 보고 확정한다.

**측정 가능한 종료 조건**

- `config/tuning.toml`에 `sim_tps`, `viewport_w`, `viewport_h`, `entity_cap`,
  `render_mode` 키가 **모두 존재** →
  `python -c "import tomllib;d=tomllib.load(open('config/tuning.toml','rb'));
  assert all(k in d for k in ['sim_tps','viewport_w','viewport_h','entity_cap','render_mode'])"`
  → **exit code 0**.
- 기입된 `entity_cap` 값이 측정표에서 "목표 FPS 하한을 만족하는 최대 N" 규칙으로 도출된
  값과 **일치**(decision.md에 N 도출 근거 행 인용 1건 이상).
- `bench/results/decision.md`에 fallback 판정 결과("작동점 확정" 또는 "축소 경로 가동:
  ...")가 **명시** → `grep -E '작동점 확정|축소 경로|접근 재검토' bench/results/decision.md`
  매치 **1건 이상**.

---

## 3. 아키텍처·기술 노트 (이 phase가 구체화하는 마스터 절)

### 3.A §3.3 렌더 처리량 — 1차 지표는 프레임당 바이트

마스터 §3.3은 병목이 파이썬 연산이 아니라 터미널 I/O 처리량(한 프레임에 쓸 수 있는
바이트량)일 공산이 크다고 본다. 따라서 하네스의 **1차 측정 지표는 프레임당 출력 바이트**다.
글리프 수 N이 이 바이트량을 좌우하고, 바이트량이 지속 가능 FPS를 좌우한다. 완화 기법(뷰포트
축소·엔티티 캡·diff 렌더·색 변경 최소화)의 효과를 모두 "프레임당 바이트 절감"으로 환산해 비교한다.

### 3.B §3.6 깜빡임 없는 렌더 — 측정 대상 렌더 규약

- 전체 화면 clear 금지. `term.home` 후 프레임 문자열을 **한 번에** 출력.
- 짧은 줄은 고정폭 패딩으로 잔상 제거.
- diff 렌더 시에는 바뀐 셀로 **커서 이동(`term.move_yx`)** 후 그 셀만 출력.

하네스는 이 규약을 그대로 구현해 측정한다. 즉 측정값이 곧 실제 게임 렌더 경로의 처리량을 대표한다.

### 3.C §3.2 카메라·뷰포트·컬링 — 측정 변수로서의 뷰포트

게임은 가시 영역 안의 엔티티만 렌더한다(컬링). Phase 0에서는 컬링 로직 자체가 아니라
**뷰포트 크기**를 측정 변수로 둔다. full-frame은 항상 뷰포트 W×H 셀을 출력하므로 뷰포트가
처리량 상한을 직접 규정한다. 측정으로 "어느 뷰포트에서 어느 N까지 버티는가"를 본다.

### 3.D §4 게임 루프 시간 모델 — 측정이 TPS를 규정

마스터 §4는 fixed timestep + accumulator로 시뮬레이션 TPS와 렌더를 분리한다. Phase 0의
프레임 시간 분포 측정이 **렌더가 따라갈 수 있는 TPS 상한**을 알려준다. 하네스는 게임 루프
전체가 아니라 "렌더 한 프레임"의 시간만 측정하되, 그 분포로부터 작동점 TPS를 역산한다.

### 작동점 결정 절차 (채워진 표 → `(N, TPS, 뷰포트)`)

1. **목표 FPS 하한 후보 제시 (측정 후 합의 대상).**
   터미널 실시간 게임 체감 기준으로 **15~30 FPS 구간**을 후보로 둔다. 마스터 §1 비-목표는
   60 FPS 보장을 명시적으로 포기하고 "충분히 부드러운" 체감을 목표한다. 잠정 후보 하한:
   **20 FPS** (= 프레임 시간 p95 ≤ 50ms). 이 하한 자체는 Day 3에서 실제 분포를 보고 확정한다.
   **이 수치는 결론이 아니라 측정 후 합의 대상이다.**

2. **엔티티 캡 N 도출.**
   채택 렌더 방식(아래 4번)에서, 목표 FPS 하한을 **지속(p95 기준) 만족하는 최대 N**을
   엔티티 캡으로 채택한다. 안전 마진(예: 도출 N의 0.7~0.8배)을 둘지 여부는 decision.md에 기록.

3. **뷰포트 선택.**
   목표 FPS 하한을 만족하면서 마스터 §D3(최소 지원 터미널 크기, 미정)과 정합하는 뷰포트를
   고른다. 큰 뷰포트가 체감(난장·가독성)에 유리하나 처리량을 깎으므로 trade-off를 기록.

4. **렌더 방식 채택.**
   목표 N·뷰포트에서 diff와 full의 프레임당 바이트를 비교해 더 적은 쪽을 채택한다.
   diff 렌더는 N ≪ (W×H)에서 크게 유리하고 밀도가 오르면 full로 수렴하므로, **채택 N 근방의
   밀도**에서 비교해 결정한다(낮은 N에서 diff가 좋아 보여도 캡 근방에서 역전되면 의미 없음).

5. **TPS 도출.**
   채택 작동점의 프레임 시간 p50/p95로부터 렌더가 따라갈 수 있는 상한 TPS를 정한다.
   시뮬레이션 TPS는 렌더 FPS와 분리되나(§4), 렌더가 장기적으로 따라잡지 못하면 accumulator가
   폭주하므로 **렌더 지속 처리량을 넘지 않게** 잡는다. 마스터 §4 잠정 가정 15~20 TPS를
   측정 분포와 대조해 확정.

6. **`tuning.toml` 기입.**
   도출한 `(entity_cap, viewport_w, viewport_h, sim_tps, render_mode)`를 초기값으로 기입.

7. **fallback 판정.**
   목표 FPS 하한을 만족하는 N이 "화면을 뒤덮는 손맛"(마스터 §2.1, §2.4)에 필요한 최소 밀도에
   미달하면 아래 fallback 경로를 가동한다.

### Fallback 경로 (불가 판정 시 — Exit Gate 포함)

| 트리거 | 1차 대응 | 2차 대응 |
| --- | --- | --- |
| 채택 N이 너무 작아 난장 체감 불가 | 뷰포트 축소(같은 N에서 FPS 상승) + diff 렌더 강제 | 엔티티 캡 유지하되 글리프 밀집 연출(겹침 우선순위 §3.5)로 밀도감 보완 |
| 어떤 뷰포트에서도 목표 FPS 하한 미달 | 목표 FPS 하한 재합의(20→15 등), 색 변경 최소화 강제 | 시뮬레이션 TPS 하향 + 렌더 스킵 허용(§4 accumulator 따라잡기) |
| SSH/원격에서만 붕괴 | 원격은 뷰포트/색 축소 프로파일 별도 제공 | 원격 미지원으로 범위 축소(로컬 우선) |
| 전 구간에서 부드러움 불가 | **접근 재검토** — 셀 단위 부분 갱신 외 대안(스크롤 영역, 저빈도 렌더) 탐색 | 마스터 계획 §10 Phase 0 "설계 축소 또는 접근 재검토" 분기로 회귀 |

---

## 4. Critical Code Specs (의사 Python)

> 하네스의 핵심만. helper/util은 생략한다. blessed 의존은 측정 경로에만 두고,
> 프레임 합성·diff 계산은 blessed 비의존 순수 로직으로 분리해 `--selftest`에서 재사용한다.

```python
# bench/render_spike.py — 스트레스 하네스 (Phase 0)
# 측정 경로만 blessed에 의존. 프레임 합성/diff는 순수 로직(selftest 재사용).

from __future__ import annotations
import random, time, argparse
from dataclasses import dataclass

# --- 불변 측정 설정 (config 주입 원칙과 동일: 읽기 전용으로 주입) ---
@dataclass(frozen=True)
class BenchConfig:
    glyphs: int          # N: 이동 글리프 수
    mode: str            # "full" | "diff"
    color_freq: float    # 0.0..1.0, 매 프레임 색 변경 비율
    vw: int              # viewport width (cols)
    vh: int              # viewport height (rows)
    duration: float      # sustained 측정 시간(초)
    seed: int            # 결정적 글리프 이동

# --- 가변 글리프 버퍼: 측정 루프 안에서만 제자리 갱신(§6 경계) ---
class Glyphs:
    # parallel arrays: xs, ys, dxs, dys, colors. sim step 밖으로 누출 금지.
    def __init__(self, cfg: BenchConfig, rng: random.Random): ...
    def advance(self, cfg: BenchConfig, rng: random.Random) -> None:
        # 매 프레임 약 1셀 이동, 경계 반사. 제자리 갱신.
        ...

# --- 순수 프레임 합성: blessed 비의존 → selftest 재사용 ---
def compose_cells(cfg: BenchConfig, g: Glyphs) -> list[list[tuple[str, tuple|None]]]:
    # 뷰포트 W×H 셀 그리드 반환. 각 셀 = (char, rgb_or_None).
    # 빈 셀은 공백 + None. 겹침은 그리기 우선순위로 해소(여기선 마지막 글리프 우선).
    ...

# --- full-frame 출력 문자열 합성 (순수): term.home 후 1회 출력할 본문 ---
def build_full_frame(term, cells, last_color_cache) -> str:
    # 행 단위로 고정폭 패딩(잔상 제거, §3.6). 색은 직전 색과 다를 때만 SGR escape.
    # 반환 문자열 길이가 곧 '프레임당 바이트'의 핵심.
    ...

# --- diff 출력 문자열 합성 (순수): 바뀐 셀만 커서 이동 후 출력 ---
def build_diff_frame(term, prev_cells, cur_cells) -> str:
    # prev != cur 인 셀만 term.move_yx(y,x) + char(+color). N ≪ W×H일 때 바이트 급감.
    # 바뀐 셀 수 ≈ 2N(이전 칸 비우고 새 칸 채움) vs full의 W×H.
    ...

def measure(term, cfg: BenchConfig) -> dict:
    rng = random.Random(cfg.seed)        # 결정적 주입(§13)
    g = Glyphs(cfg, rng)
    prev_cells = None
    frame_ms: list[float] = []
    frame_bytes: list[int] = []
    warmup_until = time.monotonic() + 1.0   # 워밍업 1초 제외
    end = time.monotonic() + cfg.duration + 1.0

    with term.fullscreen(), term.hidden_cursor():
        while time.monotonic() < end:
            t0 = time.perf_counter()
            g.advance(cfg, rng)                      # 가변 제자리 갱신
            cur = compose_cells(cfg, g)              # 순수 합성
            if cfg.mode == "full":
                frame = term.home + build_full_frame(term, cur, ...)
            else:
                frame = build_diff_frame(term, prev_cells, cur) if prev_cells \
                        else term.home + build_full_frame(term, cur, ...)
            # 단일 write — 1차 지표는 이 문자열의 인코딩 바이트 길이
            print(frame, end="", flush=True)
            prev_cells = cur
            dt = time.perf_counter() - t0
            if time.monotonic() >= warmup_until:
                frame_ms.append(dt * 1000.0)
                frame_bytes.append(len(frame.encode("utf-8")))
            # 목표 프레임 간격까지 sleep(과도 busy-spin 방지)은 측정 모드에선 생략 가능

    return summarize(frame_ms, frame_bytes, cfg)     # p50/p95/avg, fps_sustained, bytes/frame

def summarize(frame_ms, frame_bytes, cfg) -> dict:
    # fps_sustained = 1000 / mean(frame_ms) 등. p50/p95 percentile.
    return {
        "env": ..., "viewport": f"{cfg.vw}x{cfg.vh}", "mode": cfg.mode,
        "color_freq": cfg.color_freq, "N": cfg.glyphs,
        "fps_sustained": ..., "bytes_per_frame": ...,
        "frame_ms_p50": ..., "frame_ms_p95": ...,
    }

# --- 헤드리스 selftest: TTY 없이 순수 로직만. timing/처리량 주장 안 함. exit 0. ---
def selftest() -> int:
    cfg = BenchConfig(glyphs=20, mode="diff", color_freq=0.5,
                      vw=40, vh=12, duration=0.0, seed=1)
    rng = random.Random(cfg.seed)
    g = Glyphs(cfg, rng)
    c0 = compose_cells(cfg, g)
    assert len(c0) == cfg.vh and all(len(r) == cfg.vw for r in c0)  # 그리드 형상
    g.advance(cfg, rng)
    c1 = compose_cells(cfg, g)
    # diff 계산이 예외 없이 동작하고, 이동 후 바뀐 셀이 존재
    changed = sum(1 for y in range(cfg.vh) for x in range(cfg.vw) if c0[y][x] != c1[y][x])
    assert changed > 0
    return 0   # CI/헤드리스 안전. 타이밍 측정 없음.

def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--glyphs", type=int, default=100)
    p.add_argument("--mode", choices=["full", "diff"], default="full")
    p.add_argument("--color-freq", type=float, default=0.0)
    p.add_argument("--viewport", default="100x30")     # "WxH"
    p.add_argument("--duration", type=float, default=10.0)
    p.add_argument("--target-fps", type=float, default=20.0)
    p.add_argument("--selftest", action="store_true")
    p.add_argument("--out", default=None)              # CSV append 경로
    args = p.parse_args()
    if args.selftest:
        return selftest()                              # TTY 불필요
    import blessed                                      # 측정 경로에서만 import
    term = blessed.Terminal()
    cfg = parse_cfg(args)
    result = measure(term, cfg)
    emit_csv(result, args.out)                         # 환경 메타 헤더 포함
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
```

설계 의도 요약:

- **두 경로 분리**: `selftest()`는 blessed 없이 순수 로직만 검사하고 exit 0(헤드리스/CI 안전,
  타이밍·처리량 주장 안 함). `measure()`만 실제 TTY에서 처리량을 측정한다. 마스터 §13의
  "selftest exit 0"와 "측정은 실제 TTY 필요"가 충돌하지 않도록 한 분리다.
- **1차 지표 = `len(frame.encode())`**: 마스터 §3.3의 "프레임당 바이트" 병목을 직접 계측.
- **결정적 주입**: `random.Random(seed)`로 글리프 이동을 재현(§13). 측정 반복성 확보.
- **순수/가변 경계(§6)**: `compose_cells`/`build_*_frame`은 순수 합성, `Glyphs.advance`만
  제자리 갱신. 가변 버퍼는 측정 루프 밖으로 누출하지 않는다.

---

## 5. Acceptance Criteria

| # | 기준 | 검증 절차 | 통과 |
| --- | --- | --- | --- |
| A1 | 하네스 헤드리스 selftest가 통과한다 | `python bench/render_spike.py --selftest ; echo $?` → **0** | ☐ |
| A2 | selftest가 파이프에서도 통과(TTY 비의존) | `python bench/render_spike.py --selftest \| cat ; echo $?` → **0** | ☐ |
| A3 | full·diff 두 렌더 함수가 존재 | `grep -E 'def render_(full\|diff)\|def build_(full\|diff)' bench/render_spike.py` 매치 **2건 이상** | ☐ |
| A4 | 측정이 4개 지표를 산출 | 임의 N 실행 결과에 `fps_sustained`·`bytes_per_frame`·`frame_ms_p50`·`frame_ms_p95` **4/4** 존재 | ☐ |
| A5 | 색 변경 빈도 영향이 바이트로 관측 | `--color-freq 1.0`의 `bytes_per_frame` ≥ `--color-freq 0.0` (동일 N·mode·viewport) **1쌍** | ☐ |
| A6 | diff 유리 구간이 관측 | 낮은 N(예: 50)에서 diff의 `bytes_per_frame` < full의 `bytes_per_frame` **1건 이상** | ☐ |
| A7 | 측정표 빈 셀 0건(1차 축소격자) | `grep -c ',,' bench/results/*.csv` → **0** (1차 격자 행 한정) | ☐ |
| A8 | 측정 환경 2종 이상 | `ls bench/results/*.csv \| wc -l` → **2 이상** (로컬 + SSH/원격) | ☐ |
| A9 | 환경 메타 기재 | 각 CSV에 host·emulator·term·colorterm·local\|ssh·cols×rows·timestamp **7/7** | ☐ |
| A10 | `tuning.toml` 작동점 키 기입 | `tomllib.load`로 `sim_tps`·`viewport_w`·`viewport_h`·`entity_cap`·`render_mode` 키 **전부 존재** → exit **0** | ☐ |
| A11 | `entity_cap`이 결정 규칙으로 도출됨 | `decision.md`에 "목표 FPS 하한 만족 최대 N → entity_cap" 도출 근거 행 인용 **1건 이상** | ☐ |
| A12 | fallback 판정 명시 | `grep -E '작동점 확정\|축소 경로\|접근 재검토' bench/results/decision.md` 매치 **1건 이상** | ☐ |

---

## 6. Risks & Mitigations

| 위험 | 가능성 | 영향 | 완화 |
| --- | --- | --- | --- |
| 측정이 단발 피크만 잡아 실제 지속 처리량을 과대평가 | 중 | 높음 | 고정 duration(10초) 측정, 워밍업 1초 제외, p50/p95 보고. 피크 금지 |
| 파이프/리다이렉트로 측정해 escape가 떨어져 무의미한 수치 | 중 | 높음 | 측정은 실제 TTY 강제, selftest만 TTY 비의존. 두 경로 코드 분리 |
| 글리프 이동 모델이 비현실적이라 diff 측정이 왜곡 | 중 | 중 | 매 프레임 약 1셀 이동·경계 반사로 실제 게임 이동 패턴 근사. 시드 고정 |
| 단일 환경만 측정해 SSH/원격 붕괴를 놓침 | 중 | 높음 | 로컬+원격 최소 2환경, 가능하면 에뮬레이터 2종 이상. 환경별 CSV 분리 |
| `bytes_per_frame`을 측정 안 하고 FPS만 봐 병목(§3.3)을 놓침 | 낮음 | 높음 | 1차 지표를 바이트로 명시, `len(frame.encode())` 계측을 종료 조건에 포함 |
| 목표 FPS 하한을 임의로 못 박아 결론이 측정과 무관해짐 | 중 | 중 | 하한은 후보(20 FPS)만 제시·"측정 후 합의 대상" 표기, Day 3 분포로 확정 |
| diff가 낮은 N에서만 유리해 캡 근방에서 역전됨을 못 봄 | 중 | 중 | 채택 N 근방 밀도에서 diff/full 비교(결정 절차 4번), 저밀도 단독 판단 금지 |
| 부드러움 불가 판정인데 fallback 없이 멈춤 | 낮음 | 높음 | Fallback 경로 표를 Exit Gate에 포함, decision.md에 판정 강제 |

---

## 7. Exit Gate — Phase 1로 넘어가기 위한 체크리스트

마스터 §10 Phase 0 Exit("작동점이 숫자로 확정. 불가 판정이면 설계 축소 또는 접근 재검토")의
구체화. 아래가 **모두** 충족되면 Phase 1(코어 루프 수직 슬라이스)로 진입한다.

- [ ] **G1** 하네스 selftest exit 0 — `python bench/render_spike.py --selftest ; echo $?` → 0 (A1, A2).
- [ ] **G2** full·diff·색 변경·뷰포트 토글이 동작하고 4개 지표(`fps_sustained`,
      `bytes_per_frame`, `frame_ms_p50`, `frame_ms_p95`)를 산출 (A3, A4).
- [ ] **G3** 측정표 1차 축소격자가 2개 이상 환경(로컬+원격)에서 빈 셀 0건으로 채워짐 (A7, A8, A9).
- [ ] **G4** 색 변경 빈도·diff 유리 구간이 데이터로 관측됨 (A5, A6).
- [ ] **G5** 작동점 결정 규칙이 적용되어 `(entity_cap, viewport_w, viewport_h, sim_tps,
      render_mode)`가 `config/tuning.toml`에 기입됨 — `tomllib.load` 키 검사 exit 0 (A10, A11).
- [ ] **G6** 목표 FPS 하한이 측정 분포로 확정됨(후보 20 FPS에서 합의값으로) — `decision.md` 기록.
- [ ] **G7** fallback 판정이 명시됨: "작동점 확정"이면 Phase 1 진입 / "축소 경로 가동" 또는
      "접근 재검토"이면 해당 경로(뷰포트·엔티티 축소, 목표 하한 재합의, 원격 프로파일 분리,
      접근 대안 탐색)를 실행하고 그 결과를 다시 G1~G6로 재검증 (A12).

> **불가 판정 처리**: G7이 "접근 재검토"로 귀결되면 Phase 1로 진입하지 않는다. Fallback 경로
> 표(§3 Fallback)의 대응을 적용해 측정을 재실행하고, 축소된 작동점으로 G1~G6를 다시 통과해야
> 한다. 마스터 §10/§12의 Phase 0 게이트 취지 그대로다.
