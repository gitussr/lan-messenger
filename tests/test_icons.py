import os
import re

import gui


def test_every_icon_used_by_the_gui_has_a_png():
    with open(gui.__file__, encoding="utf-8") as f:
        names = set(re.findall(r'_icon_image\(\s*"(\w+)"', f.read()))

    assert names
    for name in names:
        assert os.path.isfile(os.path.join(gui.ICON_DIR, f"{name}.png")), name


def test_tinted_icon_takes_the_color_and_keeps_the_shape():
    img = gui._tinted_icon("paperclip", 36, "#FF0000")

    assert img.size == (36, 36)
    assert img.mode == "RGBA"
    red, green, blue, alpha = img.split()
    assert (red.getextrema(), green.getextrema(), blue.getextrema()) == ((255, 255), (0, 0), (0, 0))
    lowest, highest = alpha.getextrema()
    assert highest > 0, "icon has no visible pixels"
    assert lowest == 0, "icon has no transparent background"
