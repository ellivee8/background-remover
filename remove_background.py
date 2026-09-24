#!/usr/bin/env python3
"""
Remove the background from photos of objects (e.g. leaves) lying on a
light / white board, keeping only the objects on the board.

Usage:
    python remove_background.py                      # processes images in this folder
    python remove_background.py <folder-or-files...> # processes given folders / files
    python remove_background.py -o out_dir --white   # white background instead of transparent

Output (in ./output by default), PNGs with a transparent background:
    <name>.png            all objects together, original image size
    <name>_1.png, _2.png  every object on its own, cropped (numbered top-to-bottom, left-to-right)
"""

import argparse
import sys
from pathlib import Path

import cv2
import numpy as np

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff", ".webp"}


def read_image(path: Path):
    # cv2.imread cannot handle non-ASCII paths on Windows -> use imdecode
    data = np.fromfile(str(path), dtype=np.uint8)
    if data.size == 0:
        return None
    return cv2.imdecode(data, cv2.IMREAD_COLOR)


def write_image(path: Path, img) -> None:
    ok, buf = cv2.imencode(path.suffix, img)
    if not ok:
        raise RuntimeError(f"Could not encode {path}")
    buf.tofile(str(path))


def fill_holes(mask, max_hole_area=None):
    """Fill holes in a binary mask. If max_hole_area is given only small holes are filled."""
    inv = cv2.bitwise_not(mask)
    n, labels, stats, _ = cv2.connectedComponentsWithStats(inv, connectivity=4)
    h, w = mask.shape
    out = mask.copy()
    for i in range(1, n):
        x, y, bw, bh, area = stats[i]
        touches_border = x == 0 or y == 0 or x + bw == w or y + bh == h
        if touches_border:
            continue
        if max_hole_area is None or area <= max_hole_area:
            out[labels == i] = 255
    return out


def find_board(board_like):
    """Return a filled mask of the largest bright, neutral region (the board)."""
    white = cv2.morphologyEx(board_like, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))
    contours, _ = cv2.findContours(white, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None
    biggest = max(cv2.contourArea(c) for c in contours)
    # the board can be split into several pieces by objects lying across it -> use all big pieces
    pieces = [c for c in contours if cv2.contourArea(c) > biggest * 0.01]
    # convex hull: objects touching / overlapping the board edge would otherwise cut notches into it
    hull = cv2.convexHull(np.vstack(pieces))
    board = np.zeros_like(white)
    cv2.drawContours(board, [hull], -1, 255, thickness=cv2.FILLED)
    return board


def hanging_hole_mask(A, B, ref_a, ref_b, board, k, args):
    """Find the board's hanging hole: a ring in the rim's saturated green.

    A ring is hollow, so its convex hull is much larger than the ring itself; this
    also works when the ring is cut off by the photo edge, and doesn't catch
    (solid) green leaves.
    """
    rim_green = ((A < ref_a - args.rim_green) & (B > ref_b + 20)).astype(np.uint8) * 255
    rim_green &= cv2.dilate(board, np.ones((k(40), k(40)), np.uint8))  # only on the board
    rim_green = cv2.morphologyEx(rim_green, cv2.MORPH_CLOSE, np.ones((k(7), k(7)), np.uint8))
    hole = np.zeros_like(rim_green)
    board_area = np.count_nonzero(board)
    min_area = board_area * 0.0005
    max_hull = board_area * 0.05  # the hole is small; big rings are the board's own rim
    n, labels, stats, _ = cv2.connectedComponentsWithStats(rim_green, connectivity=8)
    for i in range(1, n):
        ring_area = stats[i, cv2.CC_STAT_AREA]  # pixels of the ring itself, not what it encloses
        if ring_area < min_area:
            continue
        pts = cv2.findNonZero((labels == i).astype(np.uint8))
        hull = cv2.convexHull(pts)
        hull_area = cv2.contourArea(hull)
        if 1.8 * ring_area < hull_area < max_hull:
            cv2.drawContours(hole, [hull], -1, 255, thickness=cv2.FILLED)
    hole = cv2.dilate(hole, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k(8) * 2 + 1,) * 2))
    return hole > 0


def remove_background(img, args):
    h, w = img.shape[:2]
    scale = max(h, w) / 2000.0  # keep pixel-based parameters resolution independent
    k = lambda px: max(1, int(round(px * scale)))

    blur = cv2.GaussianBlur(img, (0, 0), 1.2)
    lab = cv2.cvtColor(blur, cv2.COLOR_BGR2LAB).astype(np.int16)
    L, A, B = lab[..., 0], lab[..., 1], lab[..., 2]

    # Board colour reference = median of the bright, fairly neutral pixels
    neutral = (L > 150) & (np.abs(A - 128) < 12) & (np.abs(B - 128) < 18)
    if np.count_nonzero(neutral) > 1000:
        ref_a = int(np.median(A[neutral]))
        ref_b = int(np.median(B[neutral]))
    else:
        ref_a = ref_b = 128

    # local board brightness (handles uneven light / shadows)
    # (normalised blur over bright neutral pixels = interpolated board brightness)
    wmask = ((L > 150) & (np.abs(A - ref_a) < 8) & (np.abs(B - ref_b) < 10)).astype(np.float32)
    sig = k(60)
    num = cv2.GaussianBlur(L.astype(np.float32) * wmask, (0, 0), sig)
    den = cv2.GaussianBlur(wmask, (0, 0), sig)
    fallback = float(np.median(L[wmask > 0])) if wmask.any() else 220.0
    L_ref = np.where(den > 1e-3, num / np.maximum(den, 1e-6), fallback)

    # "Object" pixels: noticeably more coloured than the board, or much darker.
    # Pixels almost as bright as the board need much stronger colour, because the
    # white board picks up a green/yellow tint from light reflected by the leaves.
    chroma = np.sqrt((A - ref_a) ** 2 + np.maximum(B - ref_b, 0) ** 2)
    brightness = np.clip((L - (L_ref - 60)) / 60.0, 0, 1)
    colored = chroma > (args.color + brightness * args.bright_color)
    dark = L < L_ref - args.dark
    obj = colored | dark

    # 1. Locate the board, shrink it a bit to drop its coloured rim / edge shadow
    board_like = ((~obj) & (L > args.board_light)).astype(np.uint8) * 255
    board = find_board(board_like)
    if board is None:
        board = np.full((h, w), 255, np.uint8)
    board = cv2.erode(board, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k(args.rim) * 2 + 1,) * 2))

    # 2. Foreground = object pixels on the board, minus the board's hanging hole
    fg = (obj.astype(np.uint8) * 255) & board
    fg[hanging_hole_mask(A, B, ref_a, ref_b, board, k, args)] = 0
    fg = cv2.morphologyEx(fg, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    fg = cv2.morphologyEx(fg, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5)))

    # 3. Keep only meaningful objects; drop specks
    n, labels, stats, _ = cv2.connectedComponentsWithStats(fg, connectivity=8)
    board_area = max(1, int(np.count_nonzero(board)))
    keep = np.zeros_like(fg)
    for i in range(1, n):
        area = stats[i, cv2.CC_STAT_AREA]
        if area < board_area * args.min_area:
            continue
        comp = (labels == i).astype(np.uint8) * 255
        keep |= comp

    # Fill holes inside objects (pale spots, glare) - unless the hole shows the board
    # (a real hole in the leaf: bright and neutral like the board)
    keep = fill_holes(keep, max_hole_area=int(board_area * args.max_fill_hole))
    inv = cv2.bitwise_not(keep)
    n, labels, stats, _ = cv2.connectedComponentsWithStats(inv, connectivity=4)
    for i in range(1, n):
        x, y, bw, bh, area = stats[i]
        if x == 0 or y == 0 or x + bw == w or y + bh == h:
            continue
        sel = labels == i
        looks_like_board = (np.mean(L[sel] - L_ref[sel]) > -args.hole_dark
                            and np.mean(chroma[sel]) < args.color + args.bright_color)
        if not looks_like_board:
            keep[sel] = 255

    # 4. Split into separate objects (sorted top-to-bottom, then left-to-right)
    n, labels, stats, _ = cv2.connectedComponentsWithStats(keep, connectivity=8)
    objects = []
    for i in range(1, n):
        if stats[i, cv2.CC_STAT_AREA] < board_area * args.min_area:
            continue
        m = (labels == i).astype(np.uint8) * 255
        if args.feather > 0:
            m = cv2.GaussianBlur(m, (0, 0), args.feather)
        objects.append((stats[i, cv2.CC_STAT_TOP], stats[i, cv2.CC_STAT_LEFT], m))
    objects.sort(key=lambda o: (o[0] // k(150), o[1]))  # rows of ~150px, then left-to-right
    return [m for _, _, m in objects]


def compose(img, alpha, white_bg, crop, pad):
    if crop:
        ys, xs = np.where(alpha > 0)
        if len(xs):
            x0, x1 = max(0, xs.min() - pad), min(img.shape[1], xs.max() + pad + 1)
            y0, y1 = max(0, ys.min() - pad), min(img.shape[0], ys.max() + pad + 1)
            img, alpha = img[y0:y1, x0:x1], alpha[y0:y1, x0:x1]
    if white_bg:
        a = (alpha.astype(np.float32) / 255.0)[..., None]
        return (img * a + 255 * (1 - a)).astype(np.uint8)
    return np.dstack([img, alpha])


def collect_inputs(paths):
    files = []
    for p in paths:
        p = Path(p)
        if p.is_dir():
            files += sorted(f for f in p.iterdir() if f.suffix.lower() in IMAGE_EXTS)
        elif p.is_file() and p.suffix.lower() in IMAGE_EXTS:
            files.append(p)
        else:
            print(f"Skipping {p} (not an image or folder)")
    return files


def main():
    here = Path(__file__).resolve().parent
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("inputs", nargs="*", help="Image files or folders (default: folder of this script)")
    ap.add_argument("-o", "--output", help="Output folder (default: <input folder>/output)")
    ap.add_argument("--white", action="store_true", help="White background (JPG) instead of transparent PNG")
    ap.add_argument("--crop", action="store_true", help="Crop the combined image tightly around the objects")
    ap.add_argument("--no-separate", action="store_true", help="Don't save each object as its own image")
    ap.add_argument("--no-combined", action="store_true", help="Don't save the combined image with all objects")
    ap.add_argument("--pad", type=int, default=20, help="Padding in px around cropped / separate objects (default 20)")
    ap.add_argument("--mask", action="store_true", help="Also save the black/white mask")
    # tuning
    ap.add_argument("--color", type=int, default=18, help="Min colour difference from the board counted as object (default 18)")
    ap.add_argument("--bright-color", type=int, default=30, help="Extra colour needed for pixels as bright as the board (default 30)")
    ap.add_argument("--dark", type=int, default=60, help="How much darker than the board counts as object (default 60)")
    ap.add_argument("--board-light", type=int, default=130, help="Min lightness (0-255) of the board (default 130)")
    ap.add_argument("--rim", type=int, default=18, help="px shaved off the board edge (default 18)")
    ap.add_argument("--min-area", type=float, default=0.002, help="Min object size as fraction of board (default 0.002)")
    ap.add_argument("--rim-green", type=int, default=22, help="How much greener than the board the rim / hanging-hole ring is (default 22)")
    ap.add_argument("--max-fill-hole", type=float, default=0.00005, help="Holes smaller than this fraction of board get filled")
    ap.add_argument("--hole-dark", type=int, default=25, help="Holes in objects are kept only if at most this much darker than the board (default 25)")
    ap.add_argument("--feather", type=float, default=1.0, help="Edge softness in px (default 1.0, 0 = hard)")
    args = ap.parse_args()

    inputs = args.inputs or [str(here)]
    files = collect_inputs(inputs)
    files = [f for f in files if f.parent.name != "output"]
    if not files:
        print("No images found.")
        return 1

    print(f"Processing {len(files)} image(s)...")
    failed = 0
    for f in files:
        try:
            process_file(f, args)
        except Exception as e:  # keep going with the other images
            failed += 1
            print(f"  ! {f.name}: FAILED - {type(e).__name__}: {e}")
    if failed:
        print(f"Done, but {failed} of {len(files)} image(s) failed (see above).")
        return 2
    print("Done.")
    return 0


def process_file(f: Path, args) -> None:
    out_dir = Path(args.output) if args.output else f.parent / "output"
    out_dir.mkdir(parents=True, exist_ok=True)
    img = read_image(f)
    if img is None:
        raise ValueError("could not read the image (corrupt or unsupported file?)")
    objects = remove_background(img, args)
    ext = ".jpg" if args.white else ".png"
    if not objects:
        print(f"  {f.name}: no objects found")
        return
    alpha = np.maximum.reduce(objects)
    if not args.no_combined:
        write_image(out_dir / (f.stem + ext), compose(img, alpha, args.white, args.crop, args.pad))
    if args.mask:
        write_image(out_dir / (f.stem + "_mask.png"), alpha)
    if not args.no_separate:
        for idx, m in enumerate(objects, 1):
            write_image(out_dir / f"{f.stem}_{idx}{ext}", compose(img, m, args.white, True, args.pad))
    print(f"  {f.name}: {len(objects)} object(s) -> {out_dir}")


if __name__ == "__main__":
    sys.exit(main())
