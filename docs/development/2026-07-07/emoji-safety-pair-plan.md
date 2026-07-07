# 상세개발 계획 — 이모지 안전쌍 (3.1 + 3.2)

- 작성일: 2026-07-07
- 문서 종류: 상세개발 계획(feature-level). 백로그 `docs/plan/2026-07-07/future-specs-backlog.md`의 3.1 / 3.2 항목을 착수 계획으로 구체화한다.
- 결정 주체: PO 검토(OMC planner, Opus) + 코드 대조 + advisor 검증.

## 1. 개요

| 항목 | 내용 |
|---|---|
| Goal | 방금 shipped 기본값으로 뒤집은 emoji 렌더(PR #11·#12)의 유일한 미굳힘 위험(비-emoji 터미널에서 화면 깨짐 + 사용자가 복구법 모름)을 저비용으로 제거한다. |
| Scope in | (3.1) `run.sh --ascii/--emoji` 플래그 + README 호환성 안내. (3.2) 비-UTF-8 터미널 자동 ascii 폴백(`__main__` 순수 함수). |
| Scope out | 게임플레이/sim 변경 없음. 새 on-screen glyph 없음. 런타임 토글(3.3) 아님. 폰트 능력 프로빙 없음. config.py의 emoji 기본값 변경 없음. |
| Deliverables | PR A(`feat/run-sh-glyph-flags`), PR B(`feat/glyph-autodetect-fallback`). 각각 별도 브랜치·PR, main에서 분기. |
| Effort | PR A: S(반나절). PR B: S-M(반나절~하루). |
| 위험 | 매우 낮음. bash-only(A) + 순수 함수 1개(B), 결정성·폭-2 가드 무관. |

## 2. PO 결정 근거

**선정: 3.1 + 3.2 결합 안전쌍을 최우선. 그중 3.1 선봉.** 3.1은 수동 탈출구, 3.2는 자동 안전망이며, 3.2의 폴백은 곧 3.1이 노출하는 모드 선택이다. 하나의 안전 단위다.

**근거(가치 x 노력 x 위험 x 전략 적합성).** 모든 사용자의 기본 렌더 경로를 emoji로 전환했고, 딱 하나 굳히지 못한 실패 모드가 남았다: emoji를 폭-2로 못 그리는 터미널/폰트에서 화면이 깨지는데, 첫 사용자는 `TVS_GLYPH_SET=ascii` 해법을 대역 내(in-band)에서 발견할 수 없다. 소리 없이 첫인상을 죽이는 위험이며, 완화 비용은 거의 0이다(3.1 bash-only, 3.2 작은 순수 heuristic, 게임플레이/sim 무변경, 새 glyph 없음 -> 폭-2 가드·결정성 무관). 원칙: 방금 흔든 토대 위에 다음 기능을 쌓지 않는다.

**runner-up(5.1 드래프트 리롤/스킵/밴)이 먼저가 아닌 이유.** 체감 가치는 가장 크지만 (a) 방금의 위험을 전혀 건드리지 못하고(화면이 깨진 사용자에겐 좋은 드래프트도 비가시), (b) 후보 중 가장 무거우며(levelup 입력 처리 + 드래프트 재생성 + 밴 run-state + 리롤 비용 경제 + 주입 RNG 결정성), (c) 안정화된 기본값 위에 얹는 편이 낫다. 다음 차례.

### 우선순위 3걸

| 순위 | 항목 | 가치 / 노력 / 위험 |
|---|---|---|
| 1 | 3.1+3.2 이모지 안전쌍 (선정) | 출하한 기본값 보호 / S·S-M / 매우 낮음 |
| 2 | 5.1 드래프트 리롤·스킵·밴 | 높은 체감가치 / M-L / 게임플레이·결정성 |
| 3 | 7.1 이모지 폭-2 규약 문서 | 회귀 예방 / S / 코드 위험 0 |

## 3. 우선순위 사다리 (두 PR 모두 보존)

각 PR 본문에 명시한다.

1. `TVS_GLYPH_SET` env(비어있지 않음) -> 항상 우선(기존 동작 유지). `test_glyph_set_override_activates_emoji_without_toml_edit` green 유지.
2. run.sh `--ascii/--emoji` -> `TVS_GLYPH_SET`을 export -> 자식 프로세스에게는 (1)이 됨(플래그가 상속 env를 덮음). [3.1]
3. 자동감지 -> `TVS_GLYPH_SET`이 unset/empty일 때만; **명확한 비-UTF-8 신호일 때만** ascii로 내림. [3.2]
4. TOML `glyph_set = "emoji"`(shipped) -> 위가 아무것도 발동 안 하면 이것이 기본. `test_shipped_config_glyph_set_is_emoji` green 유지 -> **config.py 기본값 손대지 않음.**
5. `_TUNING_DEFAULTS["glyph_set"] = "ascii"` -> 키가 아예 없을 때만(shipped 경로 아님).

## 4. PR A — run.sh `--ascii` / `--emoji` 편의 플래그

### Goal
`./run.sh --ascii` / `--emoji`로 렌더 모드를 전환할 수 있게 한다(env 변수 몰라도 됨). 비-emoji 터미널에 한 명령 탈출구 제공.

### Scope
- in: `run.sh` 인자 파싱(`TVS_GLYPH_SET` 세팅), README 호환성 안내, 통합 테스트 1개.
- out: Python 변경 없음. `terminal_vs` 내부 argparse 도입 없음(env-only 유지). 자동감지 없음(PR B). `--help` 등 기타 플래그 없음.

### Tasks
1. `run.sh`에서 venv 활성화 블록 뒤·최종 `exec` 앞에 `"$@"` 순회: `--ascii` -> `export TVS_GLYPH_SET=ascii`, `--emoji` -> `export TVS_GLYPH_SET=emoji`, 그 외는 `PASS_ARGS` 배열에 축적. `--ascii/--emoji` 중 마지막이 이김.
2. `exec python -m terminal_vs`에 살아남은 인자 전달. macOS bash 3.2 + `set -u` 대응 위해 **빈 배열 안전 확장** `${PASS_ARGS[@]+"${PASS_ARGS[@]}"}` 사용.
3. README에 "터미널 호환성 / glyph 모드" 안내(~3줄): emoji가 shipped 기본이며, glyph이 깨지거나 어긋나면 `./run.sh --ascii`(또는 `TVS_GLYPH_SET=ascii`) 실행.

### 파일 변경
- `run.sh`: line 20 `exec python -m terminal_vs "$@"`를 위 parse-then-exec 블록으로 교체. `set -euo pipefail`·venv 가드는 그대로.
- `README.md`: ~3줄 호환성 안내 추가.
- 신규 `tests/test_run_sh.py`.

### 테스트 (결정적)
`tests/test_run_sh.py`: `subprocess.run`으로 `bash run.sh …` 실행. `tmp_path`에 스텁 `python` 스크립트를 만들어 `PATH` 앞에 얹음. 스텁은 `TVS_GLYPH_SET`(없으면 `<unset>`)과 `"$@"`를 출력 후 `exit 0`. **커밋된 venv 없음**(확인 완료)이라 스텁을 가리는 것이 없고, 스텁은 터미널을 열지 않음 -> 완전 결정적, RNG 무관.

- `test_ascii_flag_exports_ascii` -> 스텁이 `TVS_GLYPH_SET=ascii` 관측.
- `test_emoji_flag_exports_emoji` -> `emoji` 관측.
- `test_no_flag_leaves_glyph_set_unset` -> `<unset>` 관측(하류가 TOML/detect 사용).
- `test_last_glyph_flag_wins` -> `--emoji --ascii` -> `ascii`.
- `test_unknown_args_forwarded_and_flag_consumed` -> `run.sh --ascii foo --bar` -> 스텁이 `-m terminal_vs foo --bar` 수신, `--ascii`는 미수신.

### 완료 조건 (측정 가능)
- `grep -q 'TVS_GLYPH_SET=ascii' run.sh` 그리고 `grep -q 'TVS_GLYPH_SET=emoji' run.sh` 둘 다 성공.
- `bash -n run.sh` exit 0 (가능하면 `shellcheck run.sh` clean).
- `python -m pytest tests/test_run_sh.py` 통과(위 5케이스).
- `grep -q -- '--ascii' README.md` 성공.

### 위험·완화
- macOS bash 3.2 + `set -u`에서 빈 배열 `"${PASS_ARGS[@]}"`는 "unbound variable" -> `${PASS_ARGS[@]+"${PASS_ARGS[@]}"}` 사용. `test_no_flag_leaves_glyph_set_unset`(빈 PASS_ARGS)이 정확히 이 경로를 밟음.
- 상속 `TVS_GLYPH_SET` vs 전달 플래그 -> 플래그 export가 자식에게 우선. 의도된 동작으로 문서화.

### 메타
- 브랜치 `feat/run-sh-glyph-flags` · PR title `feat(run): --ascii/--emoji convenience flags for TVS_GLYPH_SET` · 노력 S.

## 5. PR B — 비-UTF-8 터미널 자동 ascii 폴백

### Goal
명시 `TVS_GLYPH_SET`이 없을 때, 환경이 **명확한 비-UTF-8 신호**를 줄 때만 ascii glyph으로 내려, 명백히 emoji 불가한 터미널이 깨진 기본을 그리지 않게 한다.

### Scope
- in: 순수 helper 2개 + `terminal_vs/__main__.py` 배선, 유닛 테스트 1개.
- out: 폰트 능력 프로빙/터미널 왕복 질의 없음. **config.py·emoji 기본값 무변경.** 런타임 토글(3.3) 아님. heuristic은 비-UTF-8 케이스만 잡음(UTF-8 로케일 + 나쁜 폰트는 감지 불가 -> 3.1 + 문서로 커버, 알려진 gap으로 명시).

### 설계
`os.environ`을 `__main__`에 유지(기존 `_make_rng`/`_glyph_set_override` 미러). heuristic은 문자열 입력 순수 함수로 유닛테스트 -> 결정성 확보.

- `_detect_glyph_fallback(stdout_encoding, lang, lc_all, lc_ctype) -> str | None` (순수): 명확한 비-UTF-8 신호일 때만 `"ascii"`, 아니면 `None`(emoji 유지). 논리: `stdout_encoding`에 `"utf"` 포함 -> `None`; elif `stdout_encoding`이 비어있지 않음(존재+비-UTF-8, 예: ascii/latin-1/cp1252) -> `"ascii"`(stdout이 실제 기록 대상의 가장 직접 신호); elif 유효 로케일(POSIX 우선순위 `LC_ALL` -> `LC_CTYPE` -> `LANG`)에 `"utf"` 포함 -> `None`; elif 그 로케일이 `"c"`/`"posix"` -> `"ascii"`; else -> `None`(애매하면 emoji 유지, 오탐 회피).
- `_resolve_glyph_override(explicit, stdout_encoding, lang, lc_all, lc_ctype) -> str | None` (순수): `if explicit: return explicit`(비어있지 않은 env가 이김); else `return _detect_glyph_fallback(...)`. **빈** `TVS_GLYPH_SET`은 "not explicit"로 취급(config.py의 `glyph_set_override or …` empty-falls-through 시맨틱과 정합) -> 빈 env여도 detect 수행.
- `main()`: `os.environ.get("TVS_GLYPH_SET")`, `sys.stdout.encoding`, `LANG`/`LC_ALL`/`LC_CTYPE`를 읽어 `override = _resolve_glyph_override(...)` 계산 -> 기존 `load_default_config(glyph_set_override=override)`에 전달.

### 파일 변경
- `terminal_vs/__main__.py`: helper 2개 추가; line 58 `cfg = load_default_config(glyph_set_override=_glyph_set_override())`를 resolve 호출로 교체; 모듈 docstring "Glyph set" 문단에 "비-UTF-8만 좁게 폴백, 명시 env는 항상 우선" 명시.
- 신규 `tests/test_glyph_autodetect.py`.
- config.py 무변경. `test_import_smoke.py`가 이미 `terminal_vs.__main__` 포함 -> MODULES 변경 불필요.

### 테스트 (결정적) — `tests/test_glyph_autodetect.py`, 문자열 직접 전달, 글로벌 monkeypatch·터미널 없음
- `test_utf8_stdout_keeps_emoji` -> `_detect_glyph_fallback("utf-8", None, None, None) is None`.
- `test_ascii_stdout_falls_back` -> `_detect_glyph_fallback("ascii", "en_US.UTF-8", None, None) == "ascii"`(stdout 우선).
- `test_c_locale_falls_back_when_no_stdout_enc` -> `_detect_glyph_fallback("", None, None, "C") == "ascii"`.
- `test_utf8_locale_keeps_emoji_without_stdout_enc` -> `_detect_glyph_fallback("", "en_US.UTF-8", None, None) is None`.
- `test_ambiguous_keeps_emoji` -> `_detect_glyph_fallback("", None, None, None) is None`.
- `test_lc_precedence` -> `LC_ALL="C"`가 `LANG="…UTF-8"`을 덮음 -> `"ascii"`.
- `test_explicit_env_beats_detection` -> `_resolve_glyph_override("emoji", "ascii", None, None, "C") == "emoji"` (및 `("ascii", "utf-8", …) == "ascii"`).
- `test_empty_explicit_runs_detection` -> `_resolve_glyph_override("", "utf-8", None, None, None) is None`.

### 완료 조건 (측정 가능)
- `python -m pytest tests/test_glyph_autodetect.py` 통과(8케이스).
- 회귀 게이트: `python -m pytest tests/test_config.py -k "glyph_set or shipped_config"` 통과(기본값·명시 오버라이드 불변).
- 전체 게이트: `python -m pytest && python selftest.py && ruff check` 모두 exit 0. (rules/config 무변경 -> 80% 커버리지 게이트 무영향. `__main__`은 설계상 `--cov` 범위 밖 -> 커버리지 위해 env 로직을 config.py로 옮기지 않음.)
- `grep -q "utf" terminal_vs/__main__.py`(heuristic이 config.py 아닌 `__main__`에 존재).

### 위험·완화
- 유능한 터미널 오탐 강등(방금 보호하려는 기본값을 해침) -> 명확한 비-UTF-8 신호일 때만 `"ascii"`; 애매하면 emoji; 명시 env는 항상 우선; 유닛테스트가 애매 케이스를 `None`으로 고정.
- 미탐(UTF-8 로케일 + emoji 불가 폰트)은 감지 불가 -> 설계상 out of scope; 3.1 `--ascii` + README 안내로 커버(PR 본문에 명시하여 reviewer가 heuristic을 완전한 net으로 오독하지 않게).
- 결정성/커버리지 -> 문자열 입력 순수 함수, RNG 없음, 글로벌 monkeypatch 없음, rules/config 무변경.

### 메타
- 논리적으로 PR A에 의존(폴백이 고르는 수동 오버라이드이자 문서가 가리키는 대상)이나 기술적으로 독립. A 이후 ship.
- 브랜치 `feat/glyph-autodetect-fallback` · PR title `feat(launch): auto-fallback to ascii glyphs on non-UTF-8 terminals` · 노력 S-M.

## 6. 백로그 대비 정정 (코드 대조 결과)

- 3.1 "미지의 플래그는 `python -m terminal_vs`로 통과": `__main__`은 argparse/`sys.argv` 미사용(env-only)이라 오늘은 forwarding이 무해한 no-op. 그래도 `--ascii/--emoji`만 소비하고 나머지는 전달해 미래 대비.
- 3.1 완료 조건이 게임 프로세스 실행을 암시: blessed 터미널을 열어 headless 단언 불가 -> 스텁-python-on-PATH subprocess 테스트로 대체(커밋된 venv 없어 견고). Python 계층 계약(`load_default_config(glyph_set_override="ascii").glyph_set == "ascii"`)은 `tests/test_config.py`가 이미 커버.
- 3.2 배치: 감지는 `__main__`에 위치(`_make_rng`처럼)하여 `load_default_config(glyph_set_override=…)`에 공급. config.py의 shipped emoji 기본값을 바꾸면 `test_shipped_config_glyph_set_is_emoji`가 깨짐 -> 절대 변경 금지. heuristic은 정직하게 비-UTF-8 케이스만 잡음 -> 3.2를 "일반 auto-detect"가 아닌 "좁고 오탐-회피"로 재정의.

## 7. 착수 순서

PR A 먼저(코드 위험 0, 분 단위 mergeable, 즉시 한 명령 완화 + 문서 안내 제공) -> PR B(오탐 위험 고려한 heuristic, 자체 PR로 A의 수동 오버라이드 위에 구축). 둘 다 `main`에서 분기(emoji 작업은 이미 merged; 다른 feature 브랜치에서 분기 금지).
