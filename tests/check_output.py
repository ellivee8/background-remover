"""Verify the result of running the remover on tests/make_sample.py images.
Usage: python check_output.py <folder-with-samples>   (results expected in <folder>/output)"""

import sys
from pathlib import Path

import cv2
import numpy as np


def load(p: Path):
    img = cv2.imdecode(np.fromfile(str(p), np.uint8), cv2.IMREAD_UNCHANGED)
    assert img is not None, f"cannot read {p}"
    return img


def main():
    folder = Path(sys.argv[1] if len(sys.argv) > 1 else ".")
    out = folder / "output"
    samples = sorted(folder.glob("*.jpg"))
    assert samples, "no sample images found"
    for s in samples:
        combined = out / (s.stem + ".png")
        assert combined.exists(), f"missing {combined}"
        a = load(combined)
        assert a.shape == (2048, 1536, 4), f"unexpected shape {a.shape}"
        alpha = a[..., 3]
        checks = {
            "leaf 1 kept": (alpha[650, 900] > 200),
            "leaf 2 kept": (alpha[1300, 560] > 200),
            "board removed": (alpha[300, 250] == 0),
            "ground removed": (alpha[50, 50] == 0),
            "rim removed": (alpha[1000, 127] == 0),
            "hanging hole removed": (alpha[1800, 760] == 0 and alpha[1800, 700] == 0),
            "hole in leaf see-through": (alpha[650 - 75, 900 + 100] == 0),
        }
        parts = sorted(out.glob(s.stem + "_[0-9]*.png"))
        checks["2 separate objects"] = len(parts) == 2
        failed = [k for k, ok in checks.items() if not ok]
        print(f"{s.name}: " + ("OK" if not failed else "FAILED: " + ", ".join(failed)))
        if failed:
            sys.exit(1)
    print("All checks passed.")


if __name__ == "__main__":
    main()
