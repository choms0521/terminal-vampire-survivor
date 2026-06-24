"""terminal_vs.loop - fixed-timestep game loop (Day 5).

Implements the master plan appendix-A loop: a fixed-timestep simulation driven by
a time accumulator, with a small mode machine (``play`` / ``levelup`` / ``pause``
/ ``gameover``). This module sits on the blessed boundary -- it polls input and
calls ``render_frame`` -- but it NEVER passes ``term`` into the sim or rules
layers; it only hands them plain values (Intent, Config, rng).

Timing contract (master section 3.6, no hardcoded performance numbers): every
timing constant is read from ``cfg`` only. ``sim_dt`` is ``1.0 / cfg.sim_tps``,
the input poll uses ``cfg.poll_timeout``, and the catch-up drain is capped at
``cfg.max_catchup`` sub-steps per frame. No numeric literal stands in for any of
these.

Level-up drain (master section 8, the leveling contract): ``step`` SETS
``state.level_up_pending`` when xp crosses a threshold and never clears it. On a
confirm key in ``levelup`` mode the loop consumes the level-up by rolling a
choice and applying it (rebinding ``state.level_state``), then RE-CHECKS
``leveling.level_up_pending`` -- a single large xp grant can bank several levels,
so the loop keeps applying one choice per banked level until pending is false,
then clears ``state.level_up_pending`` and returns to ``play``.
"""

from __future__ import annotations

import random
from time import monotonic

from .config import Config
from .render.frame import render_frame
from .rules import leveling
from .sim.state import Intent, new_run
from .sim.step import step

# Mode names for the loop state machine.
_MODE_PLAY = "play"
_MODE_LEVELUP = "levelup"
_MODE_PAUSE = "pause"
_MODE_GAMEOVER = "gameover"

# Arrow-key names returned by blessed term.inkey() (.name attribute).
_KEY_TO_INTENT = {
    "KEY_UP": (0, -1),
    "KEY_DOWN": (0, 1),
    "KEY_LEFT": (-1, 0),
    "KEY_RIGHT": (1, 0),
}
# Keys that quit the loop (a bare 'q' or the ESC key).
_QUIT_KEYS = ("q", "Q")
# Keys that confirm a level-up choice / unpause.
_CONFIRM_KEYS = (" ", "\n", "\r")
# Key that toggles pause in play mode.
_PAUSE_KEY = "p"


def _intent_from_key(key) -> Intent | None:
    """Map a polled blessed key to a movement Intent, or None if not a move key.

    Arrow keys map to 8-direction-capable Intents (Phase 1 uses 4 of the 8). A
    key that is not an arrow returns None so the caller can keep the last intent.
    """
    if key is None:
        return None
    name = getattr(key, "name", None)
    if name in _KEY_TO_INTENT:
        dx, dy = _KEY_TO_INTENT[name]
        return Intent(dx, dy)
    return None


def _is_quit(key) -> bool:
    """True if the key quits the loop: a 'q'/'Q' or the ESC key."""
    if key is None:
        return False
    if getattr(key, "name", None) == "KEY_ESCAPE":
        return True
    return str(key) in _QUIT_KEYS


def _is_confirm(key) -> bool:
    """True if the key confirms a level-up choice or unpauses."""
    if key is None:
        return False
    name = getattr(key, "name", None)
    if name in ("KEY_ENTER",):
        return True
    return str(key) in _CONFIRM_KEYS


def _drain_levelups(state, cfg: Config, rng: random.Random) -> None:
    """Consume every banked level-up, then clear the pending flag.

    Per the leveling contract, ``step`` only SETS ``level_up_pending``; the loop
    clears it. One ``apply_choice`` consumes exactly one level, so a single big xp
    grant that banked several levels needs several applications. Loop while
    ``leveling.level_up_pending`` is true on the rebound ``level_state``, applying
    one rolled choice per iteration, then set the flag false. ``roll_choices``
    does not consume rng in Phase 1, so the drain does not perturb determinism.
    """
    while leveling.level_up_pending(state.level_state, cfg):
        choice = leveling.roll_choices(state.level_state, cfg, rng, n=1)[0]
        state.level_state = leveling.apply_choice(state.level_state, choice, cfg)
    state.level_up_pending = False


def run(term, cfg: Config, rng: random.Random, sim=None) -> None:
    """Run the fixed-timestep game loop until a quit key or the player dies.

    The simulation advances in fixed ``sim_dt`` sub-steps consumed from a time
    accumulator (master appendix A); rendering happens once per frame. ``term`` is
    only polled/drawn here and never handed to the sim or rules layers.

    ``sim`` is a test seam: production calls pass nothing and a fresh ``new_run``
    is created; tests may inject a primed ``SimState`` (e.g. with a pending
    level-up) to exercise a specific mode transition deterministically.
    """
    if sim is None:
        sim = new_run(cfg, rng)
    # Capture the player's full hp as the HUD's HP-bar denominator BEFORE any
    # step mutates it -- there is no max_hp field in the contract, so this avoids
    # both a hardcoded 100 and importing a private start constant.
    max_hp = sim.player.hp

    sim_dt = 1.0 / cfg.sim_tps  # fixed timestep; timing comes from cfg only.
    accumulator = 0.0
    last = monotonic()
    mode = _MODE_PLAY
    # Last movement intent: spec section 3.3 uses the last polled key's intent
    # vector, so an empty poll keeps the player moving in the last direction.
    intent = Intent(0, 0)
    # Paint the starting frame once so the player sees the initial state before
    # the first simulation step.
    render_frame(term, sim, sim.camera, cfg, max_hp)

    while True:
        key = term.inkey(timeout=cfg.poll_timeout)
        if _is_quit(key):
            break

        if mode == _MODE_PLAY:
            new_intent = _intent_from_key(key)
            if new_intent is not None:
                intent = new_intent
            elif str(key) == _PAUSE_KEY:
                mode = _MODE_PAUSE
                render_frame(term, sim, sim.camera, cfg, max_hp)
                continue

            now = monotonic()
            accumulator += now - last
            last = now

            steps = 0
            while accumulator >= sim_dt and steps < cfg.max_catchup:
                step(sim, intent, cfg, rng)
                accumulator -= sim_dt
                steps += 1
            # If the catch-up cap was hit, drop the leftover backlog so a slow
            # frame cannot spiral the accumulator (master appendix A guard).
            if steps >= cfg.max_catchup:
                accumulator = 0.0

            if sim.player.hp <= 0.0:
                mode = _MODE_GAMEOVER
            elif sim.level_up_pending:
                mode = _MODE_LEVELUP

            # Repaint only when the sim actually advanced or the mode just
            # changed. The input poll runs far faster than sim_tps, so emitting
            # the full frame on every idle poll wastes IO and (observed) starves
            # the sim, making it run slower than wall-clock. Phase 1 keeps the
            # simple full-frame emit; a diff renderer is deferred to Phase 2.
            if steps > 0 or mode != _MODE_PLAY:
                render_frame(term, sim, sim.camera, cfg, max_hp)

        elif mode == _MODE_LEVELUP:
            # Simulation is PAUSED while the overlay is up. A confirm key consumes
            # all banked level-ups (drain), then returns to play with the clock
            # reset so the paused wall-time does not become a catch-up backlog.
            render_frame(term, sim, sim.camera, cfg, max_hp)
            if _is_confirm(key):
                _drain_levelups(sim, cfg, rng)
                mode = _MODE_PLAY
                last = monotonic()
                accumulator = 0.0

        elif mode == _MODE_PAUSE:
            render_frame(term, sim, sim.camera, cfg, max_hp)
            if str(key) == _PAUSE_KEY or _is_confirm(key):
                mode = _MODE_PLAY
                last = monotonic()
                accumulator = 0.0

        elif mode == _MODE_GAMEOVER:
            render_frame(term, sim, sim.camera, cfg, max_hp)
            # Stay on the game-over frame until a quit key is pressed (handled at
            # the top of the loop); no further simulation runs.
