"""Create a synthetic test photo: two leaves on a white board with a green rim and a
hanging hole, lying on brown ground. Usage: python make_sample.py <output-folder>"""

import sys
from pathlib import Path

import cv2
import numpy as np


def leaf(img, center, size, angle, color, hole=False):
    cx, cy = center
    pts = []
    for t in np.linspace(0, 2 * np.pi, 400, endpoint=False):
        # lobed outline like a maple leaf
        r = size * (0.75 + 0.25 * np.cos(5 * t)) * (0.9 + 0.1 * np.sin(23 * t))
        pts.append((cx + r * np.cos(t + angle), cy + r * np.sin(t + angle)))
    cv2.fillPoly(img, [np.array(pts, np.int32)], color, cv2.LINE_AA)
    # stem + veins
    end = (int(cx - 1.6 * size * np.cos(angle)), int(cy - 1.6 * size * np.sin(angle)))
    cv2.line(img, (cx, cy), end, (95, 150, 140), 6, cv2.LINE_AA)
    for a in np.linspace(0, 2 * np.pi, 5, endpoint=False):
        p = (int(cx + 0.8 * size * np.cos(a + angle)), int(cy + 0.8 * size * np.sin(a + angle)))
        cv2.line(img, (cx, cy), p, (100, 165, 150), 2, cv2.LINE_AA)
    if hole:
        cv2.circle(img, (cx + size // 3, cy - size // 4), size // 12, (228, 230, 226), -1, cv2.LINE_AA)


def main():
    out = Path(sys.argv[1] if len(sys.argv) > 1 else ".")
    out.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(1)
    h, w = 2048, 1536

    # ground: brown noise + needle strokes
    img = np.zeros((h, w, 3), np.uint8)
    img[:] = (40, 70, 95)
    img = cv2.add(img, rng.integers(0, 40, (h, w, 3), dtype=np.uint8))
    for _ in range(1500):
        x, y = rng.integers(0, w), rng.integers(0, h)
        a = rng.uniform(0, np.pi)
        cv2.line(img, (x, y), (int(x + 80 * np.cos(a)), int(y + 80 * np.sin(a))), (60, 110, 150), 2)

    # board with green rim
    rim, board_col = (40, 175, 60), (228, 230, 226)
    x0, y0, x1, y1 = 120, 180, 1400, 1900
    cv2.rectangle(img, (x0, y0), (x1, y1), rim, -1)
    cv2.rectangle(img, (x0 + 15, y0 + 15), (x1 - 15, y1 - 15), board_col, -1)
    board = img[y0 + 15:y1 - 15, x0 + 15:x1 - 15]
    board[:] = cv2.add(board, rng.integers(0, 8, board.shape, dtype=np.uint8))

    # hanging hole: green ring with ground showing through
    cv2.circle(img, (760, 1800), 70, rim, -1, cv2.LINE_AA)
    cv2.circle(img, (760, 1800), 52, (45, 75, 100), -1, cv2.LINE_AA)

    # two leaves, one with a real hole
    leaf(img, (900, 650), 300, 0.4, (70, 140, 95), hole=True)
    leaf(img, (560, 1300), 280, 2.3, (60, 150, 80))

    img = cv2.GaussianBlur(img, (0, 0), 1.0)
    for name in ("sample leaves.jpg", "lehti_\u00e4\u00f6.jpg"):  # also a non-ASCII file name
        ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 90])
        buf.tofile(str(out / name))
    print(f"wrote sample images to {out}")


if __name__ == "__main__":
    main()
