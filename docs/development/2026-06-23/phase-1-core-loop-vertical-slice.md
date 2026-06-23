# Phase 1 상세개발 계획서 — 코어 루프 수직 슬라이스

작성일: 2026-06-23
대상 레포: `terminal-vampire-survivor`
상위 문서: `docs/plan/2026-06-23/work-plan-v1.md` (마스터 계획서 v1)
대상 마스터 절: §3.1, §3.4, §3.5, §4, §5.1~§5.4, §6, §8, §10 Phase 1

> 이 문서는 마스터 §10 Phase 1을 day-by-day 상세 개발 계획으로 구체화한다.
> 수직 슬라이스 원칙: 무기 1종·적 1종·레벨업 1택으로 좁히되,
> `loop / world / sim / rules / render`의 모든 경계를 한 번 관통해 세운다.
> 성능 수치(TPS·뷰포트·엔티티 캡)는 Phase 0 산출값이며, 이 문서는
> 그 값을 하드코딩하지 않고 `config/tuning.toml` 참조로만 표기한다.

---

## 1. 개요

### Goal

마스터 §10 Phase 1을 달성한다: **"이동하며 적을 자동으로 잡고 경험치로 레벨업한다"가 플레이 가능**한 최소 수직 슬라이스를 만든다. 마스터의 풀 모듈 구조(`§5.1`)를 최소 구현으로 한 번 관통하여, 후속 Phase가 확장할 경계(loop/world/sim/rules/render)를 모두 세운다.

### Scope

**In (이번 Phase에 구현):**

- 8방향 이동 입력 폴링과 플레이어 의도 속도 적용 (마스터 §3.4)
- 플레이어 중심 카메라·뷰포트, 월드↔셀 좌표 매핑·종횡비 보정 (마스터 §3.1, §3.2)
- 적 1종 스폰(화면 밖 링에서 평탄 비율 생성, 디렉터 곡선은 placeholder) (마스터 §5.4 2단계)
- 적 1종 AI 이동(플레이어 추적) (마스터 §5.4 3단계)
- 무기 1종 자동 발사: 단검류 — 최근접 적 방향 투사체 (마스터 §5.4 4단계, §7-1)
- 투사체 이동·수명 (마스터 §5.4 5단계)
- 충돌 해소: 투사체↔적 데미지, 적↔플레이어 피해 (마스터 §5.4 6단계)
- 사망 처리 → 경험치 보석 드랍 (마스터 §5.4 7단계)
- 픽업 수집(자석 범위) → 경험치 적립 → 레벨업 트리거 (마스터 §5.4 8단계)
- 레벨업 1택 오버레이(선택지 1개, 일시정지 모드) (마스터 §8)
- 정리(죽은 엔티티 제거, 원거리 디스폰), 카메라 갱신 (마스터 §5.4 9~10단계)
- uniform grid spatial hash 충돌 질의 (마스터 §5.3)
- fixed-timestep + accumulator 루프 (마스터 §4, 부록 A)
- config 로딩·검증→불변 설정 객체 (마스터 §5.5)
- rules 계층 헤드리스 결정적 단위테스트 (마스터 §13)

**Out (후속 Phase로 연기):**

- 진화(`rules/evolution.py`는 stub) — Phase 2
- 다중 무기·패시브(공속/이속/자석 강화) — Phase 2
- 디렉터 난이도 곡선(시간 기반 스폰율 상승·강화 스텝) — Phase 2
- 적 2종째(빠른 약체 떼), 보스/엘리트 — Phase 2
- hazard(장판/오라) — Phase 2 (넉백 계산은 Phase 1 `rules/damage.py`에 포함)
- diff 렌더 최적화(Phase 1은 단순 전체 프레임 출력 또는 Phase 0 결정 방식) — 필요 시 Phase 2/3
- HUD 전체(무기/패시브 아이콘·킬 수 등)는 Phase 1 최소(HP·레벨·경험치·생존 타이머)만 — 확장은 Phase 3
- 게임오버/재시작 폴리시, 밸런스 1차 — Phase 3
- 메타 진행·사운드 — Phase 4

### Key Deliverables

| # | 산출물 | 위치 |
| --- | --- | --- |
| K1 | 패키지 스캐폴드 + config 로더 | `terminal_vs/{__main__.py,config.py}`, `config/{balance.toml,tuning.toml}` |
| K2 | 월드 좌표·카메라·종횡비 보정 | `terminal_vs/world.py` |
| K3 | 시뮬레이션 상태·틱 파이프라인·공간해시·스폰 | `terminal_vs/sim/{state.py,step.py,spatial.py,spawn.py}` |
| K4 | 순수 규칙 계층(무기·데미지·레벨링·정의) | `terminal_vs/rules/{weapons.py,damage.py,leveling.py,defs.py}` |
| K5 | 렌더·HUD | `terminal_vs/render/{frame.py,hud.py}` |
| K6 | fixed-timestep 루프 | `terminal_vs/loop.py` |
| K7 | 헤드리스 rules 단위테스트 | `tests/` |
| K8 | 실행 스크립트 | `run.sh` |

### Dependencies

- **Entry gate**: Phase 0 exit 충족 — 작동점 `N`(지속 가능 글리프 수)·`sim_tps`·뷰포트·엔티티 캡이 숫자로 확정되고, `config/tuning.toml`에 그 초기값이 존재한다.
- Python 3.11+ (표준 라이브러리 `tomllib` 사용, 마스터 §5.5).
- `blessed>=1.20` (이미 `requirements.txt`에 존재). `render/`·`__main__`에서만 import.
- 마스터 §6 / ADR-001(불변성 한정 예외)이 D5로 승인된 상태를 전제로 sim 계층 제자리 갱신을 적용한다.

### Effort

| 영역 | 예상 소요 |
| --- | --- |
| 스캐폴드 + config + world | 1.0~1.5일 |
| sim 파이프라인 + spatial + spawn | 1.5~2.0일 |
| rules 순수 함수 + 헤드리스 테스트 | 1.0~1.5일 |
| render + loop + 대화형 검증 | 1.5~2.0일 |
| 합계 | 5~7일 (Day 1~6, 버퍼 1일) |

---

## 2. Day-by-Day Work Package

각 Day 카드는 6개 필드를 가진다: 목표 / 산출물 / OMC 위임 / 예상 소요 / 기술 노트 / 측정 가능한 종료 조건.
종료 조건의 모든 명령은 레포 루트에서 실행 가능해야 하며, "정상 동작"·"통과" 같은 모호한 표현을 쓰지 않는다.

---

### Day 1 — 패키지 스캐폴드 + config 로더 + import smoke

**목표.** 마스터 §5.1 패키지 레이아웃의 빈 골격과 `config.py`(로드→검증→불변 설정 객체)를 세운다. 모든 모듈이 import 가능한 상태를 만든다.

**산출물.**
- `terminal_vs/` 패키지: `__init__.py`, `__main__.py`(스텁 엔트리), `loop.py`·`world.py`·`config.py`(스텁 가능), `sim/{__init__,state,step,spatial,spawn}.py`(스텁), `rules/{__init__,weapons,damage,evolution,leveling,defs}.py`(스텁), `render/{__init__,frame,hud}.py`(스텁), `content/__init__.py`
- `config/balance.toml`, `config/tuning.toml` (Phase 0 산출 초기값 포함, 신규 키는 코드 기본값 폴백)
- `config.py`: TOML 로드(`tomllib`) → 스키마·범위 검증 → **불변 설정 객체**(frozen dataclass 또는 `NamedTuple`). 누락 키는 코드 기본값 폴백, 범위 위반은 명확한 에러.
- `run.sh`, `tests/__init__.py`, `tests/test_config.py`

**OMC 위임.** `executor` (model=opus, 스캐폴드·config 스키마 설계는 경계 결정 포함) → 검증 `verifier`.

**예상 소요.** 1.0~1.5일.

**기술 노트.**
- 설정 객체는 불변. `rules/defs.py`가 이를 읽어 밸런스 테이블을 구성하고, 규칙 계층은 전역 접근이 아니라 **읽기 전용 의존성 주입**으로 설정을 받는다(마스터 §5.5, §6).
- `tuning.toml`에는 `sim_tps`, `poll_timeout`, `max_catchup`, `viewport_w`, `viewport_h`, `entity_cap`, `aspect_x`(종횡비 보정 계수) 등 Phase 0 운영 상수. **이 문서는 그 수치를 본문/코드에 적지 않는다 — 키 이름만 참조.**
- `balance.toml`에는 무기(단검) 쿨다운·데미지·투사체 속도·수명, 적 HP·이동속도·스폰 가중치, 경험치 곡선, 자석 범위 등. 값 자체는 balance.toml에 두고 코드 기본값 폴백.

**측정 가능한 종료 조건.**
- [ ] `python -c "import terminal_vs.__main__, terminal_vs.loop, terminal_vs.world, terminal_vs.config, terminal_vs.sim.state, terminal_vs.sim.step, terminal_vs.sim.spatial, terminal_vs.sim.spawn, terminal_vs.rules.weapons, terminal_vs.rules.damage, terminal_vs.rules.leveling, terminal_vs.rules.defs, terminal_vs.render.frame, terminal_vs.render.hud"` → exit code 0
- [ ] `python -m pytest tests/test_config.py -q` → exit code 0 (정상 로드, 누락 키 폴백, 범위 위반 에러 raise 각 케이스 검증)
- [ ] `grep -rEn 'sim_tps|viewport|entity_cap|aspect' terminal_vs/` 결과의 모든 매치가 `cfg.` 접근 또는 키 문자열이고, 숫자 리터럴 할당이 0건 (성능 수치 하드코딩 금지 검증)
- [ ] `python -c "import tomllib; tomllib.load(open('config/tuning.toml','rb')); tomllib.load(open('config/balance.toml','rb'))"` → exit code 0 (TOML 파싱 가능)

---

### Day 2 — world.py: 좌표 매핑 · 종횡비 보정 · 카메라/뷰포트

**목표.** float 월드 좌표를 렌더 셀로 양자화하는 단방향 매핑과, 종횡비 보정을 `world.py` 한 곳에 모은다(마스터 §3.1). 플레이어 중심 카메라·뷰포트·가시 영역 컬링 질의를 제공한다(§3.2).

**산출물.**
- `world.py`: `world_to_cell(wx, wy, cam, cfg) -> (col, row)`, `cell_to_world(col, row, cam, cfg) -> (wx, wy)`(역매핑은 스폰 링 계산에만), `Camera`(플레이어 추종), `visible_bounds(cam, cfg) -> Rect`, `is_visible(wx, wy, cam, cfg) -> bool`
- 종횡비 보정: X축을 `cfg.aspect_x` 계수로 압축(셀 2:1 길쭉함 보정). 원형 사거리/확산은 타원 보정. **보정 계수는 tuning.toml에서만 읽는다.**

**OMC 위임.** `executor` (좌표 수학은 결정적이므로 단위테스트 가능) → 헤드리스 테스트 `test-engineer`.

**예상 소요.** 0.5~1.0일.

**기술 노트.**
- `world.py`는 `blessed` 비의존(순수 수학). 카메라·매핑은 결정적이라 헤드리스 단위테스트 가능 → rules와 별개로 `tests/test_world.py`에서 검증.
- 컬링은 §3.3 처리량 문제와 직결(마스터). 뷰포트 크기는 `cfg.viewport_w/h`로만 참조.
- 라운드트립 오차: `world_to_cell`은 다대일(양자화)이므로 완전 역가역이 아니다. 테스트는 셀 경계 내 포함 여부로 검증한다(부동소수 동등 비교 금지).

**측정 가능한 종료 조건.**
- [ ] `python -m pytest tests/test_world.py -q` → exit code 0
- [ ] 테스트가 다음을 포함: (a) 동일 월드 거리에서 X·Y 셀 변위 비가 `cfg.aspect_x`를 반영한다(`assert` 수치 비교), (b) 뷰포트 밖 좌표에 `is_visible == False`, 안쪽 좌표에 `True`, (c) `world_to_cell(cell_to_world(c,r)) == (c,r)` 셀 경계 내 일치
- [ ] `grep -En '[0-9]' terminal_vs/world.py` 매치 중 종횡비/뷰포트 관련 숫자 리터럴 0건 (모두 `cfg.` 경유) — 인덱스·0/1 상수 제외 수동 확인

---

### Day 3 — sim 골격: state · spatial hash · 틱 파이프라인 (불변성 경계)

**목표.** 마스터 §5.4 10단계 파이프라인의 골격을 `sim/step.py`에 세운다. Phase 1에 필요한 단계만 실제 구현하고, 나머지는 명시적 placeholder/stub로 둔다. uniform grid spatial hash(`sim/spatial.py`)와 가변 상태 버퍼(`sim/state.py`)를 만든다.

**산출물.**
- `sim/state.py`: `SimState`(가변 엔티티 버퍼 — player, enemies, projectiles, pickups). `new_run(cfg, rng) -> SimState`. 엔티티 공통 필드: id(결정적 정수 시퀀스), 위치(x,y float), 속도, HP, 팀, 글리프/색, 수명(투사체). **가변 버퍼는 §6 경계의 '가변' 쪽 — sim/step 밖으로 누출 금지.**
- `sim/spatial.py`: `SpatialHash`(uniform grid), `build(entities, cell_size)`, `query_near(x, y, radius) -> ids`. 인접 버킷만 검사(O(n²) 회피, 마스터 §5.3).
- `sim/step.py`: `step(state, intent, cfg, rng) -> None`(제자리 갱신). 10단계 순서 골격 + 단계별 구현/연기 마커(§3 표 참조).
- `sim/spawn.py`: `maybe_spawn(state, cfg, rng)` — 화면 밖 링에서 적 1종 평탄 비율 스폰. **디렉터 난이도 곡선은 placeholder(고정 비율)**, 시간 기반 상승은 Phase 2.

**OMC 위임.** `executor` (model=opus, 불변성 경계·파이프라인 골격은 아키텍처 결정) → 경계 누출 검토 `code-reviewer`.

**예상 소요.** 1.5~2.0일.

**기술 노트.**
- 불변성 경계(마스터 §6 / ADR-001): `sim/step.py` 내부에서만 제자리 갱신. `step` 함수에 경계 주석 명시. 엔티티 캡은 `cfg.entity_cap`으로만 참조.
- `rng: random.Random` 주입 — 스폰 위치·드랍을 결정적으로 재현. `new_run`·`step`·`maybe_spawn` 모두 rng를 인자로 받는다.
- step은 내부에서 rules 순수 함수를 호출(Day 4 산출). Day 3에서는 rules 호출부를 인터페이스로 두고, rules 미완성 단계는 임시 직접 구현 후 Day 4에서 교체 가능.

**측정 가능한 종료 조건.**
- [ ] `python -m pytest tests/test_spatial.py -q` → exit code 0 (브루트포스 전수 비교 결과와 `query_near` 결과 집합 일치를 100개 랜덤 시드 엔티티로 검증)
- [ ] `python -m pytest tests/test_sim_step.py -q` → exit code 0 (동일 시드 `random.Random(42)` 두 번 실행 → N틱 후 `SimState` 엔티티 위치·HP·id 시퀀스 완전 일치 = 결정성 검증)
- [ ] `grep -En 'def step|placeholder|deferred|TODO\(phase2\)' terminal_vs/sim/step.py` 결과에 10단계 각각의 구현/연기 마커가 주석으로 존재 (단계 누락 0)
- [ ] `grep -En 'class SimState|in-place|mutate' terminal_vs/sim/state.py terminal_vs/sim/step.py` 로 불변성 경계 주석 존재 확인 (경계 문서화 1건 이상)

---

### Day 4 — rules 순수 계층: 무기 발사 · 데미지 · 경험치 · 레벨업 1택

**목표.** 게임의 "두뇌"를 순수·불변 함수로 구현한다(마스터 §6). 무기 발사 판정(최근접 타게팅), 데미지, 경험치 적립·레벨업 트리거, 레벨업 1택 선택지 산출. `blessed` 비의존, 결정적.

**산출물.**
- `rules/defs.py`: 불변 설정 객체에서 밸런스 테이블 구성. `weapon_def(cfg)`, `enemy_def(cfg)`, `xp_curve(cfg)`.
- `rules/weapons.py`: `select_target(player_pos, enemies, cfg) -> enemy_id | None`(최근접, **타이브레이크는 최저 entity id로 결정적**), `should_fire(weapon_state, dt, cfg) -> bool`(쿨다운 만료), `spawn_projectile_intent(player_pos, target_pos, cfg) -> ProjectileSpec`. 모두 순수 함수.
- `rules/damage.py`: `apply_hit(hp, dmg) -> new_hp`, `is_dead(hp) -> bool`, `knockback(pos, source_pos, force) -> new_pos`(넉백 방향·크기, 순수 계산).
- `rules/leveling.py`: `accrue_xp(level_state, gained) -> new_level_state`, `level_up_pending(level_state, cfg) -> bool`, `roll_choices(level_state, cfg, rng, n=1) -> tuple[Choice, ...]`(**Phase 1은 n=1 단일 선택만** 반환; Phase 2에서 `(build_state, defs, rng, n)`으로 일반화), `apply_choice(sim_facing_state, choice) -> ...`(순수 산출, 적용은 sim에서).
- `rules/evolution.py`: stub(`def can_evolve(...): return False  # Phase 2`).

**OMC 위임.** `tdd-guide` 또는 `test-engineer` (RED→GREEN, 헤드리스 단위테스트 우선) → 구현 `executor`.

**예상 소요.** 1.0~1.5일.

**기술 노트.**
- 모든 rules 함수는 부수효과 없음 + 불변 입출력. 전역 상태·`blessed` 접근 금지(마스터 §13).
- 타게팅 결정성: 최근접 거리 동률 시 **entity id 오름차순 최저값** 선택. 이 규칙을 weapons.py docstring과 테스트에 명시 → 단위테스트가 결정적.
- `random.Random` 주입: `roll_choices`가 rng를 받지만 Phase 1은 선택지 1개(n=1)라 사실상 결정적. 시그니처는 Phase 2 N택 대비 rng·n 인자 유지.
- 경험치 곡선·무기 상수는 주입된 cfg에서만 읽는다. 테스트는 임의 cfg를 주입해 곡선·쿨다운을 검증.

**측정 가능한 종료 조건.**
- [ ] `python -m pytest tests/test_weapons.py tests/test_damage.py tests/test_leveling.py -q` → exit code 0
- [ ] `test_weapons.py`: (a) 적 3마리 중 최근접 선택, (b) 거리 동률 2마리에서 **최저 id 선택**을 단언, (c) 적 0마리에서 `select_target == None`
- [ ] `test_damage.py`: `apply_hit` 결과 단언, HP 0 이하 시 `is_dead == True`
- [ ] `test_leveling.py`: 경험치 곡선 임계 미달→`level_up_pending False`, 임계 도달→`True`, `roll_choices` 길이 == 1, `accrue_xp`가 입력 상태를 변형하지 않음(불변 — 입력 객체 동일성/값 보존 단언)
- [ ] `grep -rEn "import blessed|from blessed" terminal_vs/rules/` → 0건 (규칙 계층 blessed 비의존)
- [ ] `grep -rEn "tie|lowest id|entity id" terminal_vs/rules/weapons.py` → 타이브레이크 규칙 주석 1건 이상

---

### Day 5 — render + loop: 레이어 합성 · HUD · fixed-timestep · 대화형 결선

**목표.** `render/`와 `loop.py`를 세워 수직 슬라이스를 **플레이 가능**하게 만든다. 마스터 부록 A의 fixed-timestep + accumulator 루프, 그리기 우선순위 레이어 합성, 최소 HUD를 구현한다. 이 Day가 blessed 경계를 세운다.

**산출물.**
- `render/frame.py`: `render_frame(term, state, cam, cfg)` — 가시 영역만 렌더(컬링). 그리기 우선순위(아래일수록 위에 덮음): 바닥 < 픽업 < 적 < 탄막 < 플레이어 < HUD. **플레이어 항상 최상위**(마스터 §3.5). Phase 1은 단순 전체 프레임 출력(diff 렌더는 Phase 0 결정/후속).
- `render/hud.py`: HP 바, 레벨·경험치 바, 생존 타이머. 무기/패시브 아이콘·킬 수는 Phase 3.
- `loop.py`: `run(term, cfg, rng)` — 부록 A 골격. `term.inkey(timeout=cfg.poll_timeout)` 폴링, accumulator로 `SIM_DT = 1.0/cfg.sim_tps` 소비, `cfg.max_catchup` 상한, 모드 전환(`play`/`levelup`/`pause`/`gameover`). 레벨업 트리거 시 선택 오버레이 모드(시뮬레이션 일시정지).
- `__main__.py`: 터미널 셋업(`term.fullscreen`/`cbreak`/`hidden_cursor`) + `loop.run` 호출.
- `run.sh`: venv 활성화 + `python -m terminal_vs`.

**OMC 위임.** 구현 `executor` (blessed 렌더 경계) → 대화형 검증 `qa-tester`(tmux 세션).

**예상 소요.** 1.5~2.0일.

**기술 노트.**
- `blessed` 의존은 `render/`·`loop.py`·`__main__.py`에만(마스터 §13). loop은 sim/rules를 호출만 하고 blessed 객체를 그 계층으로 넘기지 않는다.
- 8방향 이동: 화살표 키. 대각선은 두 키 연속/동시 입력 정책(마스터 §3.4) — Phase 1은 가장 단순한 처리(마지막 폴링 키 기준 의도 벡터)로 시작.
- 깜빡임 없는 렌더(마스터 §3.6): 전체 clear 금지, `term.home` 후 프레임 문자열 일괄 출력, 짧은 줄 고정폭 패딩.
- 모든 루프 타이밍 상수는 `cfg`에서만 읽는다 — `SIM_DT`, `POLL_TIMEOUT`, `max_catchup` 모두 cfg 경유. **루프 코드에 TPS/타임아웃 숫자 리터럴 금지.**

**측정 가능한 종료 조건.**
- [ ] `python -c "import terminal_vs.loop, terminal_vs.render.frame, terminal_vs.render.hud, terminal_vs.__main__"` → exit code 0 (import smoke)
- [ ] `grep -rEn "import blessed|from blessed|term\." terminal_vs/sim/ terminal_vs/rules/ terminal_vs/world.py` → 0건 (blessed 경계: sim/rules/world 비의존)
- [ ] `grep -En "1\.0 ?/ ?cfg\.sim_tps|cfg\.poll_timeout|cfg\.max_catchup" terminal_vs/loop.py` → 각 1건 이상이고, `grep -En 'timeout=[0-9]|sim_tps ?= ?[0-9]' terminal_vs/loop.py` → 0건 (타이밍 상수 cfg 경유)
- [ ] **qa-tester(tmux) 대화형 관측**: tmux로 `run.sh` 실행 후 ~30초 관측 시 (a) 플레이어 글리프가 화살표 입력으로 이동, (b) 적 글리프가 플레이어 방향으로 접근, (c) 투사체가 자동 발사되어 적 제거 시 경험치 픽업 글리프 출현, (d) HUD 경험치 바 값 > 0 그리고 레벨 ≥ 2 도달, (e) 레벨업 시 선택 오버레이가 렌더되고 선택 입력 후 `play` 모드 복귀 — 5개 항목 관측 로그로 기록

---

### Day 6 — 헤드리스 통합 · selftest · Exit Gate 검증 (버퍼)

**목표.** rules 계층 전체 헤드리스 테스트를 묶고, 한 판이 결정적으로 도는지를 헤드리스 시뮬레이션으로 검증한다. Exit Gate 종료 조건을 실측한다.

**산출물.**
- `tests/test_integration_run.py`: blessed 없이 `new_run` → N틱 `step` 반복 → "적 처치 → 경험치 드랍 → 픽업 수집 → 레벨업 트리거"가 한 번 발생하는 시나리오를 결정적 시드로 검증(렌더 제외 순수 시뮬레이션).
- `selftest.py`(또는 `tests/`로 통합): 헤드리스 실행 시 exit 0.
- README/run.sh 실행 경로 정리.

**OMC 위임.** `test-engineer`(통합 시나리오) → `verifier`(Exit Gate 전체 종료 조건 실측).

**예상 소요.** 0.5~1.0일.

**기술 노트.**
- 통합 테스트는 렌더를 호출하지 않는다(sim+rules만). 한 판 시나리오를 고정 시드로 짧게(예: 레벨업 1회 발생까지) 돌려 결정성과 루프 폐쇄를 검증.
- 헤드리스에서 "이동→처치→경험치→레벨업"을 관측 가능한 proxy로: 시작 레벨 1 → N틱 후 `level >= 2` 그리고 `level_up_pending`가 한 번이라도 True가 됐는지 카운터로 확인.

**측정 가능한 종료 조건.**
- [ ] `python -m pytest tests/ -q` → exit code 0 (rules+world+spatial+sim+integration 전체)
- [ ] `python -m pytest tests/test_integration_run.py -q` → exit code 0 (동일 시드 2회 실행 결과 완전 일치 + 레벨업 1회 발생 단언)
- [ ] `python selftest.py` (존재 시) 또는 `python -m pytest tests/ -q` → exit code 0
- [ ] `python -c "import terminal_vs.__main__"` → exit code 0 (import smoke 재확인)

---

## 3. 아키텍처·기술 노트 — 마스터 절 구체화

### 3.1 §5.4 틱 파이프라인 10단계: 구현 / 연기 분할 (마스터 §5.1 모듈 이름 그대로)

| 단계 | 마스터 §5.4 | Phase 1 처리 | 담당 모듈 (§5.1 이름) |
| --- | --- | --- | --- |
| 1 | input 적용 | **구현** (8방향 의도 속도) | `loop.py` → `sim/step.py` |
| 2 | director 스폰 | **최소** (평탄 비율, 난이도 곡선 placeholder) | `sim/spawn.py` |
| 3 | 적 AI 이동 | **구현** (플레이어 추적, 적 1종) | `sim/step.py` |
| 4 | 무기 쿨다운·발사 | **구현** (단검 1종, 최근접 타게팅) | `rules/weapons.py` (순수) + `sim/step.py` |
| 5 | 투사체 이동/수명 | **구현** | `sim/step.py` |
| 6 | 충돌 해소 | **구현** (투사체↔적 데미지, 적↔플레이어 피해, 넉백 방향·크기) | `sim/spatial.py` + `rules/damage.py` |
| 7 | 사망 처리 → 경험치 드랍 | **구현** | `sim/step.py` + `rules/damage.py` |
| 8 | 픽업 수집 → 경험치 → 레벨업 트리거 | **구현** (자석 범위, 1택 트리거) | `rules/leveling.py` (순수) + `sim/step.py` |
| 9 | 정리 (제거·디스폰) | **구현** | `sim/step.py` |
| 10 | 카메라 갱신 | **구현** | `world.py` (Camera) |

**모듈별 구현 수준 요약:**

| 모듈 (§5.1) | Phase 1 수준 |
| --- | --- |
| `loop.py`, `world.py`, `config.py` | 실구현 |
| `sim/state.py`, `sim/step.py`, `sim/spatial.py` | 실구현 |
| `sim/spawn.py` | 최소 (평탄 비율, 디렉터 곡선 없음) |
| `rules/weapons.py`, `rules/damage.py`, `rules/leveling.py`, `rules/defs.py` | 실구현 |
| `render/frame.py`, `render/hud.py`, `__main__.py` | 실구현 (HUD 최소) |
| `rules/evolution.py` | **stub** (`return False`) |
| hazard / 다중 무기 / 패시브 / diff 렌더 | **미작성 또는 후속 Phase** |

### 3.2 §3.1 좌표계·종횡비

- float 월드 좌표에서 시뮬레이션이 돌고, 렌더 시에만 셀 양자화. 종횡비 보정(X축 `cfg.aspect_x` 압축)은 `world.py` 한 곳에 집중. 원형 사거리는 타원 보정으로 체감상 원형이 되게 한다.

### 3.3 §3.4 입력

- non-blocking 폴링(`term.inkey(timeout=cfg.poll_timeout)`). 입력이 없어도 시뮬레이션 전진. 8방향 이동(화살표), 대각선은 Phase 1 단순 정책(마지막 폴링 키 의도 벡터).

### 3.4 §3.5 그리기 우선순위

- 바닥 < 픽업 < 적 < 탄막 < 플레이어 < HUD. 플레이어는 난장 속에서도 항상 최상위로 그린다.

### 3.5 §6 불변성 경계 (ADR-001)

- 순수·불변(`rules/*`): 부수효과 없는 순수 함수 + 불변 값. 가변·제자리(`sim/step.py` 내부에서만): 엔티티 버퍼 제자리 갱신. 가변 상태는 sim step 밖으로 누출 금지. 렌더/규칙은 읽기 전용으로만 본다.

### 3.6 §4 게임 루프

- fixed-timestep + accumulator(부록 A). `SIM_DT = 1.0/cfg.sim_tps`, 폭주 방지 `cfg.max_catchup` 상한, dirty 플래그·tick interval 패턴. 모드: `play`/`levelup`/`pause`/`gameover`.

---

## 4. Critical Code Specs

> 의사 Python. 함수 시그니처·핵심 분기·불변성 경계만 표기하고 helper는 생략한다.
> 성능 수치는 모두 `cfg.*`로 참조하며 숫자 리터럴을 쓰지 않는다.

### 4.1 `config.py` — 로드·검증·불변 설정 (마스터 §5.5)

```python
from dataclasses import dataclass
import tomllib

@dataclass(frozen=True)            # 불변 설정 객체 (§6 경계의 '불변' 쪽)
class Config:
    sim_tps: float                 # Phase 0 산출값, tuning.toml에서만 로드
    poll_timeout: float
    max_catchup: int
    viewport_w: int
    viewport_h: int
    entity_cap: int
    aspect_x: float                # 종횡비 보정 계수 (§3.1)
    balance: "BalanceTable"        # balance.toml에서 구성된 불변 밸런스

def load_config(tuning_path: str, balance_path: str) -> Config:
    # 1) tomllib로 로드 (Python 3.11+ 표준, 추가 의존성 없음)
    # 2) 누락 키는 코드 기본값으로 폴백 → 설정 파일 없어도 첫 실행 보장
    # 3) 범위 위반(예: sim_tps <= 0)은 모호하지 않은 ValueError
    # 4) frozen Config 반환 (불변 → 규칙 계층에 읽기 전용 주입)
    ...
```

### 4.2 `world.py` — 좌표 매핑·종횡비 보정 (마스터 §3.1)

```python
def world_to_cell(wx: float, wy: float, cam: "Camera", cfg: Config) -> tuple[int, int]:
    # float 월드 → 렌더 셀 양자화. 종횡비 보정은 여기 한 곳에만.
    rel_x = (wx - cam.x) * cfg.aspect_x      # X 압축 (셀 2:1 보정)
    rel_y = (wy - cam.y)
    col = cfg.viewport_w // 2 + int(round(rel_x))
    row = cfg.viewport_h // 2 + int(round(rel_y))
    return col, row

def is_visible(wx: float, wy: float, cam: "Camera", cfg: Config) -> bool:
    col, row = world_to_cell(wx, wy, cam, cfg)
    return 0 <= col < cfg.viewport_w and 0 <= row < cfg.viewport_h
```

### 4.3 `rules/weapons.py` — 무기 1종 발사 판정 (순수, 최근접 타게팅)

```python
def select_target(player_pos, enemies, cfg: Config):
    # 순수 함수: 부수효과 없음. 최근접 적 선택.
    # 타이브레이크: 거리 동률이면 최저 entity id (결정성 보장 → 단위테스트 가능).
    best_id, best_d2 = None, None
    for e in enemies:                         # enemies는 읽기 전용으로만 본다
        d2 = sq_dist_aspect(player_pos, e.pos, cfg)   # 종횡비 반영 거리
        if best_d2 is None or d2 < best_d2 or (d2 == best_d2 and e.id < best_id):
            best_id, best_d2 = e.id, d2
    return best_id                            # 적 없으면 None

def should_fire(weapon_state, dt: float, cfg: Config) -> bool:
    # 쿨다운 만료 판정 (순수). 쿨다운 값은 cfg.balance에서만 읽는다.
    return weapon_state.cooldown_remaining - dt <= 0.0
```

### 4.4 `sim/step.py` — 틱 파이프라인 골격 (불변성 경계 주석)

```python
import random

def new_run(cfg: Config, rng: random.Random) -> "SimState":
    # 가변 시뮬레이션 상태 생성. rng 주입으로 결정성 확보.
    ...

def step(state: "SimState", intent, cfg: Config, rng: random.Random) -> None:
    # ┌─ 불변성 경계 (ADR-001) ─────────────────────────────────────┐
    # │ 이 함수 내부에서만 state 엔티티 버퍼를 제자리 갱신한다.      │
    # │ rules/* 순수 함수는 읽기 전용 입력만 받고 값을 반환한다.     │
    # │ 가변 상태는 이 함수 밖으로 누출되지 않는다.                  │
    # └────────────────────────────────────────────────────────────┘
    apply_input(state.player, intent)                 # 1) 구현
    maybe_spawn(state, cfg, rng)                       # 2) 최소 (평탄 비율; 디렉터 곡선 placeholder → Phase 2)
    move_enemies_toward_player(state)                  # 3) 구현 (추적)
    fire_weapons(state, cfg, rng)                      # 4) 구현 (rules.weapons 순수 호출)
    advance_projectiles(state)                         # 5) 구현 (이동/수명)
    grid = SpatialHash.build(state, cfg.entity_cap)    # 6) 충돌 질의용 공간 해시
    resolve_collisions(state, grid, cfg)               #    구현 (rules.damage; 넉백 방향·크기 포함)
    drop_xp_on_death(state, rng)                       # 7) 구현
    collect_pickups(state, cfg)                        # 8) 구현 (rules.leveling → level_up_pending 설정)
    cleanup_dead_and_far(state, cfg)                   # 9) 구현 (entity_cap·디스폰)
    state.camera.follow(state.player)                  # 10) 구현
    # evolution / 다중 무기 / hazard 단계는 Phase 1에 없음 (후속 Phase)
```

### 4.5 `loop.py` — fixed-timestep 루프 골격 (마스터 부록 A)

```python
from time import monotonic
import random

def run(term, cfg: Config, rng: random.Random) -> None:
    sim = new_run(cfg, rng)
    sim_dt = 1.0 / cfg.sim_tps          # 타이밍은 cfg에서만 (숫자 리터럴 금지)
    acc, last, mode = 0.0, monotonic(), "play"

    while True:
        key = term.inkey(timeout=cfg.poll_timeout)
        intent = map_key(key)
        if intent == "quit":
            break
        if mode == "play":
            now = monotonic(); acc += now - last; last = now
            steps = 0
            while acc >= sim_dt and steps < cfg.max_catchup:   # 따라잡기 상한
                step(sim, intent, cfg, rng)                    # §5.4 제자리 갱신
                acc -= sim_dt; steps += 1
            if sim.level_up_pending:
                mode = "levelup"
            if sim.player.hp <= 0:
                mode = "gameover"
            render_frame(term, sim, sim.camera, cfg)           # 가시 영역만
        elif mode == "levelup":
            handle_levelup_choice(sim, intent, cfg)            # rules.leveling 순수 적용
            if not sim.level_up_pending:
                mode, last = "play", monotonic()
        # pause / gameover 처리
```

---

## 5. Acceptance Criteria

| # | 기준 | 검증 절차 | 통과 |
| --- | --- | --- | --- |
| A1 | 전체 패키지 import 무오류 | `python -c "import terminal_vs.__main__"` → exit code 0 | [ ] |
| A2 | config 로드·폴백·범위검증 동작 | `python -m pytest tests/test_config.py -q` → exit code 0 | [ ] |
| A3 | 성능 수치 하드코딩 0건 | `grep -rEn 'sim_tps ?= ?[0-9]\|timeout=[0-9]\|viewport_[wh] ?= ?[0-9]\|entity_cap ?= ?[0-9]' terminal_vs/` → 매치 0 (모두 cfg 경유) | [ ] |
| A4 | world 좌표·종횡비·컬링 결정적 | `python -m pytest tests/test_world.py -q` → exit code 0 | [ ] |
| A5 | spatial hash 정확성 | `python -m pytest tests/test_spatial.py -q` → exit code 0 (브루트포스 일치) | [ ] |
| A6 | sim step 결정성 | `python -m pytest tests/test_sim_step.py -q` → exit code 0 (동일 시드 2회 일치) | [ ] |
| A7 | 무기 최근접+타이브레이크 결정적 | `python -m pytest tests/test_weapons.py -q` → exit code 0 (최저 id 타이브레이크 단언 포함) | [ ] |
| A8 | 데미지·경험치·레벨업 1택 | `python -m pytest tests/test_damage.py tests/test_leveling.py -q` → exit code 0 (`roll_choices` 길이 1, `accrue_xp` 불변) | [ ] |
| A9 | rules 계층 blessed 비의존 | `grep -rEn 'import blessed\|from blessed' terminal_vs/rules/ terminal_vs/sim/ terminal_vs/world.py` → 0건 | [ ] |
| A10 | 헤드리스 통합 한 판 폐쇄 | `python -m pytest tests/test_integration_run.py -q` → exit code 0 (레벨업 1회 발생 + 시드 일치) | [ ] |
| A11 | 전체 헤드리스 테스트 | `python -m pytest tests/ -q` → exit code 0 | [ ] |
| A12 | 대화형 수직 슬라이스 관측 | qa-tester(tmux): Day 5 종료 조건 (a)~(e) 5항목 관측 로그 기록 | [ ] |

---

## 6. Risks & Mitigations

| 위험 | 가능성 | 영향 | 완화 |
| --- | --- | --- | --- |
| 대화형 검증이 자동화 불가(실시간 TUI) | 높음 | 중 | 관측 가능 proxy로 번역(Day 5 (a)~(e) 5항목 로그), 헤드리스 통합 테스트로 루프 폐쇄를 별도 보장(A10) |
| Phase 0 산출값 미확정 상태로 착수 | 중 | 높음 | Entry gate에서 `tuning.toml` 초기값 존재 강제. 미확정 시 Day 1 진입 차단(Dependencies) |
| 성능 수치 하드코딩 혼입 | 중 | 중 | grep 종료 조건(A3)으로 매 Day 검출, 모든 의사 코드 cfg 참조 |
| 불변성 경계 누출(가변 상태가 rules/render로) | 중 | 높음 | `code-reviewer` 경계 검토(Day 3), grep으로 sim 외부 mutate 검출, step 경계 주석 강제 |
| 타게팅 비결정성으로 테스트 flaky | 중 | 중 | 최저 id 타이브레이크 규칙 명시, 시드 주입(`random.Random`) 결정성 테스트(A6,A7) |
| 수직 슬라이스 범위 초과(다중 무기·진화 끌어들임) | 중 | 높음 | §3.1 구현/연기 표 고수, evolution stub 강제, Out of scope 명시 |
| render 작업이 testable rules에 밀려 미흡 | 중 | 중 | render/loop를 독립 Day(Day 5)로 분리, qa-tester 대화형 proxy 별도 배정 |

---

## 7. Exit Gate — Phase 2로 넘어가는 체크리스트

마스터 §10 Phase 1 Exit("이동하며 적을 자동으로 잡고 경험치로 레벨업한다"가 플레이 가능)를 다음 관측 가능 기준으로 구체화한다.

- [ ] **헤드리스 단위테스트 통과**: `python -m pytest tests/ -q` → exit code 0 (rules: 무기 발사 판정·충돌 데미지·경험치 적립·레벨업 트리거 포함)
- [ ] **import smoke**: `python -c "import terminal_vs.__main__"` → exit code 0
- [ ] **헤드리스 통합 한 판**: `python -m pytest tests/test_integration_run.py -q` → exit code 0 (시작 레벨 1 → N틱 후 `level >= 2`, `level_up_pending` 1회 이상 True, 동일 시드 2회 결과 일치)
- [ ] **성능 수치 외부화**: `grep -rEn 'sim_tps ?= ?[0-9]|timeout=[0-9]|viewport_[wh] ?= ?[0-9]|entity_cap ?= ?[0-9]' terminal_vs/` → 매치 0 (모두 `cfg.`·`config/tuning.toml` 경유)
- [ ] **blessed 경계**: `grep -rEn 'import blessed|from blessed' terminal_vs/rules/ terminal_vs/sim/ terminal_vs/world.py` → 0건
- [ ] **구현/연기 분할 준수**: `rules/evolution.py`가 stub(`grep -n 'Phase 2' terminal_vs/rules/evolution.py` 매치 존재), `sim/spawn.py`에 디렉터 곡선 placeholder 마커 존재
- [ ] **대화형 플레이 1회 관측**(qa-tester/tmux): `run.sh` 실행 후 Day 5 종료 조건 (a)~(e) 5항목 — 플레이어 이동, 적 추적 접근, 자동 발사·적 처치·경험치 드랍, HUD 경험치 바 > 0 및 레벨 ≥ 2, 레벨업 오버레이 렌더·선택 적용·`play` 복귀 — 가 모두 관측되고 로그로 기록됨

위 모든 체크가 충족되면 Phase 2(무기/패시브/진화 + MVP 콘텐츠)로 진입한다.
