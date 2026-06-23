# Phase 4 상세개발 계획서 — 확장 (옵션·후순위)

작성일: 2026-06-23  
대상 레포: `terminal-vampire-survivor`  
상태: **잠정·후순위 (optional)** — Phase 3 exit gate 통과 이후 착수하는 선택적 확장이다. 각 항목은 서로 독립적으로 착수 가능하므로 순서에 구애받지 않고 필요한 것부터 시작할 수 있다.

> **이 문서는 day-by-day 정밀도를 갖지 않는다.** 항목별 작업 묶음과 측정 가능한 종료 조건을 가볍게 정리하는 것이 목적이다.

---

## 1. 개요

### Goal

Phase 3에서 완성된 MVP(실행 가능한 한 판, selftest exit 0)를 기반으로 게임의 깊이와 재플레이 가치를 높이는 확장 요소를 선택적으로 추가한다.

### Scope

**In (이 문서에서 다루는 항목):**

- 메타 진행: 영구 업그레이드·골드·언락, 세이브 파일 시스템
- 추가 콘텐츠: 무기/적/진화 데이터 추가 (데이터 주도)
- 보스/엘리트: 시간 기반 보스 스폰, 특수 공격 패턴
- 사운드: 터미널 비프, 기본 off 옵션 토글

**Out (Phase 4에서도 제외):**

- 온라인·랭킹·클라우드 세이브
- 수십 종 캐릭터/스테이지 전체 카탈로그
- 컷신·서사·로어
- 도전과제 시스템

### Key Deliverables

| 항목 | 산출물 | 독립 착수 가능 |
|------|--------|--------------|
| 메타 진행 | `terminal_vs/meta/` 모듈, `saves/meta.json` 스키마·저장·로드 | 예 |
| 추가 콘텐츠 | `config/balance.toml` 데이터 추가, 코드 변경 없는 로드 검증 | 예 |
| 보스/엘리트 | `sim/spawn.py` 보스 디렉터 확장, 헤드리스 테스트 | 예 (Phase 0 재측정 트리거 포함) |
| 사운드 | `terminal_vs/sound.py` 옵션 토글, 렌더/로직 분리 유지 검증 | 예 |

### Dependencies

- Phase 3 exit gate 완료 (selftest exit 0, import smoke, 한 판 완주 회귀 테스트 통과)
- `config/balance.toml` · `config/tuning.toml` 스키마 안정 (Phase 2~3 확정분)
- Phase 0 측정값: TPS·뷰포트·엔티티 캡 (`config/tuning.toml` 기록) — 보스 항목에서 재측정 트리거

### Effort (잠정, 항목별)

| 항목 | 예상 소요 |
|------|----------|
| 메타 진행 | 2~3일 |
| 추가 콘텐츠 | 1~2일 |
| 보스/엘리트 | 2~3일 + Phase 0 재측정 |
| 사운드 | 0.5~1일 |

---

## 2. Work Package

### 2-A. 메타 진행 (영구 업그레이드·골드·언락)

**목표:** 런 종료 후 획득한 골드를 영구 업그레이드에 투자하고, 다음 런 시작 시 자동 적용되는 세이브 시스템을 구축한다.

**주요 작업:**

1. `terminal_vs/meta/` 모듈 신설 — 세이브 스키마 정의, 저장·로드 순수 함수 구현
2. 런 종료 시 (`sim/step.py` 게임오버 판정 이후) 골드 적립 → `save_meta()` 호출
3. 런 시작 시 `load_meta()` → 불변 메타 상태 → `rules/leveling.py`·`rules/weapons.py`에 주입
4. `config/balance.toml`에 영구 업그레이드 항목·비용 데이터 추가
5. 세이브 스키마 검증 테스트·round-trip 테스트 작성

**종료 조건:**

```
python -m pytest tests/test_meta.py -k "roundtrip" -v
# → 모든 테스트 exit 0, 실패 0건
```

```python
# 테스트에서 확인할 동등성
state = MetaState(gold=150, upgrades={"speed": 2}, unlocked=["whip"])
assert load_meta(save_meta(state)) == state
```

```
python -m pytest tests/test_meta.py -k "schema_validation" -v
# → 손상된 세이브 파일 입력 시 MetaSaveError 예외 발생 확인, exit 0
```

---

### 2-B. 추가 콘텐츠 (무기/적/진화 데이터 추가)

**목표:** 기존 코드 변경 없이 `config/balance.toml`에 새 항목을 추가하는 것만으로 무기·적·진화가 게임에 로드되고 동작함을 확인한다. 데이터 주도 설계의 실증이 핵심이다.

**주요 작업:**

1. `balance.toml`에 무기 1~2종 추가 (예: `[weapons.whip]`, `[weapons.holy_wand]`)
2. `balance.toml`에 적 1종 추가 (예: `[enemies.bat]`)
3. `balance.toml`에 진화 1종 추가 (예: `[evolutions.unholy_vespers]`)
4. `config.py`의 스키마 검증이 새 항목을 수용하는지 확인
5. selftest에 신규 콘텐츠 로드 스모크 테스트 추가

**종료 조건:**

```bash
# Python 파일 변경 없이 balance.toml만 수정 후:
git diff --name-only -- 'terminal_vs/**/*.py'
# → 출력 없음 (0건) — 코드 변경 없음 확인
```

```bash
python -m pytest tests/ -k "content_load" -v
# → exit 0, 신규 무기·적·진화 로드 검증 통과
```

```bash
python selftest.py
# → exit 0 (기존 selftest 회귀 없음)
```

---

### 2-C. 보스/엘리트

**목표:** `sim/spawn.py`의 difficulty director에 시간 기반 보스 스폰을 추가한다. 보스는 엔티티 수를 크게 증가시키므로 Phase 0 엔티티 캡 재측정 트리거를 명시한다.

**주요 작업:**

1. `balance.toml`에 보스 정의 추가 (`[enemies.boss_bat]` — HP·속도·스폰 시각·특수 공격 패턴)
2. `sim/spawn.py` director에 보스 스폰 조건 추가 (시간 임계값, `tuning.toml`의 `boss_spawn_times` 참조)
3. 보스 특수 공격 규칙 → `rules/weapons.py` 또는 `rules/damage.py` 순수 함수로 구현
4. 보스 처치 시 대형 경험치 드랍 → `rules/leveling.py` 확장
5. 보스 스폰·처치 헤드리스 테스트 작성
6. **Phase 0 재측정**: 보스 추가 후 화면 엔티티 수가 Phase 0 측정 기준 엔티티 캡을 초과할 수 있다 → `tuning.toml`의 엔티티 캡·TPS를 재측정하고 갱신

**종료 조건:**

```bash
python -m pytest tests/test_boss.py -v
# → exit 0: 보스 스폰 테스트(RNG 시드 고정, boss entity 생성 확인),
#    처치 테스트(HP 0 → 버퍼에서 제거 + XP 드랍 확인) 모두 통과
```

```bash
# 보스 추가 후 렌더 처리량 재측정 트리거:
python tools/render_stress.py --entity-count <Phase0_cap + boss_overhead>
# → 측정된 TPS가 tuning.toml의 sim_tps 목표를 충족하는지 확인,
#    충족 못 하면 tuning.toml의 boss_entity_limit 조정
```

---

### 2-D. 사운드 (터미널 비프, 최후순위)

**목표:** 터미널 비프를 옵션 토글로 추가한다. 사운드는 기본 off이며, 활성화 여부가 게임 로직에 영향을 미치지 않아야 한다(렌더/로직 분리 유지).

**주요 작업:**

1. `terminal_vs/sound.py` 신설 — `beep(event: str) -> None` (no-op 또는 `\a` 출력)
2. `tuning.toml`에 `sound_enabled = false` 키 추가
3. `__main__.py`에서만 `sound.py` 호출 (렌더 계층과 동일한 격리 규칙 — `rules/*`·`sim/*`은 `sound.py` 비의존)
4. 결정적 동등성 테스트: 동일 시드에서 사운드 on/off 두 런의 최종 시뮬레이션 상태가 동일한지 확인

**종료 조건:**

```python
# 테스트에서 확인할 동등성 (렌더/로직 분리 증명)
rng_seed = 42
state_sound_on  = headless_run(rng_seed=rng_seed, sound=True,  ticks=500)
state_sound_off = headless_run(rng_seed=rng_seed, sound=False, ticks=500)
assert hash_sim_state(state_sound_on) == hash_sim_state(state_sound_off)
```

```bash
python -m pytest tests/test_sound.py -v
# → exit 0, 동등성 테스트 통과
```

```bash
grep -rE "import sound|from.*sound" terminal_vs/rules/ terminal_vs/sim/
# → 출력 없음 (0건) — rules/·sim/에 sound 의존 없음 확인
```

---

## 3. 아키텍처·기술 노트

### 3.1 모듈 레이아웃 (§5.1 기준 추가/변경)

Phase 4에서 추가되는 파일:

```
terminal_vs/
  meta/
    __init__.py
    schema.py       # MetaState 불변 타입 정의, save/load 순수 함수
    save.py         # JSON 직렬화·역직렬화 (stdlib json 사용)
  sound.py          # 터미널 비프 토글 (선택 항목)
saves/              # 프로젝트 루트 아래 런타임 생성 디렉터리
  meta.json         # 메타 진행 세이브 파일 (gitignore 대상)
```

기존 파일 변경:

| 파일 | 변경 내용 |
|------|----------|
| `sim/spawn.py` | 보스 스폰 디렉터 추가 |
| `rules/leveling.py` | 보스 처치 대형 XP·영구 업그레이드 효과 적용 |
| `config/balance.toml` | 추가 무기·적·진화·영구 업그레이드 데이터 |
| `config/tuning.toml` | `sound_enabled`, `boss_spawn_times`, 재측정 후 엔티티 캡 갱신 |

### 3.2 세이브 포맷 — JSON (stdlib, 이유 명시)

메타 진행 세이브는 `json` (Python stdlib)으로 구현한다.

- **이유:** `tomllib` (Python 3.11+ stdlib)은 **읽기 전용** — TOML을 쓰려면 서드파티 의존성(`tomli-w` 등)이 필요하다. `json`은 읽기+쓰기 모두 stdlib으로 해결되며 추가 의존성이 없다.
- **config와의 구분:** `balance.toml`·`tuning.toml`은 TOML (사람이 편집하는 밸런스/튜닝 상수), `saves/meta.json`은 JSON (런타임이 읽고 쓰는 영구 상태). 형식이 다름으로써 역할이 명확히 구분된다.

### 3.3 불변성 경계 (ADR-001 확장 적용)

```
세이브 로드  →  불변 MetaState  →  rules/leveling.py 주입 (읽기 전용)
런 진행 중  →  sim/state.py 내부 gold_earned 누적 (가변, sim 경계 안)
런 종료 후  →  pure_function(sim_state, old_meta) → new_meta (새 객체 생성)
                → save_meta(new_meta) → saves/meta.json 기록
```

- `new_meta`는 기존 `old_meta`를 제자리 변경하지 않는다. 런 종료 후 순수 함수가 새 `MetaState`를 산출한다.
- 런 중 골드 누적은 `sim/step.py` 내부 가변 버퍼에서만 일어난다(ADR-001 가변 경계 안).
- 메타 상태가 sim 틱 중 갱신되는 일은 없다.

### 3.4 보스 스폰과 Phase 0 엔티티 캡 재측정

보스는 HP가 높고 투사체를 발사하므로 화면 엔티티 수를 Phase 0 측정 시보다 늘린다. 보스 항목 착수 전 또는 완료 후 다음을 수행한다:

1. `tools/render_stress.py`로 보스 등장 시 예상 엔티티 수(일반 적 + 보스 투사체)로 부하 측정.
2. 측정 TPS가 `tuning.toml`의 `sim_tps` 목표 미달이면 `boss_entity_limit` 또는 일반 적 캡 조정.
3. 조정값을 `tuning.toml`에 반영하고 변경 이유를 주석으로 기록.

성능 수치는 절대 이 문서에 하드코딩하지 않는다. `tuning.toml`(Phase 0 산출값)이 유일한 숫자의 출처다.

---

## 4. Critical Code Specs

### 4.1 MetaState 스키마·저장·로드 경계

```python
# terminal_vs/meta/schema.py
from dataclasses import dataclass, field
from typing import Mapping

@dataclass(frozen=True)         # frozen=True → 불변 MetaState
class MetaState:
    gold: int = 0
    upgrades: Mapping[str, int] = field(default_factory=dict)  # upgrade_id → level
    unlocked: frozenset[str] = field(default_factory=frozenset)  # weapon/character ids
    total_runs: int = 0

    # 동등성 비교: dataclass 기본 __eq__ 사용 (round-trip 테스트에서 활용)
```

```python
# terminal_vs/meta/save.py
import json
from pathlib import Path
from .schema import MetaState

SAVE_PATH = Path("saves/meta.json")

CURRENT_VERSION = 1

def save_meta(state: MetaState, path: Path = SAVE_PATH) -> None:
    """런 종료 후 호출 — sim 틱 중 호출 금지."""
    payload = {
        "version": CURRENT_VERSION,
        "gold": state.gold,
        "upgrades": dict(state.upgrades),
        "unlocked": list(state.unlocked),
        "total_runs": state.total_runs,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

def load_meta(path: Path = SAVE_PATH) -> MetaState:
    """런 시작 시 호출 → 불변 MetaState 반환. 파일 없으면 기본값 반환."""
    if not path.exists():
        return MetaState()
    raw = json.loads(path.read_text(encoding="utf-8"))
    _validate(raw)  # 스키마·범위 검증 → 실패 시 MetaSaveError 발생
    return MetaState(
        gold=raw["gold"],
        upgrades=raw["upgrades"],
        unlocked=frozenset(raw["unlocked"]),
        total_runs=raw.get("total_runs", 0),
    )

def _validate(raw: dict) -> None:
    """필수 키 존재·타입·범위 검증."""
    required = {"version", "gold", "upgrades", "unlocked"}
    missing = required - raw.keys()
    if missing:
        raise MetaSaveError(f"save missing keys: {missing}")
    if not isinstance(raw["gold"], int) or raw["gold"] < 0:
        raise MetaSaveError(f"invalid gold: {raw['gold']!r}")
    # version 마이그레이션 훅 (현재는 v1만)
    if raw["version"] > CURRENT_VERSION:
        raise MetaSaveError(f"unknown save version: {raw['version']}")

class MetaSaveError(ValueError):
    """세이브 파일 스키마 또는 내용 오류."""
```

```python
# 런 종료 후 골드 적립 — 순수 함수 (sim 완료 후 호출)
def accrue_meta(old_meta: MetaState, run_result: RunResult) -> MetaState:
    """기존 MetaState를 변경하지 않고 새 MetaState 반환."""
    new_gold = old_meta.gold + run_result.gold_earned
    new_runs = old_meta.total_runs + 1
    # 언락 조건 체크 (순수 판정)
    new_unlocked = old_meta.unlocked | _check_unlocks(run_result)
    return MetaState(
        gold=new_gold,
        upgrades=old_meta.upgrades,
        unlocked=new_unlocked,
        total_runs=new_runs,
    )
```

### 4.2 보스 스폰 디렉터 확장

```python
# sim/spawn.py (보스 디렉터 추가 부분)

def director_tick(sim_state, elapsed_sec: float, rng, cfg) -> list[Enemy]:
    """기존 일반 적 스폰 + 보스 스폰 판정."""
    spawned = _regular_spawn(sim_state, elapsed_sec, rng, cfg)

    # 보스 스폰 — tuning.toml의 boss_spawn_times 참조 (하드코딩 금지)
    for boss_time in cfg.boss_spawn_times:
        if _crosses_threshold(sim_state.prev_elapsed, elapsed_sec, boss_time):
            if not _boss_alive(sim_state):
                spawned.append(_spawn_boss(rng, cfg))

    return spawned   # 새 enemy 리스트 반환 (sim/step.py가 버퍼에 추가)
```

### 4.3 사운드 격리

```python
# terminal_vs/sound.py
import sys

def beep(event: str, enabled: bool) -> None:
    """렌더 계층과 동일한 격리 규칙: __main__에서만 호출.
    rules/*, sim/* 에서 import 금지.
    enabled=False(기본) → 완전 no-op.
    """
    if not enabled:
        return
    # 터미널 비프 — 단순 BEL 문자
    sys.stdout.write("\a")
    sys.stdout.flush()
```

---

## 5. Acceptance Criteria

| # | 기준 | 검증 절차 | 통과 |
|---|------|----------|------|
| AC-1 | MetaState round-trip 동등성 | `python -m pytest tests/test_meta.py -k roundtrip -v` → exit 0, 실패 0건 | - [ ] |
| AC-2 | 손상 세이브 파일 → MetaSaveError | `python -m pytest tests/test_meta.py -k schema_validation -v` → exit 0, 예외 타입 일치 | - [ ] |
| AC-3 | 추가 콘텐츠 — 코드 변경 없음 | `git diff --name-only -- 'terminal_vs/**/*.py'` → 출력 없음 (0건) | - [ ] |
| AC-4 | 추가 콘텐츠 — 로드 검증 통과 | `python -m pytest tests/ -k content_load -v` → exit 0 | - [ ] |
| AC-5 | 보스 스폰·처치 헤드리스 테스트 | `python -m pytest tests/test_boss.py -v` → exit 0, 스폰 확인 + 처치 후 버퍼 제거 + XP 드랍 확인 | - [ ] |
| AC-6 | 사운드 on/off 시뮬레이션 동등성 | `python -m pytest tests/test_sound.py -k determinism -v` → `hash_sim_state(sound=True) == hash_sim_state(sound=False)`, exit 0 | - [ ] |
| AC-7 | sound 비의존 확인 (rules·sim) | `grep -rE "import sound\|from.*sound" terminal_vs/rules/ terminal_vs/sim/` → 출력 없음 (0건) | - [ ] |
| AC-8 | 기존 selftest 회귀 없음 | `python selftest.py` → exit 0 | - [ ] |
| AC-9 | 세이브 파일 config 외부 위치 확인 | `ls saves/meta.json` 존재 확인; `ls config/` → `balance.toml`, `tuning.toml`만 있음 (meta.json 없음) | - [ ] |

---

## 6. Risks & Mitigations

| 위험 | 가능성 | 영향 | 완화 |
|------|--------|------|------|
| 보스 등장으로 엔티티 수 증가 → Phase 0 엔티티 캡 초과, TPS 저하 | 중~높음 | 높음 | 보스 항목 착수 시 `tools/render_stress.py`로 재측정 필수. `tuning.toml`의 `boss_entity_limit` 조정 후 재검증. 성능 수치는 이 문서에 하드코딩하지 않는다. |
| 세이브 파일 포맷 불안정 (스키마 변경으로 기존 세이브 파손) | 중 | 중 | `version` 키 관리 + `_validate()`의 마이그레이션 훅. v1 → v2 스키마 변경 시 마이그레이션 함수 추가 필수. |
| 추가 콘텐츠가 코드 의존으로 흘러들어 데이터 주도 설계 훼손 | 중 | 중 | AC-3 (`git diff` 0건) 체크. `config.py`의 스키마 검증 범위를 충분히 확장해 데이터만으로 처리하도록 설계. |
| 사운드 토글이 게임 로직 분기에 영향 | 낮음 | 중 | `sound.py`를 `__main__`에서만 호출. AC-6·AC-7 테스트로 격리 검증. |
| 메타 진행 범위 과확장 (도전과제·캐릭터 언락 전체 구현) | 중 | 높음 | 이 문서의 Scope out을 엄수. 골드·기본 영구 업그레이드·간단한 언락 조건만 포함. |
| 세이브 파일 gitignore 누락 (개인 진행 상태가 커밋됨) | 낮음 | 낮음 | `.gitignore`에 `saves/` 추가. |

---

## 7. Exit Gate / 향후 확장

Phase 4는 고정 exit gate를 갖지 않는 옵션 phase다. 대신 아래 판단 기준으로 "v1 확장으로 충분한가"를 결정한다.

### 각 항목의 독립 완료 기준

- **메타 진행**: AC-1·AC-2·AC-9 통과 + 1회 런에서 골드 적립 → 저장 → 다음 런에서 영구 업그레이드 적용 수동 확인.
- **추가 콘텐츠**: AC-3·AC-4·AC-8 통과 + 신규 무기가 실제 게임 내 선택지로 등장하는 수동 확인.
- **보스/엘리트**: AC-5 통과 + Phase 0 재측정 후 `tuning.toml` 갱신 + 보스 등장·처치 수동 확인.
- **사운드**: AC-6·AC-7 통과 + `tuning.toml`의 `sound_enabled = true` 설정으로 비프 동작 수동 확인.

### "어디까지 하면 충분한가" 판단 기준

다음 조건을 충족하면 v1 확장을 완료로 판정한다:

- 메타 진행: 세이브 round-trip 및 영구 업그레이드 1~2종 동작 확인.
- 추가 콘텐츠: 무기 1~2종·적 1종 추가, 코드 변경 없이 데이터 주도 로드 검증.
- 보스/엘리트: 보스 1종 스폰·처치 동작 + Phase 0 재측정 완료.
- 사운드: 토글 동작 + 로직 격리 테스트 통과.

이후 추가 종류(무기·적 카탈로그 확장, 엘리트 다수, 영구 업그레이드 트리 심화)는 v2 확장 또는 별도 문서로 분리한다.

---

## 부록 A. 환경·파일 목록 요약

| 경로 | 역할 |
|------|------|
| `terminal_vs/meta/schema.py` | MetaState 불변 타입, MetaSaveError |
| `terminal_vs/meta/save.py` | JSON 저장·로드·검증 순수 함수 |
| `terminal_vs/sound.py` | 터미널 비프 토글 (선택) |
| `saves/meta.json` | 런타임 생성 세이브 파일 (.gitignore 대상) |
| `config/balance.toml` | 추가 무기·적·진화·영구 업그레이드 데이터 |
| `config/tuning.toml` | `sound_enabled`, `boss_spawn_times`, 재측정 후 엔티티 캡 |
| `tests/test_meta.py` | round-trip, schema_validation 테스트 |
| `tests/test_boss.py` | 보스 스폰·처치 헤드리스 테스트 |
| `tests/test_sound.py` | 사운드 격리·결정적 동등성 테스트 |

## 부록 B. 참고

- 마스터 계획서 §10 Phase 4, §11 D4, §1 out of scope, §5.5, §6 (ADR-001), §7
- Phase 0 산출 문서 (`config/tuning.toml` 확정값)
- Python stdlib: `json` (읽기+쓰기), `tomllib` (3.11+, 읽기 전용) — 세이브 포맷 선택 근거
