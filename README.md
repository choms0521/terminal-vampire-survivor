# terminal-vampire-survivor

A terminal (TUI) port of the "bullet heaven" survival roguelite popularized by
*Vampire Survivors*: you only move, your weapons fire on their own, and waves of
enemies pour in while you collect gems, level up, and combine weapons into
powerful evolutions — all rendered in the terminal with truecolor ASCII.

> **Status: planning.** No playable build yet. The design and technical plan
> lives in [`docs/plan/2026-06-23/work-plan-v1.md`](docs/plan/2026-06-23/work-plan-v1.md).

## Vision

- Real-time, tick-based survival in a scrolling ASCII arena.
- Move-only controls; automatic, timer-driven weapons.
- Pick up gems → level up → choose weapon/passive upgrades → evolve weapons.
- A difficulty director that escalates spawns over a ~15–30 minute run.

## Tech stack

- Python 3
- [`blessed`](https://pypi.org/project/blessed/) for terminal rendering and input

## Getting started (planned)

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python -m terminal_vs   # entry point (to be implemented)
```

## Documentation

- [Master design & technical plan](docs/plan/2026-06-23/work-plan-v1.md)

## License

TBD.
