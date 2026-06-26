"""terminal_vs.loop - fixed-timestep game loop (Phase 2).

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

Level-up draft (master section 8, the leveling contract): ``step`` SETS
``state.level_up_pending`` when xp crosses a threshold and never clears it. On
entering ``levelup`` mode the loop rolls ``cfg.defs.leveling.draft_choices`` draft
cards into ``state.pending_choices`` and the overlay shows them. A number key
``1..N`` selects a card; :func:`apply_draft_selection` applies it, advances the
level (carrying the xp overflow), reconciles the per-weapon cooldowns (an
evolution swaps weapons), then re-checks ``level_up_pending``: a single large xp
grant can bank several levels, so the helper re-rolls the next draft and the loop
stays in ``levelup`` until pending clears, then returns to ``play``.
"""

from __future__ import annotations

import random
from dataclasses import replace
from time import monotonic

from .config import Config
from .meta.accrue import RunResult, accrue_meta, spend_gold
from .meta.save import DEFAULT_SAVE_PATH, load_meta, save_meta
from .render.frame import render_frame
from .rules import leveling
from .sim.state import Intent, new_run, reconcile_weapon_cooldowns
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
# Key that toggles pause in play mode.
_PAUSE_KEY = "p"
# Key that restarts the run from the game-over screen.
_RESTART_KEY = "r"


def _intent_from_key(key) -> Intent | None:
    """Map a polled blessed key to a movement Intent, or None if not a move key.

    Arrow keys map to 8-direction-capable Intents. A key that is not an arrow
    returns None so the caller can keep the last intent.
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


def _selection_index_from_key(key, n: int) -> int | None:
    """Map a number key '1'..'N' to a 0-based choice index, or None.

    ``n`` is how many cards are on offer; a digit outside ``1..n`` (or a non-digit
    key) returns None so the loop ignores it and keeps waiting for a valid pick.
    """
    if key is None:
        return None
    text = str(key)
    if len(text) == 1 and text.isdigit():
        value = int(text)
        if 1 <= value <= n:
            return value - 1
    return None


def _roll_pending(state, cfg: Config, rng: random.Random) -> None:
    """Roll a fresh draft into ``state.pending_choices`` for the current build.

    The draft size is the balance ``draft_choices``. Called when entering
    ``levelup`` and after each consumed level that leaves more banked (so the next
    level's draft reflects the just-applied build).
    """
    state.pending_choices = leveling.roll_choices(
        state.build, cfg.defs, rng, cfg.defs.leveling.draft_choices
    )


def apply_draft_selection(
    state, index: int, cfg: Config, rng: random.Random
) -> None:
    """Apply the chosen draft card, advance one level, and continue or finish.

    Consumes exactly one banked level (master section 8): apply the selected
    ``state.pending_choices[index]`` to the build (``apply_choice`` does NOT touch
    level/xp), then advance the level by one and subtract the cleared level's
    threshold from xp (clamped at 0). Reconcile the per-weapon cooldowns so an
    evolution's weapon swap is reflected (the base weapon's cooldown is dropped,
    the result weapon gets a fresh 0.0). Then re-check ``level_up_pending``: if
    more levels are banked, re-roll the next draft and stay in ``levelup``;
    otherwise clear the pending flag and ``pending_choices`` so the loop returns
    to ``play``. The interactive loop and the headless drain both call this, so
    the level/xp/cooldown bookkeeping has a single home.
    """
    if not state.pending_choices or not (0 <= index < len(state.pending_choices)):
        return
    choice = state.pending_choices[index]
    threshold = leveling.xp_for_level(state.build.level, cfg.defs)
    new_build = leveling.apply_choice(state.build, choice)
    state.build = replace(
        new_build,
        level=new_build.level + 1,
        xp=max(0.0, new_build.xp - threshold),
    )
    reconcile_weapon_cooldowns(state)
    if leveling.level_up_pending(state.build, cfg.defs):
        _roll_pending(state, cfg, rng)
    else:
        state.level_up_pending = False
        state.pending_choices = ()


def _drain_levelups(state, cfg: Config, rng: random.Random) -> None:
    """Consume every banked level-up by auto-picking the first card each time.

    The headless drain seam (used by tests and the integration mirror): when a
    level-up is pending it rolls the draft (if not already rolled) and applies
    index 0 via :func:`apply_draft_selection`, repeating until pending clears.
    Deterministic for a fixed rng. The interactive loop instead waits for a
    number key, but routes the actual application through the same helper.
    """
    while leveling.level_up_pending(state.build, cfg.defs):
        if not state.pending_choices:
            _roll_pending(state, cfg, rng)
        apply_draft_selection(state, 0, cfg, rng)
    state.level_up_pending = False
    state.pending_choices = ()


def _try_buy_upgrade(meta, key: str, cfg: Config):
    """Map a game-over shop digit to a spend_gold purchase.

    Returns the new ``MetaState`` if ``key`` is a digit naming an upgrade in the
    sorted shop order (1-based), else ``None``. ``spend_gold`` itself no-ops when
    the upgrade is maxed or unaffordable, so the returned meta may equal the input
    -- the caller re-saves / repaints either way, which is harmless.
    """
    if not key.isdigit():
        return None
    idx = int(key) - 1
    upgrade_ids = sorted(cfg.defs.upgrades)
    if not 0 <= idx < len(upgrade_ids):
        return None
    return spend_gold(meta, upgrade_ids[idx], cfg.defs)


def run(
    term, cfg: Config, rng: random.Random, sim=None, save_path=DEFAULT_SAVE_PATH
) -> None:
    """Run the fixed-timestep game loop until a quit key or the player dies.

    The simulation advances in fixed ``sim_dt`` sub-steps consumed from a time
    accumulator (master appendix A); rendering happens once per frame. ``term`` is
    only polled/drawn here and never handed to the sim or rules layers.

    ``sim`` is a test seam: production calls pass nothing and a fresh ``new_run``
    is created; tests may inject a primed ``SimState`` (e.g. with a pending
    level-up) to exercise a specific mode transition deterministically.
    """
    # Load cross-run meta and inject it into a fresh run. A primed test sim carries
    # its own authoritative meta, so reuse that and skip the disk load entirely --
    # this avoids needless IO and a MetaSaveError from a save the injected run
    # would ignore anyway.
    if sim is None:
        meta = load_meta(save_path)
        sim = new_run(cfg, rng, meta)
    else:
        meta = sim.meta
    # Capture the player's full hp as the HUD's HP-bar denominator BEFORE any
    # step mutates it -- there is no max_hp field in the contract, so this avoids
    # both a hardcoded 100 and importing a private start constant.
    max_hp = sim.player.hp

    sim_dt = 1.0 / cfg.sim_tps  # fixed timestep; timing comes from cfg only.
    accumulator = 0.0
    last = monotonic()
    mode = _MODE_PLAY
    # Last movement intent: the player keeps moving in the last direction when a
    # poll returns no new move key.
    intent = Intent(0, 0)
    # Paint the starting frame once so the player sees the initial state before
    # the first simulation step.
    render_frame(term, sim, sim.camera, cfg, max_hp, mode)

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
                render_frame(term, sim, sim.camera, cfg, max_hp, mode)
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
                # Bank this run's gold once on the play->gameover transition and
                # persist it (gold = kills * balance gold_per_kill). This branch
                # runs only on the transition, so the save happens exactly once.
                run_gold = sim.kills * cfg.defs.gold_per_kill
                meta = accrue_meta(meta, RunResult(gold_earned=run_gold))
                save_meta(meta, save_path)
                # Mirror the banked meta onto the (now finished) sim so the
                # game-over overlay's gold + shop reflect this run's earnings.
                sim.meta = meta
            elif sim.level_up_pending:
                mode = _MODE_LEVELUP
                # Roll the draft once on entering levelup so the overlay has cards
                # to show and the number keys have a stable index to select.
                _roll_pending(sim, cfg, rng)

            # Repaint only when the sim actually advanced or the mode just
            # changed. The input poll runs far faster than sim_tps, so emitting
            # the full frame on every idle poll wastes IO and (observed) starves
            # the sim. A diff renderer is deferred to Phase 3.
            if steps > 0 or mode != _MODE_PLAY:
                render_frame(term, sim, sim.camera, cfg, max_hp, mode)

        elif mode == _MODE_LEVELUP:
            # The frame was painted once when this mode was entered (the play
            # branch renders on the play->levelup transition). The sim is PAUSED,
            # so nothing changes until a number key selects a card. A valid
            # selection applies the card + advances the level via
            # apply_draft_selection; if levels are still banked the helper re-rolls
            # and we stay in levelup, otherwise it clears pending and we return to
            # play with the clock reset so the paused wall-time does not become a
            # catch-up backlog.
            index = _selection_index_from_key(key, len(sim.pending_choices))
            if index is not None:
                apply_draft_selection(sim, index, cfg, rng)
                if sim.level_up_pending:
                    # More levels banked: a fresh draft is showing.
                    render_frame(term, sim, sim.camera, cfg, max_hp, mode)
                else:
                    mode = _MODE_PLAY
                    last = monotonic()
                    accumulator = 0.0
                    render_frame(term, sim, sim.camera, cfg, max_hp, mode)

        elif mode == _MODE_PAUSE:
            # Painted once on entry (the play branch renders before pausing);
            # static while paused, so no per-poll repaint.
            if str(key) == _PAUSE_KEY:
                mode = _MODE_PLAY
                last = monotonic()
                accumulator = 0.0
                # Repaint immediately on resume so the "PAUSED" panel clears at
                # once. Otherwise the just-reset accumulator yields zero steps on
                # the next play iteration, the play branch's "render only if a step
                # ran or the mode changed" guard skips the repaint, and the stale
                # PAUSED overlay lingers until the sim advances (a visible glitch).
                render_frame(term, sim, sim.camera, cfg, max_hp, mode)

        elif mode == _MODE_GAMEOVER:
            # The frozen game-over frame stays until restart or quit (quit is
            # handled at the top of the loop). The restart key starts a fresh run
            # and returns to play: it re-captures the new run's full hp as the
            # HP-bar denominator and resets the input + clock so the time spent on
            # the game-over screen is not charged as a catch-up backlog.
            if str(key) == _RESTART_KEY:
                # Restart from the accrued meta (gold/upgrades banked at game over),
                # so a permanent upgrade bought on the game-over screen takes effect.
                sim = new_run(cfg, rng, meta)
                max_hp = sim.player.hp
                intent = Intent(0, 0)
                mode = _MODE_PLAY
                last = monotonic()
                accumulator = 0.0
                render_frame(term, sim, sim.camera, cfg, max_hp, mode)
            else:
                # A shop digit buys a permanent upgrade with the banked gold;
                # persist and repaint in place so the gold/shop lines update.
                # Non-digit / out-of-range keys return None and are ignored.
                bought = _try_buy_upgrade(meta, str(key), cfg)
                if bought is not None:
                    meta = bought
                    save_meta(meta, save_path)
                    sim.meta = meta
                    render_frame(term, sim, sim.camera, cfg, max_hp, mode)
