"""Dev-only: render the Tabler icons the GUI uses into assets/icons/*.png.

The app loads these PNGs instead of importing pytablericons at runtime. That
package pulls in pygame + numpy (~35 MB) and ships ~5,000 SVG files, which a
PyInstaller --onefile build unpacks to a temp dir on every launch -- the main
cause of a ~20s startup. Icons are stored white-on-transparent; gui.py only uses
the alpha channel and tints it to whatever color it needs.

Run after adding or changing an icon:  python tools/render_icons.py
"""
from __future__ import annotations

import os

from pytablericons import OutlineIcon, TablerIcons

# file name (used by gui._icon_image) -> Tabler outline icon
ICONS = {
    "speakerphone": OutlineIcon.SPEAKERPHONE,
    "paperclip": OutlineIcon.PAPERCLIP,
    "mood_smile": OutlineIcon.MOOD_SMILE,
}

# 2x the 18px on-screen size, so icons stay crisp on HiDPI displays.
SIZE = 36

OUT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets", "icons")


def main() -> None:
    os.makedirs(OUT_DIR, exist_ok=True)
    for name, icon in ICONS.items():
        path = os.path.join(OUT_DIR, f"{name}.png")
        TablerIcons.load(icon, size=SIZE, color="#FFFFFF").save(path)
        print(path)


if __name__ == "__main__":
    main()
