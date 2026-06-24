"""terminal_vs.world - world<->cell coordinate mapping, aspect correction, camera.

Pure math, blessed-independent (master plan section 3.1). The simulation runs in
float world coordinates; quantization to integer render cells happens only here,
and the aspect-ratio correction (terminal cells are ~2:1 tall, so the X axis is
compressed by ``cfg.aspect_x``) is concentrated in this single module.

Because this layer is deterministic and free of side effects, it is unit-tested
headlessly in tests/test_world.py.
"""

from __future__ import annotations

from dataclasses import dataclass

from .config import Config


@dataclass(frozen=True)
class Rect:
    """Visible world-coordinate bounds (inclusive-min, exclusive-max convention).

    Fields are world coordinates (floats), not cells. spawn (off-screen ring
    math) and culling consume this. ``min_x <= wx < max_x`` and
    ``min_y <= wy < max_y`` describe the visible region around the camera.
    """

    min_x: float
    min_y: float
    max_x: float
    max_y: float


class Camera:
    """Player-following camera holding the world-space center of the viewport.

    Mutable by design: ``follow`` updates ``x``/``y`` in place. This is the
    sim/camera side of the ADR-001 (section 6) immutability carve-out, not the
    frozen rules/config side. ``follow`` reads ``player.x`` / ``player.y``
    duck-typed -- any entity exposing float ``.x`` / ``.y`` works.
    """

    def __init__(self, x: float = 0.0, y: float = 0.0) -> None:
        self.x: float = x
        self.y: float = y

    def follow(self, player) -> None:
        """Center the camera on the player (reads player.x / player.y)."""
        self.x = player.x
        self.y = player.y


def world_to_cell(wx: float, wy: float, cam: Camera, cfg: Config) -> tuple[int, int]:
    """Quantize a float world coordinate to an integer render cell (col, row).

    The aspect correction lives only here: the X delta from the camera is scaled
    by ``cfg.aspect_x`` (compressing X so circular ranges read as circles on a
    2:1 cell grid). The viewport is centered on the camera, so the camera world
    position maps to the viewport center cell.
    """
    rel_x = (wx - cam.x) * cfg.aspect_x
    rel_y = (wy - cam.y)
    col = cfg.viewport_w // 2 + int(round(rel_x))
    row = cfg.viewport_h // 2 + int(round(rel_y))
    return col, row


def cell_to_world(col: int, row: int, cam: Camera, cfg: Config) -> tuple[float, float]:
    """Inverse of :func:`world_to_cell` -- the cell center in world coordinates.

    Used for spawn-ring math (place enemies just outside the visible cells, then
    convert back to world space). Because ``world_to_cell`` uses ``round`` (which
    centers on the integer cell, not its corner), the inverse adds no half-cell
    offset: it simply divides the X delta back out by ``cfg.aspect_x``. As a
    result ``world_to_cell(cell_to_world(c, r)) == (c, r)`` holds exactly on
    integer cells.
    """
    rel_x = col - cfg.viewport_w // 2
    rel_y = row - cfg.viewport_h // 2
    wx = cam.x + rel_x / cfg.aspect_x
    wy = cam.y + rel_y
    return wx, wy


def visible_bounds(cam: Camera, cfg: Config) -> Rect:
    """World-coordinate bounds of the visible viewport, centered on the camera.

    Derived by inverting the half-extent of the viewport: the X half-extent is
    divided by ``cfg.aspect_x`` (X is compressed on screen, so it covers less
    world distance). Bounds are inclusive-min / exclusive-max in world space.
    """
    half_w_world = (cfg.viewport_w / 2.0) / cfg.aspect_x
    half_h_world = cfg.viewport_h / 2.0
    return Rect(
        min_x=cam.x - half_w_world,
        min_y=cam.y - half_h_world,
        max_x=cam.x + half_w_world,
        max_y=cam.y + half_h_world,
    )


def is_visible(wx: float, wy: float, cam: Camera, cfg: Config) -> bool:
    """True if the world coordinate quantizes to an in-bounds viewport cell."""
    col, row = world_to_cell(wx, wy, cam, cfg)
    return 0 <= col < cfg.viewport_w and 0 <= row < cfg.viewport_h


def sq_dist_aspect(ax: float, ay: float, bx: float, by: float, cfg: Config) -> float:
    """Aspect-corrected squared distance between two world points.

    Single source of truth for "distance as it appears on screen": the X delta
    is scaled by ``cfg.aspect_x`` with the SAME transform as
    :func:`world_to_cell`, so targeting distance and rendered distance agree
    (a circle of equal screen radius reads as a circle). Returns the squared
    distance to avoid a sqrt -- callers comparing distances do not need it.

    rules/weapons.py imports this for nearest-enemy target selection, so the
    aspect convention has exactly one definition.
    """
    dx = (ax - bx) * cfg.aspect_x
    dy = (ay - by)
    return dx * dx + dy * dy
