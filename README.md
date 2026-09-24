# Background remover

Removes the background from photos of objects (leaves, needles, bark, …) lying on a
white board. Only the objects are kept. The board, its green rim, the hanging hole and the
ground around it are all removed. Holes in a leaf that show the board become see-through.
Results are transparent PNGs in an `output` folder next to the photos:

- `<photo>.png` has all objects together, at the original image size.
- `<photo>_1.png`, `<photo>_2.png`, … have each object on its own, cropped.
  They are numbered top-to-bottom, then left-to-right.

Objects that touch or overlap each other are treated as one object.

## Windows

1. Download this repository (**Code → Download ZIP**) and **extract** the ZIP.
2. Copy your photos into the extracted folder, then **double-click `remove_background.bat`**.
   You can also **drag & drop** photos or folders onto `remove_background.bat`.

The first run sets everything up by itself (a minute or two, needs internet):
- If Python is missing, it offers to install it (via winget). Otherwise it opens the
  download page. There, pick the 64-bit installer and tick *"Add python.exe to PATH"*.
- The needed libraries (numpy, OpenCV) go into a private folder,
  `%LOCALAPPDATA%\BackgroundRemover`. Nothing else on the PC is changed.
- If that setup ever gets broken, or `requirements.txt` changes, it's rebuilt automatically.
  You can force a rebuild with `set BGR_REINSTALL=1` before running, or by deleting that folder.
- A setup log is written to `%LOCALAPPDATA%\BackgroundRemover\setup.log`.

If one photo can't be read, it's reported and the rest are still processed.

## Options (command line)

```
remove_background.bat C:\photos\leaves --crop          # crop the combined image tightly
remove_background.bat C:\photos\leaves --no-combined   # only the separate object images
remove_background.bat C:\photos\leaves --no-separate   # only the combined image
remove_background.bat C:\photos\leaves --white         # white background (JPG) instead of transparent
remove_background.bat C:\photos\leaves -o C:\results   # choose the output folder
remove_background.bat --help                           # all options, including tuning parameters
```

Tuning options, if a photo doesn't come out right:
- **Parts of the board are kept:** raise `--color` (default 18) or `--bright-color` (default 30).
- **Pale parts of the objects go missing:** lower `--color`.
- **Rim or ground is still visible at the edge:** raise `--rim` (default 18).
- **The board's hanging hole shows up in the result:** lower `--rim-green` (default 22).
- **Small loose bits (single needles) are dropped:** lower `--min-area` (default 0.002).

## Other systems / development

```
python -m pip install -r requirements.txt
python remove_background.py <photos-folder>
```

Tests (these also run on GitHub Actions, including a real run of the `.bat` on Windows):

```
python tests/make_sample.py samples
python remove_background.py samples
python tests/check_output.py samples
```

## Known limitations

- Anything reaching past the board's edge is cut off at the edge.
- Very small objects are ignored as dust (see `--min-area`).
- When dragging files onto the `.bat`, a file name that contains `&` but no space can't be
  passed through by Windows. Rename the file, or drop its folder instead.
