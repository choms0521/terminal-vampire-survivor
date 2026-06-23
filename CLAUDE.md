# CLAUDE.md — terminal-vampire-survivor

Vampire Survivors 계열의 실시간 생존 로그라이트(bullet heaven)를 터미널(TUI)로
이식하는 프로젝트다. 스택은 Python 3 + `blessed`. 설계·기술 계획은
`docs/plan/` 아래의 마스터 계획서를 참조한다.

## 문서 저장 규칙 (Document organization)

이 저장소의 기획·개발 문서는 아래 규칙에 따라 배치한다.

- **기획 문서**(설계·기획·마스터 계획) → `docs/plan/<YYYY-MM-DD>/`
- **상세개발 계획 문서**(phase별 상세 개발 계획) → `docs/development/<YYYY-MM-DD>/`

세부 규칙:

1. 모든 문서는 **작성일 기준 날짜 폴더**(`YYYY-MM-DD` 형식) 아래에 저장한다.
   예: `2026-06-23`.
2. 기획 문서는 `docs/plan/` 아래, 상세개발 계획 문서는 `docs/development/` 아래에 둔다.
3. 새 문서를 만들 때는 **오늘 날짜**로 폴더를 생성해 그 안에 저장한다.
   기존 문서는 원래의 작성일 폴더를 유지한다.

예시:

- `docs/plan/2026-06-23/work-plan-v1.md` — 마스터 설계·기술 계획서(기획 문서)
- `docs/development/2026-06-23/phase-0-render-spike.md` — (향후) 상세개발 계획 문서

이 저장소에서 문서를 생성하거나 이동할 때는 위 레이아웃을 따른다.

## 코드 규약 (요약)

- 결정적 무작위: `random.Random` 인스턴스 주입(테스트 결정성).
- 렌더/로직 분리: 규칙 계층은 `blessed`에 의존하지 않는다.
- 식별자·주석·문자열은 표준 기술 영어. 한자(중국어 문자) 사용 금지.
- 자세한 내용은 `docs/plan/`의 계획서 §13 및 ADR-001(불변성 정책)을 참조.

## Git 워크플로 (브랜치 & PR)

이 저장소의 `main` 브랜치는 보호 규칙(branch protection)이 걸려 있어, 변경은 PR을 거쳐야 한다.

- **새 작업은 반드시 feature 브랜치를 먼저 만들고**, 작업을 쌓은 뒤 `gh pr create --base main`으로 PR을 열어 올린다.
- `main`에 직접 push하여 보호 규칙을 bypass하지 않는다.
- 예외: 사용자가 명시적으로 직접 push를 지시한 경우에 한한다.
