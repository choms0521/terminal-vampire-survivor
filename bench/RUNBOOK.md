# Phase 0 측정 runbook - 렌더 처리량 스파이크

이 문서는 `bench/render_spike.py`로 실제 터미널에서 렌더 처리량을 측정하는
재현 절차다. 측정은 **반드시 실제 TTY(터미널 에뮬레이터)** 에서 실행한다.
파이프/리다이렉트로 실행하면 `blessed`가 escape 시퀀스를 떨궈 측정값이
무의미해지므로, 하네스가 비-TTY 실행을 exit code 2로 거부한다.

상위 문서: `docs/development/2026-06-23/phase-0-render-spike.md`

---

## 0. 사전 준비 (Day 0)

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt      # blessed>=1.20
```

헤드리스 스모크(이 단계는 TTY 불필요, CI 안전):

```bash
.venv/bin/python bench/render_spike.py --selftest      ; echo "exit=$?"   # 0 기대
.venv/bin/python bench/render_spike.py --verify-bytes  ; echo "exit=$?"   # 0 기대
```

`--verify-bytes`는 색 변경 비용 단조성(A5)과 저밀도 diff 우위(A6)를
바이트 수준에서 구축으로 증명한다. 타이밍은 검사하지 않는다.

---

## 1. CLI 인자 요약

| 인자 | 의미 | 기본값 |
| --- | --- | --- |
| `--glyphs N` | 이동 글리프 수 (엔티티 캡 후보) | 100 |
| `--mode full\|diff` | 렌더 방식 (전체 재출력 / 변경 셀만) | full |
| `--color-freq F` | 매 프레임 트루컬러로 렌더되는 글리프 비율 0.0~1.0 | 0.0 |
| `--viewport WxH` | 뷰포트 크기 (셀) | 100x30 |
| `--duration S` | 지속 측정 시간(초). 워밍업 1초는 통계에서 제외 | 10.0 |
| `--target-fps T` | 목표 FPS 하한(결정 기록용) | 20.0 |
| `--seed S` | 결정적 글리프 이동 시드 | 1234 |
| `--out PATH` | CSV append 경로(환경 메타 + 지표). 생략 시 stdout | (stdout) |
| `--selftest` | 헤드리스 로직 스모크, exit 0 | - |
| `--verify-bytes` | 헤드리스 바이트 기준 검사(A4/A5/A6), exit 0 | - |

출력 지표 4종: `fps_sustained`, `bytes_per_frame`, `frame_ms_p50`, `frame_ms_p95`.
1차 지표는 `bytes_per_frame`이다(마스터 section 3.3: 병목은 프레임당 I/O 바이트).

---

## 2. 측정 절차 (Day 2)

각 환경(로컬 / SSH 원격)마다 별도 CSV 파일에 기록한다. 파일명은
`bench/results/<host>-<emulator>.csv` 규칙을 따른다. 측정 중 다른 부하를
최소화하고 창 크기를 고정한다.

### 2.1 1차 스윕 - full vs diff, 단색, 100x30, N 스윕

```bash
OUT="bench/results/$(hostname)-${TERM_PROGRAM:-term}.csv"
for N in 50 100 200 400 800 ; do
  for M in full diff ; do
    .venv/bin/python bench/render_spike.py \
      --glyphs "$N" --mode "$M" --color-freq 0.0 \
      --viewport 100x30 --duration 10 --out "$OUT"
  done
done
```

이 1차 축소격자(5 N x 2 mode = 10행)가 각 환경에서 빈 셀 0건이어야 한다.

### 2.2 색 변경 영향 - 변곡 N에서 color-freq 스윕

```bash
for F in 0.0 0.5 1.0 ; do
  .venv/bin/python bench/render_spike.py \
    --glyphs 200 --mode diff --color-freq "$F" \
    --viewport 100x30 --duration 10 --out "$OUT"
done
```

### 2.3 뷰포트 영향 - 변곡 N에서 뷰포트 스윕

```bash
for V in 80x24 100x30 120x40 ; do
  .venv/bin/python bench/render_spike.py \
    --glyphs 200 --mode diff --color-freq 0.0 \
    --viewport "$V" --duration 10 --out "$OUT"
done
```

### 2.4 원격 반복

SSH 세션에서 2.1~2.3을 반복하되, **반드시 `--out`을 로컬과 다른 파일로
지정**한다. 같은 호스트로 SSH하면 `$(hostname)`이 동일하고 `TERM_PROGRAM`이
대개 비어 있어(-> `term`) 로컬과 같은 파일에 append되므로, 측정 CSV가 1개로
합쳐져 A8(`ls bench/results/*.csv | wc -l` >= 2)이 깨진다. 원격 전용 `OUT`을
먼저 고정한 뒤 2.1~2.3의 측정 명령을 재실행한다:

```bash
OUT="bench/results/$(hostname)-ssh.csv"   # 로컬과 반드시 다른 파일명
# 이 OUT으로 2.1~2.3의 측정 명령을 재실행
```

---

## 3. 측정 매트릭스 양식 (빈 템플릿)

독립 변수: `N` in {50,100,200,400,800}, `mode` in {full,diff},
`color-freq` in {0.0,0.5,1.0}, `viewport` in {80x24,100x30,120x40}.
종속 변수: `fps_sustained`, `bytes_per_frame`, `frame_ms_p50`, `frame_ms_p95`.

CSV는 하네스가 자동 생성하며, 사람이 보는 요약은 아래 표로 정리한다.

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

변곡 구간이 잡히면 color-freq / viewport 행을 추가 스윕해 채운다.

---

## 4. CSV 스키마

하네스가 출력하는 평면 CSV의 컬럼 순서:

```
timestamp,host,emulator,term,colorterm,net,geom,viewport,mode,color_freq,N,frames,fps_sustained,bytes_per_frame,frame_ms_p50,frame_ms_p95
```

- 앞 7개 컬럼이 환경 메타다(host, emulator, term, colorterm, net=local|ssh,
  geom=cols x rows, timestamp). 미설정 env 변수는 `-` 센티넬로 채워지므로
  빈 셀(`,,`)이 생기지 않는다.
- `net` 컬럼은 `SSH_CONNECTION`/`SSH_TTY` 존재 여부로 local/ssh를 구분한다.

검증:

```bash
ls bench/results/*.csv | wc -l           # 2 이상 (로컬 + SSH)
grep -c ',,' bench/results/*.csv         # 0 (빈 셀 없음)
```

---

## 5. 작동점 결정 (Day 3)

측정이 끝나면 `bench/results/decision.md`의 결정 규칙을 적용해
`(entity_cap, viewport_w, viewport_h, sim_tps, render_mode)`를 도출하고
`config/tuning.toml`의 PROVISIONAL 값을 측정값으로 덮어쓴다.

키 존재 검증:

```bash
python3 -c "import tomllib; d=tomllib.load(open('config/tuning.toml','rb')); \
assert all(k in d for k in ['sim_tps','viewport_w','viewport_h','entity_cap','render_mode'])"
echo "exit=$?"   # 0 기대
```

fallback 판정(작동점 확정 / 축소 경로 / 접근 재검토)은 decision.md에 명시한다.
