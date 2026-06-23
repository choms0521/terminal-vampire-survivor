# Phase 3 상세개발 계획 — 폴리시 & 검증

작성일: 2026-06-23
대상 레포: `terminal-vampire-survivor`
상위 문서: `docs/plan/2026-06-23/work-plan-v1.md` (마스터 계획서 v1)
대상 단계: 마스터 §10 **Phase 3 — 폴리시 & 검증**

> 이 문서는 마스터 계획서 §10의 Phase 3 항목("HUD/오버레이 완성, 밸런스 1차, 게임오버/재시작, 헤드리스 셀프테스트")을 day-by-day 실행 계획으로 구체화한다.
> 성능 수치(시뮬레이션 TPS, 뷰포트 크기, 엔티티 캡, 프레임 타이밍)는 **Phase 0 산출값**이며 `config/tuning.toml`에서 읽는다. 이 문서는 그 수치들을 하드코딩하지 않는다(§3.3, §4, §10 절대 규칙).

---

## 1. 개요

### Goal

규칙 계층을 결정적으로 검증하는 **헤드리스 셀프테스트 인프라**를 구축하고, **HUD/오버레이를 3모드(레벨업·일시정지·게임오버)로 완성**하며, **balance.toml 편집만으로 난이도 곡선을 조정하는 1차 밸런스 절차**를 확립한다. 한 판을 완주 가능한 상태로 만들어 게임오버·재시작 흐름을 닫는다.

이 단계의 핵심은 **검증 인프라 + UI 완성 + 1차 밸런스**다. 새 콘텐츠(무기/적/진화)는 추가하지 않는다(Phase 2 책임).

### Scope

**In scope**

- `tests/` (또는 `selftest.py`) 헤드리스 테스트 스위트: rules 계층(`weapons`/`damage`/`evolution`/`leveling`) 결정적 단위테스트.
- `config.py` 로드·스키마/범위 검증 테스트(누락 키 폴백, 잘못된 값 에러).
- import smoke 테스트(모든 모듈 import 시 터미널 미기동·루프 미진입 확인).
- 헤드리스 시뮬레이션 드라이버(스크립트화된 입력 + 주입 RNG)로 게임오버까지 도달하는 **완주 회귀 테스트**.
- `render/hud.py`: HUD 요소(HP 바, 레벨·경험치 바, 생존 타이머, 보유 무기/패시브 아이콘, 킬 수) 완성.
- 오버레이 3모드(`levelup`/`pause`/`gameover`) 합성·전환. 게임오버 → 재시작 흐름.
- 레이어 합성 우선순위 확립(바닥→픽업→적→탄막→플레이어→HUD/오버레이), 플레이어 항상 최상위(§3.5).
- balance.toml 편집만으로 난이도가 바뀜을 증명하는 1차 밸런스 절차·테스트.
- pytest + pytest-cov 개발 의존성 추가, 커버리지 측정 명령 확립.

**Out of scope**

- 새 무기/적/진화/패시브 추가(Phase 2 또는 Phase 4).
- 메타 진행·영구 저장·언락(Phase 4, §8 메타 진행 후보).
- 사운드, 보스/엘리트(Phase 4).
- 성능 최적화·Phase 0 수치 재측정(diff 렌더 알고리즘 자체 변경 등). 이 단계는 Phase 0 산출값을 소비만 한다.
- 대화형 UI 루프(`loop.py`)의 자동화 E2E. UI 루프는 대화형이므로 헤드리스 검증 대상에서 분리하고(§13), 완주는 헤드리스 시뮬레이션 드라이버 + qa-tester(tmux) 수동 확인으로 대신한다.

### Key Deliverables

| # | 산출물 | 위치 |
| --- | --- | --- |
| KD1 | 헤드리스 테스트 스위트 — Phase 1·2가 산출한 rules 단위테스트의 **확장·커버리지 보강**(신규 작성 아님) | `tests/test_weapons.py`, `tests/test_damage.py`, `tests/test_evolution.py`, `tests/test_leveling.py` (기존 스위트) |
| KD2 | config 로드·검증 테스트 | `tests/test_config.py` |
| KD3 | import smoke 테스트 | `tests/test_import_smoke.py` |
| KD4 | 헤드리스 완주 회귀 테스트 + 시뮬레이션 드라이버 | `tests/test_full_run.py`, `tests/support/sim_driver.py` |
| KD5 | 셀프테스트 엔트리(exit 0 계약) | `selftest.py` (또는 `pytest` 설정 + `run.sh` 통합) |
| KD6 | HUD/오버레이 완성 | `render/hud.py`, `render/frame.py` (레이어 합성 순수 부분) |
| KD7 | 1차 밸런스 절차 + 밸런스 민감도 테스트 | `tests/test_balance_sensitivity.py`, `config/balance.toml` 갱신 |
| KD8 | 개발 의존성·테스트 실행 설정 | `requirements-dev.txt`, `pyproject.toml` 또는 `pytest.ini`, `run.sh` |

### Dependencies

- **Entry gate (Phase 2 exit)**: 무기 3종·패시브 2~3종·진화 1종·적 2종·디렉터 난이도 곡선이 `balance.toml`로 구동되고, 헤드리스 테스트가 통과하며, 진화 발동이 관측됨. (마스터 §10 Phase 2 Exit)
- `rules/*`가 순수 함수 + 불변 값으로 구현되어 있고 설정을 읽기 전용 의존성으로 주입받음(§6, §5.5). Phase 3 테스트는 이 주입 가능성에 의존한다.
- `config.py`가 로드·검증해 불변 설정 객체를 반환함(§5.5).
- `sim/step.py`가 결정적(주입 RNG)으로 한 틱을 전진시킴(§5.4). 완주 드라이버가 이를 호출한다.
- Phase 0 산출값이 `config/tuning.toml`에 확정되어 있음(TPS·뷰포트·엔티티 캡 등).

### Effort

| 항목 | 추정 |
| --- | --- |
| 총 기간 | 6 Day (Day 1~6) |
| 위임 agent | `test-engineer`(테스트 스위트), `executor`(HUD/오버레이 구현), `verifier`(커버리지·게이트 검증), `qa-tester`(tmux 완주 확인), `code-reviewer`(검증 패스) |
| 임계 경로 | Day 1(테스트 기반) → Day 2(rules 단위테스트) → Day 4(완주 드라이버) → Day 6(Exit 게이트) |

---

## 2. Day-by-Day Work Package

각 Day는 측정 가능한 종료 조건을 가진다. 종료 조건은 실행 가능한 명령과 수치로만 기술한다.

> 표기 규약: 아래 명령에서 `<rules-cov-target>`는 `--cov=terminal_vs.rules --cov=terminal_vs.config`를 의미한다. 커버리지 목표는 **rules 계층 + config 로더 + 순수 frame 합성 로직**에만 적용한다. blessed 의존 렌더 I/O와 대화형 루프는 헤드리스 측정 대상이 아니다(§13).

---

### Day 1 — 테스트 인프라·import smoke·config 검증 (기반)

**목표**
헤드리스 테스트 실행 골격을 세운다. pytest + pytest-cov 개발 의존성을 추가하고, `selftest.py` exit 0 계약을 정의한다. import smoke와 config 로드·검증 테스트로 기반을 닫는다.

**산출물**

- `requirements-dev.txt` (`pytest`, `pytest-cov` 포함).
- `pytest.ini` 또는 `pyproject.toml`의 `[tool.pytest.ini_options]` (testpaths, addopts에 `--cov` 기본 포함).
- `selftest.py`: 헤드리스 진입점. 내부에서 `pytest.main([...])`를 호출하고 그 반환 코드를 프로세스 종료 코드로 그대로 전파(통과 시 exit 0).
- `tests/test_import_smoke.py`: `terminal_vs` 하위 모든 모듈(`render/*`, `__main__` 포함)을 import해도 터미널이 기동되지 않고 루프에 진입하지 않음을 확인.
- `tests/test_config.py`: 정상 TOML 로드, 누락 키 → 코드 기본값 폴백, 잘못된 값 → 명확한 예외.

**OMC 위임**: `test-engineer` (스위트 골격·import smoke·config 테스트 작성), `executor` (필요 시 `selftest.py`·`pytest.ini` 작성).

**예상 소요**: 1 Day.

**기술 노트**

- import smoke가 성립하려면 **모듈 import 시 부수효과로 터미널을 열거나 루프에 진입하면 안 된다.** 터미널 셋업과 루프 진입은 `__main__.py`의 `main()` 함수와 `if __name__ == "__main__":` 가드 뒤에 둔다. 그래야 `python -c "import terminal_vs.__main__"`이 실제 exit 0 스모크가 된다. 이 제약이 위반되면 Day 1 종료 조건이 실패하므로 여기서 회귀를 잡는다.
- config 테스트는 임시 TOML 파일(`tmp_path` fixture)로 케이스를 구성한다. 전역 파일에 의존하지 않는다(§5.5 주입 원칙).
- 커버리지 스코프는 `terminal_vs.rules` 패키지와 `terminal_vs.config` 모듈로 한정한다(dotted 모듈 형식 사용 — 최상위 `config/` 디렉토리와 혼동하지 않는다). 전체 프로젝트 % 목표는 두지 않는다(blessed 렌더·대화형 루프는 측정 제외).

**측정 가능한 종료 조건**

- [ ] `python -c "import terminal_vs.__main__, terminal_vs.loop, terminal_vs.render.frame, terminal_vs.render.hud, terminal_vs.world, terminal_vs.config"` 실행 시 exit code 0, 터미널 화면 변화 없음(stdout에 escape 시퀀스 0건: `python -c "..." | grep -c $'\x1b'` 결과 0).
- [ ] `python -m pytest tests/test_import_smoke.py tests/test_config.py` exit code 0.
- [ ] `tests/test_config.py`에 최소 3개 테스트 존재: 정상 로드 1건, 누락 키 폴백 1건, 잘못된 값 예외 1건 (`grep -cE 'def test_' tests/test_config.py` 결과 ≥ 3).
- [ ] `python -m pytest --collect-only` exit code 0 (수집 에러 0건).
- [ ] `requirements-dev.txt`에 `pytest`와 `pytest-cov`가 존재 (`grep -E '^pytest($|[>=~])' requirements-dev.txt` 1건, `grep -E '^pytest-cov' requirements-dev.txt` 1건).

---

### Day 2 — rules 계층 결정적 단위테스트 (weapons / damage)

**목표**
규칙 계층의 "두뇌" 중 전투 핵심인 `weapons.py`와 `damage.py`를 결정적으로 검증한다. 주입 RNG와 주입 설정으로 동일 입력 → 동일 출력을 고정한다.

**산출물**

- `tests/test_weapons.py`: 무기 타게팅(최근접 적 선택), 쿨다운 갱신·발사 판정, 투사체 생성 규칙(수/속도/방향)을 순수 함수로 검증.
- `tests/test_damage.py`: 데미지 계산, 넉백 방향·크기, 사망 임계(HP ≤ 0) 판정.
- 공용 fixture: `tests/conftest.py`에 결정적 `random.Random(seed)`와 테스트용 불변 설정 객체 빌더.

**OMC 위임**: `test-engineer`.

**예상 소요**: 1 Day.

**기술 노트**

- rules 계층은 `blessed` 비의존(§13). 테스트는 blessed import 없이 동작한다.
- 타게팅·발사 같은 RNG 의존 경로는 `random.Random(seed)` 주입으로 고정한다(§13 결정성). 동일 시드 → 동일 투사체 목록을 단언한다.
- 데미지/넉백은 순수 계산이므로 입력→출력 테이블 테스트로 작성한다(부수효과 없음, §6 순수·불변 경계).
- 밸런스 상수는 테스트용 주입 설정에서 읽는다. 테스트가 `balance.toml` 실파일에 의존하지 않게 한다(결정성·격리).

**측정 가능한 종료 조건**

- [ ] `python -m pytest tests/test_weapons.py tests/test_damage.py` exit code 0.
- [ ] 동일 시드 결정성 테스트 존재: 동일 `random.Random(seed)`로 발사를 2회 호출해 결과가 동등함을 단언하는 케이스 ≥ 1 (`grep -cE 'Random\(' tests/test_weapons.py` ≥ 1).
- [ ] `python -m pytest tests/test_weapons.py tests/test_damage.py --cov=terminal_vs.rules.weapons --cov=terminal_vs.rules.damage --cov-report=term-missing` 실행 시 두 모듈 라인 커버리지 각각 ≥ 80%.
- [ ] `weapons.py`·`damage.py` 테스트 함수 합계 ≥ 8 (`grep -cE 'def test_' tests/test_weapons.py tests/test_damage.py` 합 ≥ 8).

---

### Day 3 — rules 계층 결정적 단위테스트 (evolution / leveling)

**목표**
성장 루프의 두 규칙 `evolution.py`(진화 자격 판정)와 `leveling.py`(경험치 곡선·레벨업 선택지)를 결정적으로 검증한다.

**산출물**

- `tests/test_evolution.py`: "무기 만렙 + 짝 패시브 보유" 자격 충족/미충족 경계 케이스, 진화 선택지 산출.
- `tests/test_leveling.py`: 경험치 곡선(레벨당 필요량 증가), 레벨업 트리거 임계, N택 선택지 생성(주입 RNG로 후보 결정성).

**OMC 위임**: `test-engineer`.

**예상 소요**: 1 Day.

**기술 노트**

- 진화 자격은 순수 판정(§8). 자격 경계(만렙 직전 vs 만렙, 패시브 미보유 vs 보유)를 명시적 케이스로 둔다.
- 레벨업 선택지 생성이 RNG에 의존하면 주입 시드로 후보 목록을 고정해 단언한다.
- 경험치 곡선은 단조 증가 등 불변식(invariant)을 단언한다(레벨 n+1 필요량 > 레벨 n).

**측정 가능한 종료 조건**

- [ ] `python -m pytest tests/test_evolution.py tests/test_leveling.py` exit code 0.
- [ ] 진화 자격 경계 케이스 ≥ 2 (충족 1건 + 미충족 1건), 레벨업 곡선 단조성 단언 ≥ 1.
- [ ] `python -m pytest tests/test_evolution.py tests/test_leveling.py --cov=terminal_vs.rules.evolution --cov=terminal_vs.rules.leveling --cov-report=term-missing` 실행 시 두 모듈 라인 커버리지 각각 ≥ 80%.
- [ ] rules 계층 전체 누적 커버리지 측정: `python -m pytest tests/ --cov=terminal_vs.rules --cov-report=term` 실행 시 `terminal_vs/rules` 패키지 라인 커버리지 ≥ 80%.

---

### Day 4 — 헤드리스 완주 회귀 테스트 (한 판 완주의 측정 proxy)

**목표**
"한 판 완주 가능"(마스터 §10 Phase 3 Exit)을 객관적으로 측정한다. 결정적 시드 + 스크립트화된 입력으로 게임오버 상태까지 도달하는 헤드리스 시뮬레이션 드라이버를 만들고 회귀 테스트로 고정한다.

**산출물**

- `tests/support/sim_driver.py`: 주입 `random.Random(seed)`와 스크립트화된 입력 시퀀스(예: 고정 방향 이동 패턴)를 받아 `sim/step.py`를 반복 호출하는 헤드리스 드라이버. blessed 비의존.
- `tests/test_full_run.py`: 드라이버를 돌려 (a) 게임오버 상태 도달, (b) 도달 전까지 예외 미발생, (c) 상한 틱 수 내 종료를 단언.

**OMC 위임**: `test-engineer` (드라이버·회귀 테스트), `executor` (드라이버가 요구하는 sim 진입점 정리 필요 시).

**예상 소요**: 1 Day.

**기술 노트**

- 완주의 측정 proxy는 "재미있게 돌아간다" 같은 주관 표현이 아니라 **종료 상태 코드·도달 상태**로 번역한다(SHARED CONTRACT). 단언 대상: `sim.player.hp <= 0`(게임오버) 도달, 도달 전 예외 0건, 소비 틱 수 ≤ 상한.
- 상한 틱 수는 성능 수치가 아니라 **회귀 가드용 안전 상한**이다(무한 루프 방지). 한 판 길이 자체는 `balance.toml`/`tuning.toml`이 규정하므로, 상한은 "기대 게임오버 틱 × 여유 배수"로 config에서 유도하거나 테스트 상수로 둔다. TPS·뷰포트는 드라이버가 `config`에서 읽고 하드코딩하지 않는다.
- 드라이버는 렌더를 호출하지 않는다. `sim/step.py`만 구동해 규칙·시뮬레이션 경계만 검증한다(§6). 렌더는 Day 5에서 순수 부분만 별도 검증.
- 입력 시퀀스는 결정적이어야 한다. 동일 시드 + 동일 입력 스크립트 → 동일 종료 틱 수를 재현 가능해야 한다.

**측정 가능한 종료 조건**

- [ ] `python -m pytest tests/test_full_run.py` exit code 0.
- [ ] 완주 테스트가 게임오버 도달을 명시적으로 단언 (`grep -E 'hp <= 0|game.?over|GAMEOVER' tests/test_full_run.py` 1건 이상).
- [ ] 결정성 재현 테스트: 동일 시드 + 동일 입력 스크립트로 드라이버를 2회 실행해 종료 틱 수가 동일함을 단언하는 케이스 ≥ 1.
- [ ] 드라이버 실행이 상한 틱 수 내에 종료(테스트가 상한 초과 시 실패하도록 단언). `python -m pytest tests/test_full_run.py` 의 wall-clock 실행 시간 `time` 측정 시 단일 완주 테스트 < 10초.
- [ ] `tests/support/sim_driver.py`가 blessed를 import하지 않음 (`grep -c 'blessed' tests/support/sim_driver.py` 결과 0).

---

### Day 5 — HUD/오버레이 완성 + 레이어 합성 순수 부분 테스트

**목표**
`render/hud.py`와 `render/frame.py`의 HUD 요소·오버레이 3모드를 완성한다. blessed I/O와 순수 합성 로직을 분리하고, 순수 부분만 헤드리스로 검증한다.

**산출물**

- `render/hud.py`: HP 바, 레벨·경험치 바, 생존 타이머, 보유 무기/패시브 아이콘, 킬 수(§9 HUD). 오버레이 3모드(`levelup` 선택 카드, `pause` 안내, `gameover` 재시작 안내).
- `render/frame.py`: 레이어 합성 우선순위(바닥→픽업→적→탄막→플레이어→HUD/오버레이, §3.5). 플레이어 항상 최상위 보장.
- 합성 로직의 **순수 부분**(셀 버퍼 합성·우선순위 적용·HUD 문자열 생성)을 blessed 비의존 함수로 분리.
- `tests/test_frame_compose.py`, `tests/test_hud_render.py`: 순수 합성 로직 단위테스트.

**OMC 위임**: `executor` (HUD/오버레이·합성 구현), `designer` (HUD 레이아웃·글리프/색 규칙, 선택적), `test-engineer` (순수 합성 테스트).

**예상 소요**: 1 Day.

**기술 노트**

- **렌더/테스트 경계(핵심):** `render/`는 blessed 의존이므로(§13) 헤드리스 테스트는 **순수 합성 로직만** 대상으로 한다. 합성 함수는 "엔티티/HUD 데이터 → 2차원 셀 버퍼(문자+색 코드) 또는 문자열 행 목록"을 반환하는 순수 함수로 두고, 이 반환값을 blessed로 실제 출력하는 부분은 분리한다. 테스트는 반환된 버퍼/문자열을 단언한다(blessed 미호출).
- 플레이어 최상위 규칙(§3.5)은 합성 순수 함수에서 검증한다: 동일 셀에 적·탄막·플레이어가 겹칠 때 결과 셀이 플레이어 글리프임을 단언.
- 오버레이 모드 전환은 순수 합성 입력의 `mode` 인자로 표현한다(`"levelup"`/`"pause"`/`"gameover"`). 각 모드가 서로 다른 오버레이 문자열을 생성함을 단언한다.
- 깜빡임 없는 렌더(§3.6)·diff 렌더는 Phase 0/하위 단계 책임이며, 이 단계는 합성 우선순위·HUD 내용만 다룬다. diff 알고리즘 자체는 변경하지 않는다.

**측정 가능한 종료 조건**

- [ ] `python -m pytest tests/test_frame_compose.py tests/test_hud_render.py` exit code 0.
- [ ] 레이어 우선순위 테스트 존재: 동일 셀에 적+탄막+플레이어 겹침 → 결과 셀이 플레이어 글리프임을 단언 (`grep -iE 'priority|overlap|player.*top|top.*player' tests/test_frame_compose.py` 1건 이상).
- [ ] 오버레이 3모드 각각의 합성 출력이 서로 다름을 단언하는 테스트 ≥ 3 (`levelup`/`pause`/`gameover` 각 1건; `grep -cE 'levelup|pause|gameover' tests/test_hud_render.py` ≥ 3).
- [ ] HUD 요소 5종(HP/레벨·경험치/타이머/무기·패시브 아이콘/킬 수) 각각이 합성 출력에 포함됨을 단언하는 케이스 존재 (요소별 단언 ≥ 5).
- [ ] 순수 합성 모듈이 blessed를 직접 import하지 않는 함수 경계를 가짐: 테스트 파일이 blessed를 import하지 않음 (`grep -c 'import blessed\|from blessed' tests/test_frame_compose.py tests/test_hud_render.py` 결과 0).

---

### Day 6 — 1차 밸런스 + Exit 게이트 통합

**목표**
balance.toml 편집만으로 난이도가 바뀜을 증명하는 1차 밸런스 절차를 확립하고, Phase 3 Exit 게이트를 통합 검증한다. 게임오버 → 재시작 흐름을 qa-tester로 대화형 확인한다.

**산출물**

- `tests/test_balance_sensitivity.py`: 동일 시드 + 동일 입력 스크립트로, `balance.toml` 파라미터(예: 적 HP 또는 디렉터 스폰율)를 변경했을 때 완주 결과(생존 틱 수/킬 수)가 달라짐을 단언. 코드 수정 없이 설정 주입만으로 분기.
- `config/balance.toml` 1차 밸런스 조정안(난이도 곡선 1차 튜닝).
- `run.sh` 또는 `selftest.py`에 통합된 전체 셀프테스트 진입점(전 스위트 + 커버리지).
- qa-tester(tmux) 완주 세션 로그: 게임오버 도달 → 재시작 → 재진행 확인.

**OMC 위임**: `test-engineer` (밸런스 민감도 테스트), `executor` (balance.toml 조정·게임오버/재시작 흐름 마감), `verifier` (Exit 게이트 통합 검증·커버리지 집계), `qa-tester` (tmux 대화형 완주·재시작 확인), `code-reviewer` (검증 패스, 작성과 분리된 리뷰 lane).

**예상 소요**: 1 Day.

**기술 노트**

- 밸런스 민감도 테스트는 **코드 변경 없이 config 주입만으로** 결과가 바뀜을 증명하는 것이 목적이다(§5.5, §12 밸런스 붕괴 완화: 데이터 주도 밸런스 + 주입 RNG 결정적 테스트). 두 설정 객체(baseline vs mutated 한 파라미터)를 같은 드라이버에 주입해 결과 차이를 단언한다.
- qa-tester 완주 확인은 헤드리스로 불가능한 **대화형 UI 루프**의 보강이다. exit 상태는 헤드리스 드라이버(Day 4)가, 사람이 보는 화면 흐름은 qa-tester가 본다. qa-tester 결과도 "게임오버 화면 도달", "재시작 키 입력 후 play 모드 재진입" 같은 **상태 도달**로 기록한다.
- Exit 게이트는 마스터 §10 Phase 3 Exit("selftest exit 0, 임포트 스모크 통과, 한 판 완주 가능")에 SHARED CONTRACT의 HUD/오버레이 3모드 전환 확인을 더한다.
- 검증 패스(verifier/code-reviewer)는 작성 패스와 **분리된 lane**에서 수행한다(자기 승인 금지).

**측정 가능한 종료 조건**

- [ ] `python -m pytest tests/test_balance_sensitivity.py` exit code 0.
- [ ] 밸런스 민감도 테스트가 동일 시드에서 baseline vs mutated 결과 차이를 단언 (생존 틱 수 또는 킬 수가 유의하게 다름; `grep -iE 'assert.*!=|assert.*<|assert.*>' tests/test_balance_sensitivity.py` 1건 이상). 테스트 내에서 `terminal_vs/rules` 또는 `sim/` 소스 파일은 수정되지 않음(설정 객체 주입만 사용).
- [ ] `python selftest.py` exit code 0 (전 스위트 통과). 또는 동등하게 `python -m pytest tests/` exit code 0.
- [ ] `python -m pytest tests/ --cov=terminal_vs.rules --cov=terminal_vs.config --cov-report=term --cov-fail-under=80` exit code 0 (rules + config 라인 커버리지 ≥ 80%).
- [ ] qa-tester tmux 세션에서 (a) 게임오버 화면 도달, (b) 재시작 입력 후 play 모드 재진입, (c) HUD 3모드(levelup/pause/gameover) 전환을 각각 관측·기록(세션 로그에 3모드 전환 시각 기재).

---

## 3. 아키텍처·기술 노트

이 단계가 건드리는 마스터 절을 구체화한다.

### 3.1 헤드리스 검증 경계 (§13)

- **검증 대상(헤드리스):** `rules/*`(순수 함수), `config.py`(로드·검증), `sim/step.py`·`sim/state.py`를 구동하는 완주 드라이버, `render/`의 **순수 합성 함수**, 모든 모듈의 import smoke.
- **검증 제외(대화형):** `loop.py`의 대화형 입력 폴링 루프, blessed 실제 출력(`term.home`, escape 시퀀스 방출). 이 부분은 qa-tester(tmux) 수동 확인으로 보강한다.
- 경계 근거: 규칙·시뮬레이션·합성 로직은 결정적·순수이므로 단위테스트로 회귀를 잡고, blessed I/O와 사람 상호작용은 자동화 비용 대비 효용이 낮아 분리한다.

### 3.2 커버리지 스코프 (측정 정합)

- **80% 수치 게이트는 `terminal_vs.rules` + `terminal_vs.config`에만 적용한다**(AC3·Day 6 게이트·Exit Gate). 이 두 계층은 순수·결정적이라 라인 커버리지가 의미를 가진다. rules 계층은 프로젝트 표준(전역 규약 80%)을 따른다: `--cov=terminal_vs.rules --cov=terminal_vs.config --cov-fail-under=80`.
- **순수 frame 합성 로직은 테스트하되 80% 수치 게이트는 적용하지 않는다.** Day 5의 `tests/test_frame_compose.py`·`tests/test_hud_render.py`는 합성 결과(레이어 우선순위·HUD 5요소·오버레이 3모드)를 **동작 단언**으로 검증한다(커버리지 % 임계 없음). 이는 blessed 출력과 분리된 순수 부분이 회귀 없이 동작함을 보장하는 것이지, 라인 커버리지 비율을 목표로 하는 것이 아니다.
- 전체 프로젝트 커버리지 %는 두지 않는다 — blessed 렌더 I/O와 대화형 루프는 의도적으로 헤드리스 테스트에서 제외되므로 전체 % 자체가 측정 불가능한 수치다.

### 3.3 import smoke가 함의하는 아키텍처 제약 (§5.1, §13)

- 모든 모듈(특히 blessed가 필요한 `render/*`, `__main__`)을 import해도 **터미널을 열거나 메인 루프에 진입하면 안 된다.**
- 따라서 터미널 셋업과 루프 진입은 `__main__.py`의 `main()` 함수와 `if __name__ == "__main__":` 가드 뒤에 둔다. 그래야 `python -c "import terminal_vs.__main__"`이 부수효과 없이 exit 0으로 끝나는 진짜 스모크 테스트가 된다.
- blessed import 자체(모듈 로드)는 터미널을 열지 않으므로 허용된다. 금지되는 것은 `Terminal()` 인스턴스화 후 화면 제어를 import 시점에 수행하는 것이다.

### 3.4 레이어 합성과 가독성 (§3.5, §9, §12)

- 합성 우선순위: 바닥 → 픽업 → 적 → 탄막 → 플레이어 → HUD/오버레이.
- **플레이어 항상 최상위**(§3.5, §12 가독성 리스크 완화): 난장 속에서도 플레이어가 보여야 한다. 이 불변식은 순수 합성 함수의 단위테스트로 강제한다(Day 5).
- 오버레이는 합성의 최상위 레이어로, `mode`에 따라 HUD 위에 모달 패널을 덮는다.

### 3.5 1차 밸런스의 데이터 주도성 (§5.5, §12)

- 밸런스 조정은 **코드 수정 없이 `balance.toml` 편집만으로** 수행한다. 이를 테스트로 증명한다(Day 6 민감도 테스트).
- 결정성: 동일 시드 + 동일 입력 → 동일 결과. 밸런스 변경 효과는 "다른 설정 → 다른 결과"로 격리 측정한다.

---

## 4. Critical Code Specs

의사 Python 코드. helper는 생략하고 시그니처·핵심 분기·불변성 경계만 표시한다. 성능 수치는 모두 `config`에서 읽으며 하드코딩하지 않는다.

### 4.1 셀프테스트 진입점 (exit 0 계약)

```python
# selftest.py — 헤드리스 진입점. pytest 반환 코드를 프로세스 종료 코드로 전파.
# 부수효과 경계: 터미널을 열지 않는다. blessed 출력 없음.
import sys
import pytest

def main() -> int:
    # rules + config 커버리지 게이트를 기본 적용. UI/blessed는 측정 제외.
    return pytest.main([
        "tests/",
        "--cov=terminal_vs.rules",
        "--cov=terminal_vs.config",
        "--cov-fail-under=80",
        "-q",
    ])

if __name__ == "__main__":
    sys.exit(main())   # 통과 시 0, 실패/커버리지 미달 시 비0
```

### 4.2 import smoke (부수효과 없음 단언)

```python
# tests/test_import_smoke.py
# 모든 모듈 import가 터미널을 열거나 루프에 진입하지 않음을 보장.
import importlib

MODULES = [
    "terminal_vs.__main__", "terminal_vs.loop", "terminal_vs.config",
    "terminal_vs.world", "terminal_vs.render.frame", "terminal_vs.render.hud",
    "terminal_vs.sim.state", "terminal_vs.sim.step", "terminal_vs.sim.spawn",
    "terminal_vs.rules.weapons", "terminal_vs.rules.damage",
    "terminal_vs.rules.evolution", "terminal_vs.rules.leveling",
]

def test_all_modules_import_without_side_effects():
    for name in MODULES:
        importlib.import_module(name)   # 예외 발생 시 테스트 실패
    # 터미널 미기동 단언: __main__에 main 가드가 있어 import만으로 루프 미진입.
    import terminal_vs.__main__ as entry
    assert hasattr(entry, "main")       # 진입점이 함수 뒤에 격리됨
```

### 4.3 헤드리스 완주 드라이버 (한 판 완주 proxy)

```python
# tests/support/sim_driver.py — blessed 비의존. sim/step.py만 구동.
# 불변성 경계: 시뮬레이션 상태는 sim.step 내부에서만 제자리 갱신(§6).
#              드라이버는 종료 상태를 읽기 전용으로만 관찰한다.
from terminal_vs.sim.state import new_run
from terminal_vs.sim.step import step

def run_until_gameover(cfg, rng, input_script, max_ticks):
    sim = new_run(cfg, rng)          # 가변 시뮬레이션 상태
    ticks = 0
    for intent in _iter_inputs(input_script, max_ticks):
        step(sim, intent, cfg, rng)  # 제자리 갱신(가변 경계 내부)
        ticks += 1
        if sim.player.hp <= 0:       # 게임오버 도달
            return {"reached_gameover": True, "ticks": ticks, "kills": sim.kills}
        if ticks >= max_ticks:       # 회귀 가드 상한(무한 루프 방지)
            break
    return {"reached_gameover": sim.player.hp <= 0, "ticks": ticks, "kills": sim.kills}
```

```python
# tests/test_full_run.py
import random
from tests.support.sim_driver import run_until_gameover

def test_full_run_reaches_gameover(test_cfg, fixed_input_script):
    rng = random.Random(1234)
    # max_ticks는 성능 수치가 아니라 회귀 가드 상한. 기대 완주 틱의 여유 배수.
    result = run_until_gameover(test_cfg, rng, fixed_input_script, max_ticks=test_cfg.full_run_tick_cap)
    assert result["reached_gameover"] is True

def test_full_run_is_deterministic(test_cfg, fixed_input_script):
    a = run_until_gameover(test_cfg, random.Random(1234), fixed_input_script, test_cfg.full_run_tick_cap)
    b = run_until_gameover(test_cfg, random.Random(1234), fixed_input_script, test_cfg.full_run_tick_cap)
    assert a["ticks"] == b["ticks"]   # 동일 시드 + 동일 입력 → 동일 종료 틱
```

### 4.4 순수 레이어 합성 (렌더/테스트 경계)

```python
# render/frame.py — 순수 합성 부분(blessed 비의존). 출력만 __main__/loop가 담당.
# 우선순위: floor < pickup < enemy < projectile < player < overlay
LAYER_ORDER = ("floor", "pickup", "enemy", "projectile", "player")

def compose_cells(view) -> list[list[Cell]]:
    """가시 영역 엔티티 → 셀 버퍼(순수). 동일 셀은 우선순위 높은 레이어가 덮는다.
       플레이어는 항상 최상위(§3.5). blessed 미호출."""
    buf = _blank(view.w, view.h)
    for layer in LAYER_ORDER:
        for ent in view.entities_in(layer):
            cx, cy = view.world_to_cell(ent.x, ent.y)   # world.py 매핑(§3.1)
            buf[cy][cx] = Cell(ent.glyph, ent.color)     # 후순위 레이어가 덮음
    return buf

def compose_overlay(buf, mode, run_state) -> list[str]:
    """mode in {'play','levelup','pause','gameover'} 별 HUD/오버레이 문자열(순수)."""
    rows = render_hud(buf, run_state)        # HP/XP/타이머/아이콘/킬 수
    if mode == "levelup":
        return overlay_levelup(rows, run_state.choices)
    if mode == "pause":
        return overlay_pause(rows)
    if mode == "gameover":
        return overlay_gameover(rows, run_state.summary)   # 재시작 안내 포함
    return rows
```

### 4.5 밸런스 민감도 (config 주도 증명)

```python
# tests/test_balance_sensitivity.py
# 코드 수정 없이 balance.toml 파라미터 변경만으로 결과가 달라짐을 증명.
from tests.support.sim_driver import run_until_gameover

def test_enemy_hp_changes_outcome(base_cfg, fixed_input_script):
    import random
    seed = 42
    base = run_until_gameover(base_cfg, random.Random(seed), fixed_input_script, base_cfg.full_run_tick_cap)
    # 동일 구조에서 적 HP 한 파라미터만 주입 변경(코드 불변, 설정만 변경).
    tougher_cfg = base_cfg.with_balance(enemy_base_hp=base_cfg.enemy_base_hp * 2)
    tough = run_until_gameover(tougher_cfg, random.Random(seed), fixed_input_script, tougher_cfg.full_run_tick_cap)
    # 적이 단단해지면 킬 수 또는 생존 틱 분포가 달라진다(데이터 주도 밸런스).
    assert tough["kills"] != base["kills"] or tough["ticks"] != base["ticks"]
```

---

## 5. Acceptance Criteria

| # | 기준 | 검증 절차 | 통과 |
| --- | --- | --- | --- |
| AC1 | 셀프테스트 exit 0 | `python selftest.py`; echo $? == 0 | [ ] |
| AC2 | import smoke exit 0 (부수효과 없음) | `python -c "import terminal_vs.__main__, terminal_vs.loop, terminal_vs.render.frame, terminal_vs.render.hud, terminal_vs.world, terminal_vs.config"`; echo $? == 0 | [ ] |
| AC3 | rules + config 라인 커버리지 ≥ 80% | `python -m pytest tests/ --cov=terminal_vs.rules --cov=terminal_vs.config --cov-fail-under=80`; exit 0 | [ ] |
| AC4 | 헤드리스 완주 회귀(게임오버 도달) | `python -m pytest tests/test_full_run.py`; exit 0 | [ ] |
| AC5 | 완주 결정성(동일 시드 → 동일 종료 틱) | `test_full_run_is_deterministic` 통과 (AC4 스위트 내) | [ ] |
| AC6 | 밸런스 1차: config만으로 결과 변동 | `python -m pytest tests/test_balance_sensitivity.py`; exit 0, 소스 미수정 | [ ] |
| AC7 | HUD 5요소 합성 출력 포함 | `python -m pytest tests/test_hud_render.py`; exit 0, 요소별 단언 ≥ 5 | [ ] |
| AC8 | 레이어 우선순위(플레이어 최상위) | `tests/test_frame_compose.py` 겹침 케이스 통과 | [ ] |
| AC9 | 오버레이 3모드 전환(levelup/pause/gameover) | 헤드리스: `tests/test_hud_render.py` 모드별 단언 ≥ 3 통과 + qa-tester tmux 세션에서 3모드 관측 기록 | [ ] |
| AC10 | rules 단위테스트 결정성(주입 RNG) | `grep -rE 'Random\(' tests/test_weapons.py tests/test_leveling.py` ≥ 1 + 해당 스위트 exit 0 | [ ] |
| AC11 | 게임오버 → 재시작 흐름 | qa-tester tmux: 게임오버 도달 후 재시작 입력 → play 모드 재진입 관측 기록 | [ ] |
| AC12 | 종료 조건 측정성(모호 표현 0건) | 각 Day "측정 가능한 종료 조건"·Exit Gate 항목이 모두 실행 가능한 명령/수치/상태 도달로 기술됨을 리뷰어가 확인. 금지어("정상 동작 확인", "잘 작동", "에러 없음", 단독 "OK")가 종료 조건 본문에 0건(grep 명령 인용 줄은 제외) | [ ] |

---

## 6. Risks & Mitigations

| 위험 | 가능성 | 영향 | 완화 |
| --- | --- | --- | --- |
| import smoke 실패(모듈 import 시 터미널 기동·루프 진입) | 중 | 높음 | 터미널 셋업·루프 진입을 `main()` + `if __name__ == "__main__"` 가드 뒤로 격리(§3.3). Day 1에서 회귀 가드. |
| 완주 드라이버가 게임오버에 도달하지 못함(밸런스가 너무 쉬움) | 중 | 중 | 입력 스크립트를 "수동적/비회피" 패턴으로 구성하거나, 밸런스 민감도 테스트에서 적 HP·스폰율을 높인 config로 도달 보장. 상한 틱 초과 시 명시적 실패. |
| 커버리지 목표를 전체 프로젝트로 오인 → 측정 불가 | 중 | 중 | 커버리지 스코프를 `terminal_vs/rules` + config로 **명시적 한정**(§3.2). blessed 렌더·대화형 루프는 제외. |
| 렌더/테스트 경계 미분리 → blessed 의존 테스트 | 중 | 높음 | 합성 순수 함수와 blessed 출력을 분리(§3.1, Day 5). 테스트는 순수 반환값만 단언. |
| 밸런스 변경 효과가 결정성에 가려 측정 안 됨 | 낮음 | 중 | 동일 시드 고정 + 한 파라미터만 변경하는 격리 비교(Day 6 §3.5). |
| 가독성: 난장 속 플레이어 식별 불가 | 중 | 높음 | 레이어 우선순위·플레이어 최상위를 순수 합성 테스트로 강제(§3.4, AC8). |
| 성능 수치 하드코딩(TPS·뷰포트·캡)으로 Phase 0 산출값과 불일치 | 중 | 중 | 드라이버·테스트가 `config`에서만 읽도록 강제. 상한 틱은 회귀 가드 상한으로만 사용, config에서 유도. |
| pytest/pytest-cov 미설치로 커버리지 명령 비실행 | 중 | 중 | `requirements-dev.txt`에 명시(Day 1 KD8), `run.sh`에 설치·실행 통합. |
| 검증을 작성 패스에서 자기 승인 | 낮음 | 중 | verifier/code-reviewer를 분리 lane에서 수행(Day 6). |

---

## 7. Exit Gate — Phase 3 → (Phase 4 옵션 또는 릴리스)

마스터 §10 Phase 3 Exit("selftest exit 0, 임포트 스모크 통과, 한 판 완주 가능")에 SHARED CONTRACT의 HUD/오버레이 3모드 전환 확인을 더한 통합 체크리스트. 모든 항목은 명령·상태 도달로 검증한다.

- [ ] `python selftest.py` exit code 0 (전 스위트 통과). (AC1)
- [ ] import smoke exit code 0, escape 시퀀스 방출 0건. (AC2)
- [ ] `python -m pytest tests/ --cov=terminal_vs.rules --cov=terminal_vs.config --cov-fail-under=80` exit code 0. (AC3)
- [ ] `python -m pytest tests/test_full_run.py` exit code 0 — 헤드리스 완주(게임오버 도달) 회귀 통과. (AC4, AC5)
- [ ] `python -m pytest tests/test_balance_sensitivity.py` exit code 0 — config 편집만으로 난이도 변동 증명, 소스 미수정. (AC6)
- [ ] HUD 5요소 + 레이어 우선순위 + 오버레이 3모드 헤드리스 테스트 통과. (AC7, AC8, AC9)
- [ ] qa-tester tmux 세션에서 게임오버 도달 → 재시작 → play 모드 재진입 + 3모드(levelup/pause/gameover) 전환 관측 기록. (AC9, AC11)
- [ ] 검증 패스(verifier/code-reviewer)가 작성 패스와 분리된 lane에서 수행되어 승인 기록 존재.
- [ ] 종료 조건·Exit Gate 항목이 모두 실행 가능한 명령/수치/상태 도달로 기술됨 — 금지어("정상 동작 확인", "잘 작동", "에러 없음", 단독 "OK")가 종료 조건 본문에 0건(grep 명령 인용 줄 제외). (AC12)

위 항목이 모두 통과하면 MVP 검증이 닫히고, 이후 Phase 4(메타 진행·추가 콘텐츠·보스/엘리트·사운드, 마스터 §10) 또는 릴리스로 진행한다.
