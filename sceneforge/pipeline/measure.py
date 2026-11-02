from __future__ import annotations

import io

import numpy as np
from PIL import Image

SIZE = 256
OUTLINE = 128
RING = 6
RENDERER_GAP = 5
RENDER_CUT = 8
EDGE_CUT = 16
CLOSE = 3
SHIFTS = (0.75, 1.25)
STABLE = 0.85
FLAT = 1.3
OVERLAY = {"both": (128, 128, 128), "photo": (224, 64, 64), "model": (64, 96, 224), "none": (255, 255, 255)}


def measure(photo: bytes, grid: bytes, views: list[tuple[str, int, bool]], count: int,
            gap: int | None) -> tuple[str, bytes] | None:
    reference = photo_mask(photo)
    if reference is None:
        return None
    mask, rgb = reference
    tiles = split_grid(grid, count, RENDERER_GAP if gap is None else gap)
    measured = []
    level = []
    for name, index, eye_level in views:
        tile = np.asarray(Image.fromarray(tiles[index]).resize((SIZE, SIZE), Image.BILINEAR)).astype(np.int32)
        view = (255 - tile).max(-1) > RENDER_CUT
        if view.sum() >= 16:
            measured.append((name, tile, view, overlap(mask, view)))
            if eye_level:
                level.append(aspect(view))
    if not measured:
        return None
    name, tile, view, _ = max(measured, key=lambda item: item[3])
    lines = [
        f"- width / height of the object: photo {aspect(mask):.2f}; "
        + ", ".join(f"{name} {aspect(view):.2f}" for name, _, view, _ in measured),
        "- outline overlap with the photo (1.00 = the same outline): "
        + ", ".join(f"{name} {iou:.2f}" for name, _, _, iou in measured),
        f"- average object color: photo {mean_color(rgb, mask)}; {name} {mean_color(tile, view)}",
        f"- the overlay compares the photo with {name}",
    ]
    if level and (flatter := sum(level) / len(level) / aspect(mask)) >= FLAT:
        lines.append(f"- the eye-level views are {flatter:.1f} times flatter than the photo: if the photo looks down "
                     "on the object, tilt the whole object toward the camera about X until they show it as the photo does")
    return "\n".join(lines), overlay_png(outline(mask), outline(view))


def photo_mask(png: bytes) -> tuple[np.ndarray, np.ndarray] | None:
    rgb = np.asarray(Image.open(io.BytesIO(png)).convert("RGB").resize((SIZE, SIZE), Image.BILINEAR)).astype(np.int32)
    mask = _segment(rgb, 1.0)
    if mask is None:
        return None
    for shift in SHIFTS:
        shifted = _segment(rgb, shift)
        if shifted is None or overlap(mask, shifted) < STABLE:
            return None
    return mask, rgb


def _segment(rgb: np.ndarray, strictness: float) -> np.ndarray | None:
    sides = np.concatenate([rgb[:, :RING], rgb[:, -RING:]], axis=1)
    background = np.median(sides, axis=1).astype(np.int32)[:, None, :]
    distance = np.abs(rgb - background).max(-1)
    border = _border((SIZE, SIZE))
    cut = int(strictness * max(20, int(3 * np.median(distance[border])) + 8))
    light, light_background = rgb.sum(-1), background.sum(-1)
    tint = np.abs((3 * rgb - light[..., None]) - (3 * background - light_background[..., None])).max(-1)
    shadow = (100 * light < 97 * light_background) & (100 * light > 45 * light_background) & (tint < 36)
    edges = np.zeros((SIZE, SIZE), np.int32)
    edges[1:-1, 1:-1] = (np.abs(rgb[2:, 1:-1] - rgb[:-2, 1:-1]) + np.abs(rgb[1:-1, 2:] - rgb[1:-1, :-2])).max(-1)
    inner = border & ~_border_of((SIZE, SIZE), 1)
    edge_cut = int(strictness * max(EDGE_CUT, int(4 * np.median(edges[inner])) + 12))
    mask = ((distance > cut) & ~(shadow & (distance < 4 * cut))) | (edges > edge_cut)
    mask = _erode(_fill_holes(_dilate(_erode(mask, 1), 1 + CLOSE)), CLOSE)
    if mask.sum() < 64 or mask[border].mean() > 0.5:
        return None
    return mask


def split_grid(png: bytes, count: int, gap: int) -> list[np.ndarray]:
    image = np.asarray(Image.open(io.BytesIO(png)).convert("RGB"))
    columns = int(np.ceil(np.sqrt(count)))
    size = (image.shape[1] - (columns - 1) * gap) // columns
    tiles = []
    for index in range(count):
        row, column = divmod(index, columns)
        top, left = row * (size + gap), column * (size + gap)
        tiles.append(image[top:top + size, left:left + size])
    return tiles


def outline(mask: np.ndarray) -> np.ndarray:
    ys, xs = np.nonzero(mask)
    crop = mask[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
    height, width = crop.shape
    scale = OUTLINE / max(height, width)
    height, width = max(1, round(height * scale)), max(1, round(width * scale))
    small = np.asarray(Image.fromarray(crop.astype(np.uint8) * 255).resize((width, height), Image.BILINEAR)) >= 128
    canvas = np.zeros((OUTLINE, OUTLINE), bool)
    top, left = (OUTLINE - height) // 2, (OUTLINE - width) // 2
    canvas[top:top + height, left:left + width] = small
    return canvas


def overlap(first: np.ndarray, second: np.ndarray) -> float:
    one, two = outline(first), outline(second)
    return int((one & two).sum()) / max(1, int((one | two).sum()))


def aspect(mask: np.ndarray) -> float:
    ys, xs = np.nonzero(mask)
    return (int(xs.max()) - int(xs.min()) + 1) / (int(ys.max()) - int(ys.min()) + 1)


def mean_color(rgb: np.ndarray, mask: np.ndarray) -> str:
    inner = _erode(mask, 2)
    pixels = rgb[inner if inner.sum() >= 16 else mask].astype(np.int64)
    return "#" + "".join(f"{int(value):02x}" for value in pixels.sum(0) // len(pixels))


def overlay_png(photo: np.ndarray, model: np.ndarray) -> bytes:
    image = np.empty((OUTLINE, OUTLINE, 3), np.uint8)
    image[:] = OVERLAY["none"]
    image[photo & model] = OVERLAY["both"]
    image[photo & ~model] = OVERLAY["photo"]
    image[~photo & model] = OVERLAY["model"]
    buffer = io.BytesIO()
    Image.fromarray(image).resize((SIZE, SIZE), Image.NEAREST).save(buffer, format="PNG")
    return buffer.getvalue()


def _border(shape: tuple[int, int]) -> np.ndarray:
    return _border_of(shape, RING)


def _border_of(shape: tuple[int, int], width: int) -> np.ndarray:
    border = np.zeros(shape, bool)
    border[:width], border[-width:], border[:, :width], border[:, -width:] = True, True, True, True
    return border


def _grow(mask: np.ndarray) -> np.ndarray:
    grown = mask.copy()
    grown[1:] |= mask[:-1]
    grown[:-1] |= mask[1:]
    grown[:, 1:] |= mask[:, :-1]
    grown[:, :-1] |= mask[:, 1:]
    return grown


def _dilate(mask: np.ndarray, steps: int) -> np.ndarray:
    for _ in range(steps):
        mask = _grow(mask)
    return mask


def _erode(mask: np.ndarray, steps: int) -> np.ndarray:
    for _ in range(steps):
        mask = ~_grow(~mask)
    return mask


def _fill_holes(mask: np.ndarray) -> np.ndarray:
    outside = _border(mask.shape) & ~mask
    while True:
        grown = _grow(outside) & ~mask
        if (grown == outside).all():
            return ~outside
        outside = grown
