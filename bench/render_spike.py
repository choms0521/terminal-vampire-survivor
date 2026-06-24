#!/usr/bin/env python3
"""bench/render_spike.py - Phase 0 render-throughput stress harness.

Measures how many moving glyphs a terminal can sustain-render, to fix the
(entity_cap N, sim TPS, viewport W x H) operating point for downstream phases.

Two deliberately separated code paths (master plan section 13, phase-0 doc S4):

  * measure(): runs on a REAL TTY and times sustained rendering. blessed is used
    only here, for fullscreen()/hidden_cursor() terminal setup. Piped/redirected
    output is rejected (blessed drops escapes when stdout is not a TTY, which
    would make the byte measurement meaningless).

  * selftest() / verify_bytes(): headless, no TTY, no blessed import. They reuse
    the pure frame-composition logic. CI/pipe safe, exit 0.

Primary metric is bytes-per-frame (master section 3.3: the bottleneck is the
terminal I/O throughput - how many bytes can be written per frame - not Python
compute). FPS is a derived result.

Frame composition (compose_cells / render_full / render_diff) is pure and
blessed-independent: it emits standard ANSI/VT escapes directly (CUP cursor
moves and 24-bit truecolor SGR), which are equivalent to what blessed emits on a
modern truecolor terminal. Generating them directly keeps the byte count
deterministic and lets the headless selftest/verify_bytes paths exercise the
exact same code the real-TTY measurement runs.
"""

from __future__ import annotations

import argparse
import os
import random
import socket
import sys
import time
from dataclasses import dataclass

# --- ANSI/VT escape primitives (standard sequences; pure, deterministic) ------
ESC = "\x1b"
SGR_RESET = f"{ESC}[0m"

# Cosmetic glyph variety; assigned deterministically by index.
GLYPH_CHARS = "@#$%&*+=oO"


def sgr_truecolor(rgb: tuple[int, int, int]) -> str:
    """24-bit foreground SGR. ~19 bytes - the dominant per-cell color cost."""
    r, g, b = rgb
    return f"{ESC}[38;2;{r};{g};{b}m"


def cursor_move(y: int, x: int) -> str:
    """1-based row;col cursor move (CUP). Equivalent to blessed term.move_yx."""
    return f"{ESC}[{y + 1};{x + 1}H"


# --- Immutable measurement config (injected read-only, like the game config) --
@dataclass(frozen=True)
class BenchConfig:
    glyphs: int          # N: number of moving glyphs
    mode: str            # "full" | "diff"
    color_freq: float    # 0.0..1.0: fraction of glyphs truecolor-rendered/frame
    vw: int              # viewport width (cols)
    vh: int              # viewport height (rows)
    duration: float      # sustained measurement seconds (excludes 1s warmup)
    seed: int = 1234         # deterministic glyph motion + color
    target_fps: float = 20.0  # target FPS floor; recorded with the result row


# --- Mutable glyph buffer: in-place advance is the ADR-001 section 6 carve-out -
class Glyphs:
    """Parallel-array glyph buffer, mutated in place inside the measure loop.

    In-place mutation here is deliberate: the measure loop mirrors the real
    game's sim-step, which mutates in place for throughput (ADR-001 section 6).
    The buffer must not leak outside the measure loop.

    color_freq decides how many glyphs are truecolor-rendered: glyphs with index
    < round(color_freq * N) carry an rgb that is re-randomized every frame (the
    "frequently changing color" cost), the rest carry None (default color). This
    makes bytes-per-frame monotonically non-decreasing in color_freq (0.0 = no
    truecolor escapes, 1.0 = every glyph emits a fresh truecolor escape/frame).
    """

    def __init__(self, cfg: BenchConfig, rng: random.Random) -> None:
        n = cfg.glyphs
        self.xs = [rng.randrange(cfg.vw) for _ in range(n)]
        self.ys = [rng.randrange(cfg.vh) for _ in range(n)]
        self.dxs: list[int] = []
        self.dys: list[int] = []
        for _ in range(n):
            dx = dy = 0
            while dx == 0 and dy == 0:           # never a stationary glyph
                dx = rng.randint(-1, 1)
                dy = rng.randint(-1, 1)
            self.dxs.append(dx)
            self.dys.append(dy)
        self.chars = [GLYPH_CHARS[i % len(GLYPH_CHARS)] for i in range(n)]
        self._n_colored = round(cfg.color_freq * n)
        self.colors: list[tuple[int, int, int] | None] = [
            self._rand_rgb(rng) if i < self._n_colored else None for i in range(n)
        ]

    @staticmethod
    def _rand_rgb(rng: random.Random) -> tuple[int, int, int]:
        return (rng.randint(64, 255), rng.randint(64, 255), rng.randint(64, 255))

    def advance(self, cfg: BenchConfig, rng: random.Random) -> None:
        """Move ~1 cell/frame with boundary reflection; recolor colored glyphs."""
        vw, vh = cfg.vw, cfg.vh
        xs, ys, dxs, dys, colors = self.xs, self.ys, self.dxs, self.dys, self.colors
        for i in range(cfg.glyphs):
            nx = xs[i] + dxs[i]
            if nx < 0 or nx >= vw:
                dxs[i] = -dxs[i]
                nx = xs[i] + dxs[i]
            ny = ys[i] + dys[i]
            if ny < 0 or ny >= vh:
                dys[i] = -dys[i]
                ny = ys[i] + dys[i]
            # Reflection is exact for viewports >= 2 (the CLI guard), so this
            # clamp is the identity there and does not affect any measurement.
            # It only defends compose_cells against a future caller building a
            # degenerate 1-wide/1-tall BenchConfig (would otherwise IndexError).
            xs[i] = 0 if nx < 0 else (vw - 1 if nx >= vw else nx)
            ys[i] = 0 if ny < 0 else (vh - 1 if ny >= vh else ny)
            if i < self._n_colored:
                colors[i] = self._rand_rgb(rng)


# --- Pure frame composition (blessed-independent; reused by selftest) ----------
Cell = tuple  # (char: str, rgb: tuple[int,int,int] | None)
Grid = list   # list[list[Cell]], vh rows x vw cols

BLANK: Cell = (" ", None)


def compose_cells(cfg: BenchConfig, g: Glyphs) -> Grid:
    """Pure: compose the viewport grid (vh rows x vw cols of immutable cells).

    Empty cell = (" ", None). Overlap resolved by draw priority: last glyph wins.
    """
    grid: Grid = [[BLANK] * cfg.vw for _ in range(cfg.vh)]
    xs, ys, chars, colors = g.xs, g.ys, g.chars, g.colors
    for i in range(cfg.glyphs):
        grid[ys[i]][xs[i]] = (chars[i], colors[i])
    return grid


def changed_cells(prev: Grid, cur: Grid) -> list[tuple[int, int, str, object]]:
    """Pure: (y, x, char, rgb) for every cell that differs. Reused by render_diff
    and selftest. Changed-cell count is ~2N (a glyph vacates one cell and fills
    another), versus full's W x H."""
    out: list[tuple[int, int, str, object]] = []
    for y, (prow, crow) in enumerate(zip(prev, cur)):
        for x, (pcell, ccell) in enumerate(zip(prow, crow)):
            if pcell != ccell:
                char, rgb = ccell
                out.append((y, x, char, rgb))
    return out


def render_full(cells: Grid) -> str:
    """Pure: full-frame string built by positioning each row explicitly.

    No screen clear; every cell (including blanks) is emitted, so rows are fixed
    width and ghosts are overwritten (master section 3.6). Each row is placed
    with an explicit cursor move instead of a trailing newline, so the frame
    never emits a newline past the last row (which would scroll the viewport when
    its height equals the terminal height) and never depends on terminal
    auto-wrap. Truecolor SGR is emitted only when the color changes from the
    previous cell (last-color caching; cursor moves do not reset SGR), and reset
    at end-of-frame.
    """
    out: list[str] = []
    last_color: object = "init"          # sentinel != any rgb and != None
    for y, row in enumerate(cells):
        out.append(cursor_move(y, 0))
        for char, rgb in row:
            if rgb != last_color:
                out.append(SGR_RESET if rgb is None else sgr_truecolor(rgb))
                last_color = rgb
            out.append(char)
    out.append(SGR_RESET)
    return "".join(out)


def render_diff(prev: Grid, cur: Grid) -> str:
    """Pure: emit only changed cells (cursor move + optional SGR + char).

    Raw ANSI (CUP + truecolor SGR) is a deliberate choice: it keeps composition
    pure and byte-deterministic (phase-0 doc section 4) and is equivalent to
    blessed's move_yx/color output; blessed is reserved for fullscreen()/
    hidden_cursor() in measure(). Color is set per cell (it cannot be cached
    across non-contiguous writes) and reset after a colored glyph, so a blanked
    cell never inherits a stale color.
    """
    out: list[str] = []
    for y, x, char, rgb in changed_cells(prev, cur):
        out.append(cursor_move(y, x))
        if rgb is None:
            out.append(char)
        else:
            out.append(sgr_truecolor(rgb))
            out.append(char)
            out.append(SGR_RESET)
    return "".join(out)


# --- Statistics ----------------------------------------------------------------
def percentile(sorted_vals: list[float], q: float) -> float:
    """Linear-interpolation percentile. Empty -> 0.0."""
    if not sorted_vals:
        return 0.0
    idx = q * (len(sorted_vals) - 1)
    lo = int(idx)
    hi = min(lo + 1, len(sorted_vals) - 1)
    frac = idx - lo
    return sorted_vals[lo] * (1.0 - frac) + sorted_vals[hi] * frac


def summarize(frame_ms: list[float], frame_bytes: list[int], cfg: BenchConfig) -> dict:
    """Reduce per-frame samples to the four reported metrics + env meta.

    Guards against an empty sample list (e.g. --duration < warmup): reports zeros
    rather than dividing by zero.
    """
    if frame_ms:
        ordered = sorted(frame_ms)
        mean_ms = sum(frame_ms) / len(frame_ms)
        fps = 1000.0 / mean_ms if mean_ms > 0 else 0.0
        p50 = percentile(ordered, 0.50)
        p95 = percentile(ordered, 0.95)
        bpf = sum(frame_bytes) / len(frame_bytes)
        nframes = len(frame_ms)
    else:
        fps = p50 = p95 = bpf = 0.0
        nframes = 0
    return {
        "env": env_meta(),
        "viewport": f"{cfg.vw}x{cfg.vh}",
        "mode": cfg.mode,
        "color_freq": cfg.color_freq,
        "N": cfg.glyphs,
        "target_fps": cfg.target_fps,
        "frames": nframes,
        "fps_sustained": round(fps, 2),
        "bytes_per_frame": round(bpf, 1),
        "frame_ms_p50": round(p50, 3),
        "frame_ms_p95": round(p95, 3),
    }


# --- Environment metadata (every field non-empty; A7 forbids ',,') ------------
def iso_now() -> str:
    import datetime

    return datetime.datetime.now().astimezone().replace(microsecond=0).isoformat()


def env_meta() -> dict:
    def get(name: str, default: str = "-") -> str:
        v = os.environ.get(name, "").strip()
        return v if v else default

    is_ssh = "ssh" if (os.environ.get("SSH_CONNECTION") or os.environ.get("SSH_TTY")) else "local"
    emulator = get("TERM_PROGRAM")
    if emulator == "-":
        emulator = get("LC_TERMINAL")
    try:
        cols, rows = os.get_terminal_size()
        geom = f"{cols}x{rows}"
    except OSError:
        geom = "-"
    return {
        "timestamp": iso_now(),
        "host": socket.gethostname() or "-",
        "emulator": emulator,
        "term": get("TERM"),
        "colorterm": get("COLORTERM"),
        "net": is_ssh,
        "geom": geom,
    }


# --- CSV emission --------------------------------------------------------------
CSV_COLUMNS = [
    "timestamp", "host", "emulator", "term", "colorterm", "net", "geom",
    "viewport", "mode", "color_freq", "N", "target_fps", "frames",
    "fps_sustained", "bytes_per_frame", "frame_ms_p50", "frame_ms_p95",
]


def _csv_field(value: object) -> str:
    s = str(value).strip()
    if s == "":
        s = "-"                          # never emit an empty field (A7)
    if "," in s or '"' in s:
        s = '"' + s.replace('"', '""') + '"'
    return s


def csv_row(result: dict) -> str:
    e = result["env"]
    values = [
        e["timestamp"], e["host"], e["emulator"], e["term"], e["colorterm"],
        e["net"], e["geom"],
        result["viewport"], result["mode"], result["color_freq"], result["N"],
        result["target_fps"], result["frames"], result["fps_sustained"],
        result["bytes_per_frame"], result["frame_ms_p50"], result["frame_ms_p95"],
    ]
    return ",".join(_csv_field(v) for v in values)


def emit_csv(result: dict, out_path: str | None) -> None:
    header = ",".join(CSV_COLUMNS)
    line = csv_row(result)
    if out_path is None:
        print(header)
        print(line)
        return
    directory = os.path.dirname(out_path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    need_header = (not os.path.exists(out_path)) or os.path.getsize(out_path) == 0
    with open(out_path, "a", encoding="utf-8") as f:
        if need_header:
            f.write(header + "\n")
        f.write(line + "\n")


# --- Real-TTY measurement (the only blessed-dependent path) -------------------
def measure(term, cfg: BenchConfig) -> dict:
    rng = random.Random(cfg.seed)        # deterministic injection (section 13)
    g = Glyphs(cfg, rng)
    prev_cells: Grid | None = None
    frame_ms: list[float] = []
    frame_bytes: list[int] = []
    start = time.monotonic()
    warmup_until = start + 1.0           # exclude first 1s from statistics
    end = start + cfg.duration + 1.0
    write = sys.stdout.write
    flush = sys.stdout.flush
    with term.fullscreen(), term.hidden_cursor():
        while time.monotonic() < end:
            t0 = time.perf_counter()
            g.advance(cfg, rng)
            cur = compose_cells(cfg, g)
            bootstrap_full = prev_cells is None      # diff mode renders frame 0 full
            if cfg.mode == "full" or bootstrap_full:
                frame = render_full(cur)
            else:
                frame = render_diff(prev_cells, cur)
            write(frame)                 # single write; bytes = the primary metric
            flush()
            prev_cells = cur
            dt = time.perf_counter() - t0
            # Exclude the warmup window and, in diff mode, the one bootstrap full
            # frame (a full render that would contaminate the diff distribution).
            counts = cfg.mode == "full" or not bootstrap_full
            if counts and time.monotonic() >= warmup_until:
                frame_ms.append(dt * 1000.0)
                # Frames are ASCII-only (ANSI escapes + digits + ASCII glyphs),
                # so len(frame) equals the UTF-8 byte length; skipping the
                # per-frame encode() keeps the measurement loop lean.
                frame_bytes.append(len(frame))
    return summarize(frame_ms, frame_bytes, cfg)


# --- Headless logic smoke (no TTY, no blessed; exit 0) ------------------------
def selftest() -> int:
    cfg = BenchConfig(glyphs=20, mode="diff", color_freq=0.5, vw=40, vh=12, duration=0.0, seed=1)
    rng = random.Random(cfg.seed)
    g = Glyphs(cfg, rng)
    c0 = compose_cells(cfg, g)
    assert len(c0) == cfg.vh and all(len(r) == cfg.vw for r in c0), "grid shape"
    g.advance(cfg, rng)
    c1 = compose_cells(cfg, g)
    assert len(changed_cells(c0, c1)) > 0, "motion must change cells"
    full = render_full(c1)
    assert len(full) > 0, "full frame must produce bytes"
    # ASCII-only is a measurement invariant: it lets bytes_per_frame use
    # len(frame) instead of an encode() (see measure()/_mean_bytes).
    assert full.isascii(), "full frame must be ASCII-only"
    assert render_diff(c0, c1).isascii(), "diff frame must be ASCII-only"
    return 0


# --- Headless byte-criteria check (A4/A5/A6; TTY-independent by construction) --
def _mean_bytes(glyphs: int, mode: str, color_freq: float,
                vw: int = 100, vh: int = 30, seed: int = 1, frames: int = 30) -> int:
    cfg = BenchConfig(glyphs=glyphs, mode=mode, color_freq=color_freq,
                      vw=vw, vh=vh, duration=0.0, seed=seed)
    rng = random.Random(cfg.seed)
    g = Glyphs(cfg, rng)
    g.advance(cfg, rng)
    prev = compose_cells(cfg, g)         # warmup frame establishes diff baseline
    total = 0
    for _ in range(frames):
        g.advance(cfg, rng)
        cur = compose_cells(cfg, g)
        frame = render_full(cur) if mode == "full" else render_diff(prev, cur)
        total += len(frame)                  # ASCII-only frame: chars == bytes
        prev = cur
    return total // frames


def verify_bytes() -> int:
    # A4: the four metric keys are emitted.
    sample = summarize([5.0, 6.0, 7.0], [1000, 1100, 1200],
                       BenchConfig(10, "full", 0.0, 100, 30, 0.0))
    for key in ("fps_sustained", "bytes_per_frame", "frame_ms_p50", "frame_ms_p95"):
        assert key in sample, f"A4 missing metric key: {key}"
    # A5: more color -> not fewer bytes (full mode, fixed N/viewport).
    b_c0 = _mean_bytes(200, "full", 0.0)
    b_c1 = _mean_bytes(200, "full", 1.0)
    assert b_c1 >= b_c0, f"A5 color bytes not monotone: c1={b_c1} < c0={b_c0}"
    # A6: diff cheaper than full at low N.
    b_full = _mean_bytes(50, "full", 0.0)
    b_diff = _mean_bytes(50, "diff", 0.0)
    assert b_diff < b_full, f"A6 diff not cheaper at low N: diff={b_diff} full={b_full}"
    print(f"verify-bytes OK: A4 keys=4/4  "
          f"A5 full color0={b_c0} color1={b_c1} (c1>=c0)  "
          f"A6 N50 full={b_full} diff={b_diff} (diff<full)")
    return 0


# --- CLI -----------------------------------------------------------------------
def parse_viewport(spec: str) -> tuple[int, int]:
    try:
        w_str, h_str = spec.lower().split("x")
        w, h = int(w_str), int(h_str)
    except ValueError:
        raise SystemExit(f"invalid --viewport {spec!r}; expected WxH like 100x30")
    if w < 2 or h < 2:
        raise SystemExit(f"--viewport too small {spec!r}; need at least 2x2")
    return w, h


def build_config(args: argparse.Namespace) -> BenchConfig:
    vw, vh = parse_viewport(args.viewport)
    return BenchConfig(
        glyphs=args.glyphs, mode=args.mode, color_freq=args.color_freq,
        vw=vw, vh=vh, duration=args.duration, seed=args.seed,
        target_fps=args.target_fps,
    )


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="render_spike",
        description="Phase 0 render-throughput stress harness (terminal-vampire-survivor)",
    )
    p.add_argument("--glyphs", type=int, default=100, help="N: number of moving glyphs")
    p.add_argument("--mode", choices=["full", "diff"], default="full", help="render mode")
    p.add_argument("--color-freq", type=float, default=0.0,
                   help="0.0..1.0 fraction of glyphs truecolor-rendered each frame")
    p.add_argument("--viewport", default="100x30", help="viewport WxH, e.g. 100x30")
    p.add_argument("--duration", type=float, default=10.0,
                   help="sustained measurement seconds (excludes 1s warmup)")
    p.add_argument("--target-fps", type=float, default=20.0,
                   help="target FPS floor, recorded for the operating-point decision")
    p.add_argument("--seed", type=int, default=1234, help="deterministic glyph-motion seed")
    p.add_argument("--out", default=None, help="CSV append path (env meta + metrics)")
    p.add_argument("--selftest", action="store_true",
                   help="headless logic smoke; no TTY required; exit 0")
    p.add_argument("--verify-bytes", action="store_true",
                   help="headless byte-criteria check (A4/A5/A6); no TTY; exit 0")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.selftest:
        return selftest()
    if args.verify_bytes:
        return verify_bytes()

    if args.glyphs < 1:
        raise SystemExit("--glyphs must be >= 1")
    if not (0.0 <= args.color_freq <= 1.0):
        raise SystemExit("--color-freq must be in [0.0, 1.0]")

    import blessed                        # measurement path only

    term = blessed.Terminal()
    if not term.is_a_tty:
        sys.stderr.write(
            "render_spike: measurement requires a real TTY (blessed drops escape "
            "sequences when stdout is piped/redirected, which voids the byte "
            "measurement). Use --selftest or --verify-bytes for headless checks.\n"
        )
        return 2
    cfg = build_config(args)
    if cfg.vw > term.width or cfg.vh > term.height:
        sys.stderr.write(
            f"render_spike: viewport {cfg.vw}x{cfg.vh} exceeds the terminal "
            f"{term.width}x{term.height}; terminals wrap/scroll past their "
            f"bounds, which voids the byte and timing measurement. Resize the "
            f"terminal or reduce --viewport.\n"
        )
        return 2
    result = measure(term, cfg)
    emit_csv(result, args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
