# Phase 2 상세개발 계획서 — 무기/패시브/진화 + MVP 콘텐츠

작성일: 2026-06-23
대상 레포: `terminal-vampire-survivor`
대상 마일스톤: 마스터 계획서 §10 Phase 2
선행 문서: `docs/plan/2026-06-23/work-plan-v1.md` (마스터 설계·기술 계획서 v1)

> 이 문서는 마스터 계획서 §7(MVP 최소 세트), §8(진행 시스템), §5.4(틱 파이프라인),
> §5.5(config), §6/ADR-001(불변성 경계)을 Phase 2 범위로 구체화한 상세개발 계획서다.
> 성능 수치(TPS·뷰포트·엔티티 캡)는 본 문서에서 확정하지 않으며, Phase 0 산출값과
> `config/tuning.toml`을 참조로만 표기한다(마스터 §3.3, §4, §10의 절대 규칙).

---

## 1. 개요

### Goal

레벨업 N택 드래프트로 무기·패시브를 조합해 빌드가 갈리고, 특정 무기 만렙과 짝 패시브
보유 조건이 충족되면 진화가 발동하는 성장 루프를 완성한다. 무기 3종·패시브 2~3종·진화
1종·적 2종·디렉터 난이도 곡선을 모두 `config/balance.toml`로 구동하며, 빌드 분기와 진화
자격 판정을 결정적 헤드리스 테스트로 검증한다.

### Scope

**In scope**

- 무기 3종: 단검류(최근접 적 방향 투사체), 근접 휘두르기(진행 방향 좌우 짧은 범위 타격),
  자동 조준 마법탄(최근접/임의 적 추적). `rules/weapons.py`의 순수 발사 판정.
- 패시브 2~3종: 공격 속도, 이동 속도, 픽업 회수 범위(자석). 무기/이동/픽업 스탯에 곱연산.
- 진화 1종: 단검 만렙 + 공격속도 패시브 보유 → 진화 무기(관통/연사 강화). `rules/evolution.py`
  순수 자격 판정.
- 적 2종: 느린 기본 추적형(다수), 빠른 약체 떼. HP·이동속도·스폰 가중치는 `balance.toml`.
- 픽업: 경험치 보석(필수), 회복·자석(옵션). 자석 범위는 패시브로 확장.
- 디렉터: 경과 시간 기반 스폰율 상승 + 1분 단위 강화 스텝. 시간→스폰 파라미터 매핑을
  순수 규칙으로 분리(`sim/spawn.py`), 실제 엔티티 생성만 sim 제자리.
- 레벨업 N택 드래프트: 신규 무기 / 기존 무기 강화 / 패시브 후보 산출(`rules/leveling.py` 순수).
- 콘텐츠 데이터의 `config/balance.toml` 외부화 + `rules/defs.py` 불변 로드.

**Out of scope (Phase 2 밖)**

- 보스/엘리트 적(마스터 §7 후순위, Phase 4 후보).
- 메타 진행(영구 업그레이드·골드·언락; 마스터 §11 D4, Phase 4).
- HUD 시각 폴리시·게임오버/재시작 흐름 완성(Phase 3 §10).
- 밸런스 수치의 "재미" 최종 튜닝(Phase 3에서 1차 밸런싱). Phase 2는 빌드 분기가 구조적으로
  가능함을 증명하는 데까지.
- 무기 4종 이상·진화 2종 이상·추가 적(후속 콘텐츠 문서).
- TPS·뷰포트·엔티티 캡 등 운영 상수 결정(Phase 0 소관).

### Key Deliverables

| # | 산출물 | 위치 |
| --- | --- | --- |
| KD1 | 무기·적·진화·패시브·디렉터 밸런스 스키마 | `config/balance.toml` |
| KD2 | balance.toml 로드·검증 → 불변 밸런스 테이블 | `rules/defs.py`, `config.py` 확장 |
| KD3 | 무기 3종 발사 판정(쿨다운·타게팅·투사체 생성 명세) 순수 함수 | `rules/weapons.py` |
| KD4 | 패시브 효과 적용(공속·이속·자석) 순수 함수 | `rules/weapons.py`, `rules/leveling.py` |
| KD5 | 진화 자격 판정 순수 함수 | `rules/evolution.py` |
| KD6 | 레벨업 N택 후보 산출 순수 함수 | `rules/leveling.py` |
| KD7 | 디렉터 시간→스폰 파라미터 순수 규칙 + sim 스폰 통합 | `sim/spawn.py`, `sim/step.py` |
| KD8 | 무기 발사·디렉터 스폰을 틱 파이프라인(§5.4 4·2단계)에 통합 | `sim/step.py` |
| KD9 | 레벨업 드래프트 오버레이(선택지 표시·적용) | `render/hud.py`, `sim/state.py` |
| KD10 | 헤드리스 결정적 테스트(진화 자격·레벨링·빌드 분기·디렉터 곡선) | `tests/` |

### Dependencies

**Entry = Phase 1 exit (이미 존재한다고 가정, 재구축 아님):**

- 이동 + 플레이어 중심 카메라/뷰포트(`world.py`).
- 적 1종 스폰 + 무기 1종 자동 발사 + 충돌 해소 + 경험치 적립 + 레벨업 1택.
- fixed-timestep 루프(`loop.py`)와 틱 파이프라인 골격(`sim/step.py` §5.4 1~10단계 일부).
- 공간 해시(`sim/spatial.py`) 충돌 질의.
- 헤드리스 rules 테스트가 exit 0으로 통과하는 테스트 하네스.
- `config.py`의 TOML 로드·검증·불변 객체 생성 기반(`tuning.toml` 로딩 경로 존재).

**Phase 2가 그 위에 얹는 증분:**

- 무기 1종 → 3종, 적 1종 → 2종, 레벨업 1택 → N택 드래프트.
- 패시브 신설, 진화 신설, 디렉터 곡선 신설.
- `balance.toml` 신설 + `rules/defs.py` 신설.

**외부 의존:** Python 3.11+ 표준 라이브러리 `tomllib`(추가 의존성 없음). `blessed`는
`render/`·`__main__`에만(rules·sim은 비의존, 마스터 §13).

### Effort 표

| Day | 작업 묶음 | 예상 소요 |
| --- | --- | --- |
| Day 1 | balance.toml 스키마 + config 검증 + defs 불변 로드 | 1.0일 |
| Day 2 | rules/weapons.py — 무기 3종 발사·타게팅 순수 판정 | 1.0일 |
| Day 3 | rules/leveling.py + 패시브 효과 — N택 드래프트·스탯 적용 | 1.0일 |
| Day 4 | rules/evolution.py — 진화 자격 판정 + 진화 무기 정의 | 0.5일 |
| Day 5 | sim/spawn.py 디렉터 + sim/step.py 파이프라인 통합 | 1.0일 |
| Day 6 | render/hud.py 레벨업 드래프트 오버레이 + 상태 연결 | 1.0일 |
| Day 7 | 헤드리스 결정적 테스트(진화·레벨링·빌드 분기·디렉터) + qa-tester 대화형 1판 | 1.0일 |

합계: 약 6.5일(추정). 위 일수는 작업량 추정이며 성능 작동점과 무관하다.

---

## 2. Day-by-Day Work Package

각 Day 카드는 목표·산출물·OMC 위임·예상 소요·기술 노트·측정 가능한 종료 조건으로 구성한다.
종료 조건의 명령은 테스트 파일·함수명을 잠정으로 표기하며, 구현 시 동일 이름으로 작성한다.

---

### Day 1 — balance.toml 스키마 + config 검증 + defs 불변 로드

**목표**
무기/적/진화/패시브/디렉터/레벨링 밸런스 상수를 전부 `config/balance.toml`로 외부화하고,
`config.py`가 스키마·범위를 검증해 불변 객체로 만들며, `rules/defs.py`가 이를 읽어 규칙
계층에 주입 가능한 불변 밸런스 테이블로 노출한다.

**산출물**

- `config/balance.toml`: `[weapons.*]`, `[passives.*]`, `[enemies.*]`, `[evolution.*]`,
  `[director]`, `[leveling]` 섹션.
- `config.py`: `load_balance(path) -> BalanceConfig` 추가(스키마/범위 검증, 누락 키 기본값
  폴백, 잘못된 값은 명확한 에러).
- `rules/defs.py`: `BalanceConfig`를 받아 무기/적/진화/패시브 정의를 불변 데이터로 노출
  (frozen dataclass / `tuple` / `frozenset` 사용).

**OMC 위임:** `executor`(model=opus — 스키마 설계·검증 규칙 정합성이 하류 전체를 규정).

**예상 소요:** 1.0일

**기술 노트**

- 마스터 §5.5: balance 상수는 코드 하드코딩 금지, `balance.toml`로 외부화. `config.py`가
  로드→검증→불변 객체. 누락 키는 코드 기본값 폴백(파일 없어도 첫 실행 보장), 잘못된 값은
  모호하지 않은 에러.
- 마스터 §6/ADR-001: `rules/defs.py`가 노출하는 밸런스 테이블은 불변. 규칙 계층은 전역 접근
  대신 주입받아 결정적 테스트 가능(`random.Random` 주입과 동일 원칙).
- 성능 운영 상수(TPS·뷰포트·엔티티 캡)는 `tuning.toml` 소관이며 이 파일에 넣지 않는다.

**측정 가능한 종료 조건**

- `python -c "import tomllib,pathlib; tomllib.loads(pathlib.Path('config/balance.toml').read_text())"`
  가 exit code 0(TOML 파싱 성공).
- `python -m pytest tests/test_config_balance.py -q` exit code 0. 포함 케이스:
  - `test_load_balance_returns_immutable`: 반환 객체 필드 재할당 시 `FrozenInstanceError`
    또는 `AttributeError` 발생을 assert.
  - `test_missing_key_falls_back_to_default`: 특정 키를 제거한 dict 입력 시 코드 기본값으로
    채워짐을 `assertEqual`로 검증.
  - `test_out_of_range_raises`: 음수 쿨다운 등 범위 위반 입력 시 명시적 예외(메시지에 키 이름
    포함)를 `pytest.raises`로 검증.
- `grep -rEn "(cooldown|damage|hp|move_speed|spawn_weight)\s*=\s*[0-9]" terminal_vs/rules/ terminal_vs/sim/`
  결과 0건(밸런스 수치가 코드에 하드코딩되지 않음).
- `grep -rEn "(sim_tps|viewport|entity_cap|poll_timeout)" config/balance.toml` 결과 0건
  (운영 상수가 balance.toml에 섞이지 않음).

---

### Day 2 — rules/weapons.py 무기 3종 발사·타게팅 순수 판정

**목표**
무기 3종의 쿨다운 갱신·타게팅·투사체 생성 명세를 부수효과 없는 순수 함수로 구현한다.
함수는 읽기 전용 스냅샷(플레이어 위치, 적 위치 목록, 무기 상태, 밸런스 정의, 주입 RNG)을
입력받아 "생성할 투사체 명세"와 "갱신된 쿨다운"을 값으로 반환한다. 실제 버퍼 삽입은 sim의
몫이다(Day 5).

**산출물**

- `rules/weapons.py`:
  - `tick_weapon(weapon_state, ctx, rng) -> WeaponFireResult` (순수). 쿨다운이 0 이하면 발사,
    아니면 쿨다운만 감소.
  - 타게팅 전략: `target_nearest`(단검·마법탄), `target_forward_arc`(휘두르기) 순수 함수.
  - 무기별 발사 명세 생성: 단검=최근접 적 방향 투사체 1+발(패시브·무기레벨에 따라 수 증가),
    휘두르기=진행 방향 좌우 짧은 사거리 히트박스(즉시 판정), 마법탄=최근접/임의 적 추적 투사체.

**OMC 위임:** `executor`(model=opus). 검토: `python-reviewer`(별도 패스, 순수성·불변성 검증).

**예상 소요:** 1.0일

**기술 노트**

- 마스터 §5.4 4단계(무기 쿨다운 갱신 → 발사 → 투사체 생성)의 규칙 부분.
- 불변성 경계(ADR-001): 이 함수들은 **순수**. 입력 스냅샷을 변형하지 않고 새 값(`WeaponFireResult`)을
  반환한다. 호출부(`sim/step.py`)가 결과를 받아 버퍼에 제자리 삽입한다.
- 종횡비 보정: 타게팅 방향·사거리는 월드 좌표 기준. 셀 보정은 `world.py`/렌더 책임이며 규칙은
  월드 좌표로만 계산(마스터 §3.1).
- 결정적 무작위: "임의 적 추적"·동률 타깃 선택은 주입 `random.Random`으로만 결정.

**측정 가능한 종료 조건**

- `python -m pytest tests/test_weapons.py -q` exit code 0. 포함 케이스:
  - `test_cooldown_blocks_fire`: 쿨다운 > 0이면 `fired is False`이고 쿨다운이 dt만큼 감소.
  - `test_dagger_targets_nearest`: 적 3기 배치 시 최근접 적 방향(단위 벡터) 일치를
    `assertAlmostEqual`(허용오차 1e-9)로 검증.
  - `test_swing_forward_arc_hits_only_arc`: 진행 방향 좌우 사거리 안 적만 히트 목록에 포함,
    뒤쪽 적 제외를 `assertEqual`로 검증.
  - `test_magic_bolt_random_target_deterministic`: 동일 시드 2회 호출이 동일 타깃 인덱스
    반환(`assertEqual`).
  - `test_weapon_fn_is_pure`: 호출 전후 입력 스냅샷 객체가 `==`로 불변임을 검증(deepcopy 비교).
- `grep -rEn "import blessed|from blessed" terminal_vs/rules/weapons.py` 결과 0건(규칙 계층
  blessed 비의존).

---

### Day 3 — rules/leveling.py + 패시브 효과: N택 드래프트·스탯 적용

**목표**
레벨업 시 N택 업그레이드 후보(신규 무기 / 기존 무기 강화 / 패시브)를 결정적으로 산출하고,
선택을 적용해 갱신된 빌드 상태를 반환하는 순수 함수를 구현한다. 패시브(공속·이속·자석)는
스탯에 곱연산으로 적용된다.

**산출물**

- `rules/leveling.py`:
  - `xp_for_level(level, defs) -> int` (순수, 경험치 곡선).
  - `roll_choices(build_state, defs, rng, n) -> tuple[Choice, ...]` (순수, Phase 1 `roll_choices(level_state, cfg, rng, n=1)`를 `build_state`·`defs`·N택으로 일반화). 보유 무기 강화/
    신규 무기/패시브 후보를 가중 추출, 만렙 무기·만렙 패시브는 후보에서 제외.
  - `apply_choice(build_state, choice) -> BuildState` (순수, 새 불변 상태 반환).
  - `effective_stats(build_state, defs) -> Stats` (순수). 공속/이속/자석 범위에 패시브 곱연산.

**OMC 위임:** `executor`(model=opus). 검토: `python-reviewer`(별도 패스).

**예상 소요:** 1.0일

**기술 노트**

- 마스터 §8: N택 카드(신규 무기/기존 강화/패시브), 무기 레벨·만렙→진화 자격. 일시정지
  오버레이는 Day 6.
- 불변성 경계: `apply_choice`는 새 `BuildState`를 반환(전역 immutable 규약 그대로). 빌드 상태는
  규칙 계층의 불변 값이며 sim의 가변 버퍼와 분리.
- N(드래프트 선택지 수)은 `balance.toml [leveling]`에서 로드(성능 상수 아님, 밸런스 상수).
- 후보 고갈 처리: 모든 무기·패시브 만렙이면 폴백 후보(회복·소액 보너스) 정책을 명시(빌드 분기
  테스트의 결정성 보장 위해 필수).

**측정 가능한 종료 조건**

- `python -m pytest tests/test_leveling.py -q` exit code 0. 포함 케이스:
  - `test_xp_curve_monotonic`: `xp_for_level(n+1) > xp_for_level(n)` for n in range(1, 20).
  - `test_roll_choices_deterministic`: 동일 시드·동일 빌드 상태 2회 호출이 동일 후보 튜플
    반환(`assertEqual`).
  - `test_maxed_weapon_excluded`: 만렙 무기가 "기존 무기 강화" 후보에서 제외됨을 검증.
  - `test_apply_choice_returns_new_state`: `apply_choice` 반환 객체 `is not` 입력 객체이고
    입력 객체 불변(deepcopy 비교).
  - `test_passive_multiplies_stats`: 공속 패시브 1레벨 적용 후 `effective_stats().attack_speed`가
    기대 배수와 `assertAlmostEqual`(1e-9).
- `grep -rEn "import blessed|from blessed" terminal_vs/rules/leveling.py` 결과 0건.

---

### Day 4 — rules/evolution.py 진화 자격 판정 + 진화 무기 정의

**목표**
"무기 만렙 + 짝 패시브 보유" 조건을 검사하는 순수 자격 판정 함수와, 자격 충족 시 진화 후보를
산출하는 함수를 구현한다. 진화 1종(단검 만렙 + 공격속도 패시브 → 진화 무기: 관통/연사 강화)을
`balance.toml [evolution]`으로 정의한다.

**산출물**

- `rules/evolution.py`:
  - `eligible_evolutions(build_state, defs) -> tuple[EvolutionDef, ...]` (순수). 각 진화 정의의
    전제(base 무기 만렙 + 요구 패시브 보유)를 검사해 충족 목록 반환.
  - `apply_evolution(build_state, evo_def) -> BuildState` (순수). base 무기를 진화 무기로 치환,
    새 불변 상태 반환.
- `config/balance.toml [evolution.dagger_x]`: `base = "dagger"`, `requires_passive = "attack_speed"`,
  `base_max_level = N`, `result_weapon = "dagger_evolved"` + 진화 무기 스탯(관통 수·연사 배수).

**OMC 위임:** `executor`(model=opus). 검토: `python-reviewer`(별도 패스).

**예상 소요:** 0.5일

**기술 노트**

- 마스터 §8: 진화는 "무기 만렙 + 짝 패시브 보유" 충족 시 선택지 등장, `rules/evolution.py`
  순수 판정.
- 자격 판정은 진화 정의 테이블(balance.toml)을 데이터로 순회 — 진화 추가 시 코드 수정 없이
  테이블만 확장 가능(후속 콘텐츠 문서 대비).
- 진화 발동 트리거: 자격 충족이 감지되면 레벨업 드래프트(Day 3 `roll_choices`)에 진화 후보가
  주입되거나 즉시 진화 선택지가 뜨는 정책. Phase 2는 드래프트 후보 주입 방식 채택(레벨업
  오버레이 재사용, Day 6).

**측정 가능한 종료 조건**

- `python -m pytest tests/test_evolution.py -q` exit code 0. 포함 케이스(자격 판정 정확성):
  - `test_eligible_when_max_and_passive`: 단검 만렙 + 공속 패시브 보유 → 결과에 `dagger_x` 포함.
  - `test_not_eligible_without_passive`: 단검 만렙 + 공속 패시브 **없음** → 결과 빈 튜플.
  - `test_not_eligible_when_not_maxed`: 공속 패시브 보유 + 단검 **만렙 아님** → 결과 빈 튜플.
  - `test_apply_evolution_replaces_base`: `apply_evolution` 후 base 무기 제거 + 진화 무기 보유,
    입력 상태 불변(deepcopy 비교).
- `grep -rEn "import blessed|from blessed" terminal_vs/rules/evolution.py` 결과 0건.

---

### Day 5 — sim/spawn.py 디렉터 + sim/step.py 파이프라인 통합

**목표**
경과 시간 → 스폰율·강화 스텝 매핑을 순수 규칙으로 분리하고, 실제 적 엔티티 생성만 sim에서
제자리로 수행한다. Day 2의 무기 발사 결과와 디렉터 스폰을 틱 파이프라인(§5.4 4·2단계)에
통합한다.

**산출물**

- `sim/spawn.py`:
  - `director_params(elapsed_sec, defs) -> SpawnParams` (순수). 경과 시간 → 스폰 간격·동시 스폰
    수·적 종류 가중치. 1분 단위 강화 스텝은 balance.toml `[director]` 스텝 테이블 참조.
  - `spawn_enemies(state, params, world, rng) -> None` (sim, **제자리**). 화면 밖 링에서
    적 버퍼에 추가. 엔티티 캡은 Phase 0 작동점(`tuning.toml`) 참조.
- `sim/step.py`: §5.4 파이프라인에 4단계(무기 발사 → 투사체 생성)·2단계(디렉터 스폰) 통합.
  규칙 함수가 반환한 명세를 받아 버퍼에 제자리 삽입.

**OMC 위임:** `executor`(model=opus). 검토: `python-reviewer`(불변성 경계 누출 점검, 별도 패스).

**예상 소요:** 1.0일

**기술 노트**

- 마스터 §5.4: 2단계(director 스폰), 4단계(무기 발사). §7: 디렉터는 경과 시간 기반 스폰율
  상승 + 1분 단위 강화 스텝, 보스/엘리트 후순위.
- 불변성 경계(ADR-001, 절대): `director_params`는 **순수**(시간→파라미터). `spawn_enemies`·
  `step`의 버퍼 갱신만 **제자리**(`sim/` 내부). 가변 상태는 sim step 밖으로 누출 금지.
- 엔티티 캡: **하드코딩 금지**. `tuning.toml`의 Phase 0 산출 entity_cap을 참조. 캡 도달 시
  스폰 스킵 또는 원거리 디스폰 정책(마스터 §3.2).
- 결정적: 스폰 위치·적 종류 추첨은 주입 `random.Random`으로만.

**측정 가능한 종료 조건**

- `python -m pytest tests/test_director.py -q` exit code 0. 포함 케이스:
  - `test_spawn_rate_increases_with_time`: `director_params(0).spawn_interval >
    director_params(300).spawn_interval`(시간 경과 시 스폰 간격 감소 = 스폰율 상승).
  - `test_reinforce_step_at_minute`: 60초 경계 전후 `SpawnParams`가 강화 스텝만큼 달라짐을
    `assertEqual`로 검증.
  - `test_director_params_pure`: 동일 입력 2회 호출 결과 `==`이고 입력 `defs` 불변(deepcopy 비교).
  - `test_spawn_respects_cap`: 적 버퍼가 캡(테스트 주입 tuning 값)에 도달하면 `spawn_enemies`
    후 버퍼 길이가 캡을 초과하지 않음.
- `grep -rEn "import blessed|from blessed" terminal_vs/sim/spawn.py` 결과 0건.
- `grep -rEn "entity_cap\s*=\s*[0-9]" terminal_vs/sim/ terminal_vs/rules/` 결과 0건(캡 하드코딩
  없음, tuning 참조).

---

### Day 6 — render/hud.py 레벨업 드래프트 오버레이 + 상태 연결

**목표**
레벨업/진화 자격 시 시뮬레이션을 일시정지하고 N택 드래프트 선택지를 오버레이로 표시하며,
입력으로 선택을 받아 순수 규칙(`apply_choice`/`apply_evolution`)으로 빌드에 반영한다.

**산출물**

- `render/hud.py`: 레벨업 드래프트 오버레이 렌더(보유 무기/패시브 아이콘, N택 카드 텍스트).
  blessed 의존은 여기까지만(마스터 §13).
- `sim/state.py`: `level_up_pending` 플래그 + 대기 중 후보 보관 필드(가변, sim 경계 내).
- 루프 연결(`loop.py`/`__main__.py`): 마스터 부록 A의 `mode == "levelup"` 분기에서
  `roll_choices` 산출 → 입력 매핑 → `apply_choice` 적용 → `pending` 해제.

**OMC 위임:** `executor`(model=sonnet — 표시·입력 매핑 중심, 규칙은 Day 3~4에서 확정).
검토: `qa-tester`는 Day 7에서 대화형 확인.

**예상 소요:** 1.0일

**기술 노트**

- 마스터 §8: 레벨업 시 일시정지 오버레이로 N택 카드 제시. §5.4: 레벨업 트리거 시 선택 오버레이
  모드로 전환(시뮬레이션 일시정지). 마스터 부록 A `mode` 상태 머신 활용.
- 렌더/로직 분리: 후보 산출·적용은 전부 순수 규칙(Day 3~4). HUD는 표시와 키→인덱스 매핑만.
- 진화 후보는 Day 4 정책대로 드래프트 후보에 주입되어 동일 오버레이로 표시(별도 UI 불필요).
- 성능 수치 비의존: 오버레이는 일시정지 상태라 TPS·뷰포트 작동점에 영향받지 않음.

**측정 가능한 종료 조건**

- `python -m pytest tests/test_levelup_flow.py -q` exit code 0(루프 비의존 순수 흐름). 포함 케이스:
  - `test_levelup_pending_set_on_threshold`: 경험치 임계 도달 시 `state.level_up_pending is True`.
  - `test_choice_index_applies_to_build`: 후보 인덱스 입력 → `apply_choice` 호출 → 빌드에
    해당 무기/패시브 반영을 `assertEqual`로 검증.
  - `test_pending_cleared_after_choice`: 선택 적용 후 `level_up_pending is False`.
- `python -c "import terminal_vs.render.hud"` exit code 0(임포트 스모크).
- `grep -rEn "import blessed|from blessed" terminal_vs/sim/ terminal_vs/rules/` 결과 0건
  (blessed가 render 밖으로 새지 않음).

---

### Day 7 — 헤드리스 결정적 테스트(빌드 분기·진화·디렉터) + qa-tester 대화형 1판

**목표**
"빌드가 갈린다"와 "진화가 발동한다"를 결정적 헤드리스 테스트의 관측 가능한 proxy로 번역해
검증하고, 대화형 한 판에서 진화 발동을 qa-tester가 확인한다.

**산출물**

- `tests/test_build_divergence.py`: 고정 시드로 서로 다른 레벨업 선택 시퀀스 2개를 헤드리스
  시뮬레이션으로 돌려 결과 무기·패시브 집합이 서로 다름 + 한 경로만 진화 자격 도달을 검증.
- `tests/test_evolution_trigger_e2e.py`: 단검+공속 경로를 끝까지 진행해 진화 자격 → 진화 적용
  → 진화 무기 보유까지 헤드리스로 도달.
- `selftest.py` 또는 `tests/` 일괄 실행 진입점이 exit 0.
- qa-tester 대화형 세션 로그: 한 판에서 진화 발동 관측.

**OMC 위임:** `test-engineer`(헤드리스 결정적 테스트 설계·작성) + `qa-tester`(tmux 대화형 1판).

**예상 소요:** 1.0일

**기술 노트**

- "빌드가 갈린다"의 proxy 번역(계약 핵심): 주관적 "재미"가 아니라 **결정적 시드로 두 빌드 경로가
  서로 다른 무기/패시브 집합·서로 다른 진화 결과에 수렴함**을 헤드리스로 assert.
- 경로 A(단검 + 공속 패시브): 진화 자격 도달 → 진화 무기 보유.
  경로 B(마법탄 + 자석 패시브): 다른 무기 집합, 진화 자격 미도달.
- 결정성: 모든 무작위는 주입 `random.Random(seed)`. 동일 시드·동일 선택 시퀀스는 동일 결과.
- 디렉터 곡선: Day 5 단위테스트로 시간→스폰 파라미터 단조성/스텝 검증 완료. 여기서는 통합
  실행으로 누적 스폰 수가 시간에 따라 증가함을 추가 확인.
- 운영 상수 비의존: 헤드리스 테스트는 테스트용 `tuning.toml`(작은 캡/뷰포트)을 주입해 빠르게
  결정적으로 돌린다. Phase 0 작동점과 독립.

**측정 가능한 종료 조건**

- `python -m pytest tests/test_build_divergence.py -q` exit code 0. 핵심 케이스:
  - `test_two_paths_diverge`: 경로 A 결과 무기집합 `frozenset` != 경로 B 결과 무기집합
    (`assertNotEqual`).
  - `test_only_path_a_reaches_evolution`: 경로 A의 `eligible_evolutions` 비어있지 않음 AND
    경로 B의 `eligible_evolutions` 빈 튜플(`assertTrue`/`assertEqual`).
  - `test_same_seed_same_path_reproducible`: 동일 시드·동일 선택 시퀀스 2회 실행 결과
    빌드 상태 `==`(`assertEqual`).
- `python -m pytest tests/test_evolution_trigger_e2e.py -q` exit code 0:
  `test_dagger_path_evolves`가 진화 무기 보유 상태로 종료(`assertIn("dagger_evolved", weapons)`).
- `python -m pytest tests/ -q` 전체 exit code 0(Day 1~7 누적 테스트 회귀 없음).
- qa-tester 대화형 세션: 한 판 플레이 중 진화 발동 오버레이 관측 + 진화 후 무기 글리프 변화를
  세션 로그로 캡처(통과/실패 명시 기록).

---

## 3. 아키텍처·기술 노트

이 phase가 건드리는 마스터 절을 Phase 2 범위로 구체화한다.

### 3.1 콘텐츠 데이터의 config 외부화 (마스터 §5.5)

Phase 2의 핵심은 "콘텐츠 데이터의 config 외부화 + 순수 규칙 판정"이다. 무기·적·진화·패시브·
디렉터·레벨링 상수는 전부 `config/balance.toml` 스키마로 정의하고, `rules/defs.py`가 로드한
불변 데이터로 노출한다. 규칙 계층(`rules/*`)은 전역 접근 대신 이 불변 정의를 **읽기 전용
의존성으로 주입**받아 헤드리스 테스트에서 임의 밸런스를 주입할 수 있다.

- 운영 상수(TPS·뷰포트·엔티티 캡·폴링)는 `tuning.toml` 소관이며 `balance.toml`에 섞지 않는다.
- 누락 키는 코드 기본값 폴백(파일 없어도 첫 실행 보장), 범위 위반은 키 이름을 담은 명확한 에러.

### 3.2 순수 규칙 vs 가변 시뮬레이션 경계 (마스터 §6 / ADR-001)

| 계층 | 책임 | 불변성 |
| --- | --- | --- |
| `rules/weapons.py` | 쿨다운 갱신·타게팅·발사 명세 산출 | 순수, 불변 입출력 |
| `rules/leveling.py` | 경험치 곡선·N택 후보·스탯 적용 | 순수, 새 BuildState 반환 |
| `rules/evolution.py` | 진화 자격 판정·진화 적용 | 순수, 새 BuildState 반환 |
| `rules/defs.py` | 밸런스 테이블 노출 | 불변 데이터 |
| `sim/spawn.py` `director_params` | 시간→스폰 파라미터 | 순수 |
| `sim/spawn.py` `spawn_enemies` | 적 버퍼 생성 | 가변·제자리(sim 내부) |
| `sim/step.py` | 규칙 결과를 버퍼에 제자리 반영 | 가변·제자리(sim 내부) |
| `render/hud.py` | 드래프트 오버레이 표시 | 읽기 전용 + blessed |

경계 규율: 가변 상태는 sim step 밖으로 누출되지 않는다. 규칙·렌더는 버퍼를 읽기 전용으로만
본다. 디렉터는 "시간→파라미터"(순수)와 "엔티티 생성"(제자리)을 분리한다.

### 3.3 틱 파이프라인 확장 (마스터 §5.4)

Phase 1 골격에 다음 두 시스템을 확장한다.

- **2단계(디렉터 스폰):** `director_params(elapsed)` 순수 산출 → `spawn_enemies` 제자리 생성.
  적 2종 가중치·1분 강화 스텝 반영.
- **4단계(무기 발사):** 보유 무기 각각 `tick_weapon` 순수 호출 → 발사 명세 수집 → 투사체 버퍼에
  제자리 삽입. 패시브 공속이 쿨다운에 곱연산으로 반영(`effective_stats`).

8단계(레벨업 트리거)는 `level_up_pending`을 세팅하고, 루프는 마스터 부록 A의 `mode="levelup"`
오버레이로 전환한다(Day 6).

### 3.4 진행 시스템 (마스터 §8)

레벨업 N택 드래프트는 일시정지 오버레이로 신규 무기/기존 강화/패시브를 제시한다. 무기는 레벨이
있고 만렙에서 진화 자격을 얻는다. 진화는 `rules/evolution.py` 순수 판정으로 "무기 만렙 + 짝
패시브 보유"를 검사하며, 자격 충족 진화 후보는 드래프트 후보에 주입되어 동일 오버레이로 표시한다.

### 3.5 성능 수치 비하드코딩 (마스터 §3.3 / §4 / §10 절대 규칙)

본 문서는 TPS·뷰포트·엔티티 캡을 확정하지 않는다. 적 다수 스폰 시 엔티티 캡은 **Phase 0
작동점**(`tuning.toml`)을 따른다. 헤드리스 테스트는 테스트 전용 작은 `tuning.toml`을 주입해
결정적으로 빠르게 실행하며 Phase 0 작동점과 독립이다. balance 상수(쿨다운/데미지/HP/스폰
가중치)는 운영 상수가 아니므로 `balance.toml`로 외부화하며, 이는 하드코딩 금지 대상이 아니다.

---

## 4. Critical Code Specs

의사 Python 코드. helper·util은 생략하고 함수 시그니처·핵심 분기·불변성 경계만 표시한다.
실제 구현은 동일 이름으로 작성한다.

### 4.1 config/balance.toml 스키마 (무기 2종·진화 1종·적 2종 발췌)

```toml
# 밸런스 상수만. 운영 상수(TPS/뷰포트/엔티티 캡)는 tuning.toml 소관 — 여기 넣지 않는다.

[leveling]
draft_choices = 3                 # N택 (밸런스 상수)
xp_curve_base = 5
xp_curve_growth = 1.5             # xp_for_level = base * growth^(level-1) 류

[weapons.dagger]
max_level = 8
cooldown = 1.2                    # 초 단위 발사 간격 (공속 패시브가 곱연산)
damage = 6
projectile_count = 1             # 무기레벨/패시브로 증가
projectile_speed = 14.0
targeting = "nearest"

[weapons.magic_bolt]
max_level = 8
cooldown = 1.8
damage = 9
projectile_count = 1
projectile_speed = 10.0
targeting = "nearest_or_random"   # 동률/임의 추첨은 주입 RNG

[passives.attack_speed]
max_level = 5
multiplier_per_level = 0.92       # 쿨다운에 곱연산(작을수록 빠름)

[passives.move_speed]
max_level = 5
multiplier_per_level = 1.08       # 이동 속도에 곱연산(이속도 동일 패턴)

[passives.magnet]
max_level = 5
pickup_range_mult_per_level = 1.25

[enemies.walker]                  # 느린 기본 추적형(다수)
hp = 10
move_speed = 2.5
spawn_weight = 70

[enemies.swarm]                   # 빠른 약체 떼
hp = 4
move_speed = 5.0
spawn_weight = 30

[evolution.dagger_x]
base = "dagger"
requires_passive = "attack_speed"  # 짝 패시브
base_max_level = 8                 # base 무기 만렙 요구치
result_weapon = "dagger_evolved"

[weapons.dagger_evolved]           # 진화 결과(관통/연사 강화)
max_level = 1
cooldown = 0.6
damage = 10
projectile_count = 3
pierce = 4                         # 관통 수
projectile_speed = 18.0
targeting = "nearest"

[director]
base_spawn_interval = 2.0          # 초기 스폰 간격(초)
min_spawn_interval = 0.4           # 하한
# 1분 단위 강화 스텝: [경과분, 스폰간격배수, 동시스폰수]
reinforce_steps = [
  [0, 1.0, 1],
  [1, 0.8, 2],
  [2, 0.6, 3],
  [3, 0.5, 4],
]
```

### 4.2 rules/defs.py — 불변 밸런스 로드 (마스터 §5.5, §6)

```python
# 모든 정의는 불변. config.py가 검증한 BalanceConfig를 받아 규칙 계층용 테이블로 노출.
from dataclasses import dataclass

@dataclass(frozen=True)
class WeaponDef:
    name: str
    max_level: int
    cooldown: float
    damage: int
    projectile_count: int
    projectile_speed: float
    targeting: str
    pierce: int = 0

@dataclass(frozen=True)
class EvolutionDef:
    name: str
    base: str
    requires_passive: str
    base_max_level: int
    result_weapon: str

@dataclass(frozen=True)
class BalanceDefs:
    weapons: dict[str, WeaponDef]     # 호출부는 읽기 전용으로만 사용
    passives: dict[str, "PassiveDef"]
    enemies: dict[str, "EnemyDef"]
    evolutions: tuple[EvolutionDef, ...]
    director: "DirectorDef"
    leveling: "LevelingDef"

def build_defs(cfg: "BalanceConfig") -> BalanceDefs:
    # 검증된 불변 설정 → 불변 정의 테이블. 순수: 부수효과 없음.
    ...
```

### 4.3 rules/weapons.py — 발사 판정 (순수, 마스터 §5.4 4단계)

```python
# 순수 함수: 입력 스냅샷을 변형하지 않고 발사 명세 + 갱신 쿨다운을 값으로 반환한다.
# 실제 투사체 버퍼 삽입은 sim/step.py가 결과를 받아 제자리로 수행한다(불변성 경계).
from dataclasses import dataclass

@dataclass(frozen=True)
class FireContext:
    player_pos: tuple[float, float]
    player_facing: tuple[float, float]   # 진행 방향(휘두르기 타게팅)
    enemy_positions: tuple[tuple[float, float], ...]  # 읽기 전용 스냅샷
    weapon_def: "WeaponDef"
    attack_speed_mult: float             # effective_stats가 계산한 패시브 곱연산
    dt: float

@dataclass(frozen=True)
class WeaponFireResult:
    fired: bool
    new_cooldown: float
    projectiles: tuple["ProjectileSpec", ...]   # 단검/마법탄: sim이 버퍼에 삽입할 투사체 명세
    instant_hits: tuple["InstantHitSpec", ...] = ()  # 휘두르기: 즉시 피해 명세(투사체 없음)

def tick_weapon(cooldown_remaining: float, ctx: FireContext, rng) -> WeaponFireResult:
    remaining = cooldown_remaining - ctx.dt
    if remaining > 0:
        return WeaponFireResult(fired=False, new_cooldown=remaining,
                                projectiles=(), instant_hits=())
    # targeting == "forward_arc"(휘두르기)는 투사체 대신 즉시 피해 명세(instant_hits)를 반환한다.
    # 그 외(nearest / nearest_or_random)는 투사체 명세(projectiles)를 반환한다.
    if ctx.weapon_def.targeting == "forward_arc":
        hits = _make_forward_arc_hits(ctx)     # 진행 방향 좌우 사거리 안 적만 즉시 히트
        if not hits:
            return WeaponFireResult(fired=False, new_cooldown=0.0,
                                    projectiles=(), instant_hits=())
        reset = ctx.weapon_def.cooldown * ctx.attack_speed_mult
        return WeaponFireResult(fired=True, new_cooldown=reset,
                                projectiles=(), instant_hits=hits)
    target = _select_target(ctx, rng)          # nearest / nearest_or_random
    if target is None:
        return WeaponFireResult(fired=False, new_cooldown=0.0,
                                projectiles=(), instant_hits=())
    specs = _make_projectiles(ctx, target)     # projectile_count/pierce 반영
    reset = ctx.weapon_def.cooldown * ctx.attack_speed_mult  # 공속 패시브 곱연산
    return WeaponFireResult(fired=True, new_cooldown=reset,
                            projectiles=specs, instant_hits=())
```

### 4.4 rules/leveling.py — N택 후보 산출 (순수, 마스터 §8)

```python
# 순수: 동일 시드·동일 빌드 상태 → 동일 후보. apply는 새 불변 BuildState 반환.
@dataclass(frozen=True)
class BuildState:
    weapon_levels: tuple[tuple[str, int], ...]    # (name, level), 불변
    passive_levels: tuple[tuple[str, int], ...]
    xp: int
    level: int

def xp_for_level(level: int, defs: "BalanceDefs") -> int:
    ...                                            # 단조 증가 곡선

def roll_choices(build: BuildState, defs: BalanceDefs, rng, n: int) -> tuple["Choice", ...]:
    pool = []
    pool += _weapon_upgrade_candidates(build, defs)   # 만렙 무기 제외
    pool += _new_weapon_candidates(build, defs)
    pool += _passive_candidates(build, defs)          # 만렙 패시브 제외
    pool += _eligible_evolution_choices(build, defs)  # 진화 자격 시 후보 주입(Day 4 정책)
    if not pool:
        pool = _fallback_candidates(defs)             # 고갈 시 결정적 폴백
    return _weighted_sample(pool, rng, n)             # 주입 RNG로 결정적 추출

def apply_choice(build: BuildState, choice: "Choice") -> BuildState:
    # 새 BuildState 반환(전역 immutable 규약). 입력 build는 변형하지 않음.
    ...
```

### 4.5 rules/evolution.py — 진화 자격 판정 (순수, 마스터 §8)

```python
# 순수 판정: "base 무기 만렙 + 요구 패시브 보유"를 진화 정의 테이블로 순회 검사.
def eligible_evolutions(build: "BuildState", defs: "BalanceDefs") -> tuple["EvolutionDef", ...]:
    out = []
    weapon_lv = dict(build.weapon_levels)
    passive_lv = dict(build.passive_levels)
    for evo in defs.evolutions:
        base_lv = weapon_lv.get(evo.base, 0)
        has_passive = passive_lv.get(evo.requires_passive, 0) > 0
        if base_lv >= evo.base_max_level and has_passive:
            out.append(evo)
    return tuple(out)

def apply_evolution(build: "BuildState", evo: "EvolutionDef") -> "BuildState":
    # base 무기 제거 + result_weapon 추가. 새 불변 BuildState 반환.
    ...
```

### 4.6 sim/spawn.py — 디렉터 (순수 규칙 + 제자리 생성 분리, 마스터 §5.4 2단계)

```python
# 순수: 시간 → 스폰 파라미터. 가변: 적 버퍼 생성만 sim 내부 제자리.
@dataclass(frozen=True)
class SpawnParams:
    spawn_interval: float
    concurrent: int
    enemy_weights: tuple[tuple[str, int], ...]

def director_params(elapsed_sec: float, defs: "BalanceDefs") -> SpawnParams:
    step = _current_reinforce_step(elapsed_sec, defs.director)  # 1분 단위 스텝
    interval = max(defs.director.min_spawn_interval,
                   defs.director.base_spawn_interval * step.interval_mult)
    return SpawnParams(interval, step.concurrent, defs.director.enemy_weights)

def spawn_enemies(state, params: SpawnParams, world, rng) -> None:
    # 가변·제자리(sim 내부 한정). 엔티티 캡은 tuning.toml(Phase 0 산출) 참조 — 하드코딩 금지.
    if len(state.enemies) >= world.entity_cap:    # cap은 tuning에서 주입된 값
        return
    for _ in range(params.concurrent):
        kind = _weighted_pick(params.enemy_weights, rng)
        pos = _ring_spawn_position(world, rng)    # 화면 밖 링
        state.enemies.append(_make_enemy(kind, pos))   # 제자리 추가
```

---

## 5. Acceptance Criteria

| # | 기준 | 검증 절차 | 통과 |
| --- | --- | --- | --- |
| AC1 | 무기 3종·패시브 2~3종·진화 1종·적 2종·디렉터 곡선이 balance.toml로 구동된다(코드 하드코딩 없음) | `grep -rEn "(cooldown\|damage\|hp\|move_speed\|spawn_weight)\s*=\s*[0-9]" terminal_vs/rules/ terminal_vs/sim/` 결과 0건 + `python -m pytest tests/test_config_balance.py -q` exit 0 | [ ] |
| AC2 | 밸런스 정의가 불변으로 주입된다 | `tests/test_config_balance.py::test_load_balance_returns_immutable` 통과(필드 재할당 예외) | [ ] |
| AC3 | 무기 3종 발사·타게팅이 순수·결정적이다 | `python -m pytest tests/test_weapons.py -q` exit 0(타게팅·쿨다운·순수성·결정성 5케이스) | [ ] |
| AC4 | 레벨업 N택 후보가 결정적으로 산출되고 만렙은 제외된다 | `python -m pytest tests/test_leveling.py -q` exit 0 | [ ] |
| AC5 | 진화 자격 판정이 정확하다(만렙+짝 패시브만 자격) | `tests/test_evolution.py`의 자격 3케이스(`eligible`/`not_without_passive`/`not_when_not_maxed`) exit 0 | [ ] |
| AC6 | 디렉터가 시간에 따라 스폰율을 올리고 1분 강화 스텝을 적용한다 | `python -m pytest tests/test_director.py -q` exit 0(단조성·스텝·순수성·캡 준수) | [ ] |
| AC7 | "빌드가 갈린다": 서로 다른 선택 경로가 서로 다른 무기 집합에 수렴한다 | `tests/test_build_divergence.py::test_two_paths_diverge` 및 `::test_only_path_a_reaches_evolution` exit 0 | [ ] |
| AC8 | 진화 발동이 헤드리스로 도달 가능하다 | `tests/test_evolution_trigger_e2e.py::test_dagger_path_evolves`가 `dagger_evolved` 보유로 종료 | [ ] |
| AC9 | 규칙·시뮬레이션 계층이 blessed에 비의존이다 | `grep -rEn "import blessed\|from blessed" terminal_vs/rules/ terminal_vs/sim/` 결과 0건 | [ ] |
| AC10 | 성능 운영 상수가 balance/규칙/sim에 하드코딩되지 않는다 | `grep -rEn "(sim_tps\|viewport\|entity_cap\|poll_timeout)\s*=\s*[0-9]" terminal_vs/rules/ terminal_vs/sim/ config/balance.toml` 결과 0건 | [ ] |
| AC11 | 전체 헤드리스 테스트가 회귀 없이 통과한다 | `python -m pytest tests/ -q` exit code 0 | [ ] |
| AC12 | 대화형 한 판에서 진화 발동이 관측된다 | qa-tester tmux 세션 로그에 진화 오버레이 + 진화 후 무기 글리프 변화 캡처(통과/실패 명시) | [ ] |

---

## 6. Risks & Mitigations

| 위험 | 가능성 | 영향 | 완화 |
| --- | --- | --- | --- |
| balance.toml 스키마가 하류 규칙과 어긋나 재작업 발생 | 중 | 높음 | Day 1에 스키마 확정 후 defs 불변 로드 테스트로 고정. 무기/진화 추가는 코드 수정 없이 테이블 확장만 되도록 데이터 주도 설계 |
| "빌드가 갈린다"가 주관적이라 종료 조건이 모호해짐 | 중 | 높음 | 결정적 시드 기반 분기 테스트로 proxy 번역(서로 다른 무기 집합 수렴 + 한 경로만 진화 자격). AC7/AC8로 박음 |
| 진화 후보 주입 정책(드래프트 합류 vs 즉시) 혼선 | 중 | 중 | Day 4에서 "드래프트 후보 주입" 단일 정책 채택, Day 6 오버레이 재사용. evolution 테스트는 자격 판정만 검증해 UI 정책과 분리 |
| 후보 고갈(전 무기·패시브 만렙) 시 드래프트 비결정·빈 후보 | 중 | 중 | `_fallback_candidates` 결정적 폴백 명시. `test_roll_choices_deterministic`로 고갈 경계 검증 |
| 디렉터 스폰이 엔티티 캡을 무시해 Phase 0 작동점 위반 | 중 | 높음 | `spawn_enemies`가 tuning 캡 참조 후 스킵. `test_spawn_respects_cap`로 검증. 캡 하드코딩 금지(AC10) |
| 불변성 경계 누출(규칙 함수가 입력 스냅샷 변형) | 중 | 중 | 각 규칙 테스트에 deepcopy 전후 비교 `*_is_pure` 케이스 포함. python-reviewer 별도 패스 |
| 패시브 곱연산 적용 위치 불일치(쿨다운 vs 발사 수) | 중 | 중 | `effective_stats` 단일 지점에서 스탯 합성, `tick_weapon`은 곱연산된 값만 사용. `test_passive_multiplies_stats`로 고정 |
| blessed 의존이 sim/rules로 새어 헤드리스 테스트 불가 | 낮음 | 높음 | AC9 grep 게이트 + 임포트 스모크. render/·__main__만 blessed |

---

## 7. Exit Gate (다음 phase로 진행 체크리스트)

마스터 §10 Phase 2 Exit("한 판에서 빌드가 갈리고 진화가 발동")을 구체화한다. 아래 전부 충족 시
Phase 3(폴리시 & 검증)로 진행한다.

- [ ] 무기 3종(단검·휘두르기·마법탄)·패시브 2~3종(공속·이속·자석)·진화 1종(dagger_evolved)·
  적 2종(walker·swarm)·디렉터 곡선이 모두 `config/balance.toml`로 구동된다 (AC1).
- [ ] `python -m pytest tests/ -q` 전체 exit code 0 (AC11).
- [ ] 진화 자격 판정 3케이스(만렙+짝 패시브만 자격)가 통과한다 (AC5).
- [ ] 레벨링 결정성·만렙 제외 테스트가 통과한다 (AC4).
- [ ] 빌드 분기 proxy 테스트가 통과한다: 서로 다른 선택 경로 → 서로 다른 무기 집합 + 한 경로만
  진화 자격 도달 (AC7).
- [ ] 진화 발동 헤드리스 e2e가 `dagger_evolved` 보유로 종료한다 (AC8).
- [ ] 디렉터 시간→스폰 곡선 단조성·1분 강화 스텝·캡 준수 테스트가 통과한다 (AC6).
- [ ] `grep` 게이트: 규칙·sim 계층 blessed 비의존 0건(AC9) + 성능 상수 하드코딩 0건(AC10) +
  밸런스 수치 하드코딩 0건(AC1).
- [ ] 대화형 한 판에서 진화 발동이 qa-tester 세션 로그로 관측된다 (AC12).
- [ ] 적 다수 스폰 시 엔티티 캡이 Phase 0 작동점(`tuning.toml`)을 따른다(본 phase에서 캡 수치를
  새로 확정하지 않음).
