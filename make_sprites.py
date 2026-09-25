"""Generate the crab's pixel-art frames into assets/.

Every frame is a 32x32 PNG built from the same parts (body, eyes, claws,
legs), so all animations stay consistent. Re-run after changing any part:

    python make_sprites.py
"""

from pathlib import Path

from PIL import Image

SIZE = 32
ASSETS = Path(__file__).parent / "assets"

CLEAR = (0, 0, 0, 0)
OUTLINE = (58, 16, 20, 255)
SHELL = (226, 68, 46, 255)
SHELL_LIGHT = (255, 128, 92, 255)
SHELL_DARK = (176, 44, 34, 255)
EYE_WHITE = (255, 255, 255, 255)
PUPIL = (20, 12, 16, 255)
BLUSH = (255, 150, 160, 255)
SWEAT = (120, 200, 255, 255)

# Left claw; the right claw is its mirror. "#" = shell, "." = empty.
CLAW_OPEN = [
    "##..##",
    "##..##",
    "######",
    "######",
    ".####.",
    "..##..",
]
CLAW_GRIP = [  # closed, pointing sideways at the rope
    ".###.",
    "#####",
    "####.",
    ".###.",
]
CLAW_HALF = [
    "###.##",
    "######",
    "######",
    "######",
    ".####.",
    "..##..",
]


class Canvas:
    def __init__(self):
        self.px = [[CLEAR] * SIZE for _ in range(SIZE)]
        self.ox = 0  # horizontal shift applied to every set()

    def set(self, x, y, color):
        x += self.ox
        if 0 <= x < SIZE and 0 <= y < SIZE:
            self.px[y][x] = color

    def mirror_set(self, x, y, color):
        self.set(x, y, color)
        self.set(SIZE - 1 - x, y, color)

    def line(self, x0, y0, x1, y1, color, mirror=True):
        dx, dy = abs(x1 - x0), -abs(y1 - y0)
        sx, sy = (1 if x0 < x1 else -1), (1 if y0 < y1 else -1)
        err = dx + dy
        while True:
            (self.mirror_set if mirror else self.set)(x0, y0, color)
            if x0 == x1 and y0 == y1:
                return
            e2 = 2 * err
            if e2 >= dy:
                err += dy
                x0 += sx
            if e2 <= dx:
                err += dx
                y0 += sy

    def outline(self):
        """Ring every filled shape with a 1px dark outline (4-neighbour)."""
        filled = {(x, y) for y in range(SIZE) for x in range(SIZE) if self.px[y][x] != CLEAR}
        for y in range(SIZE):
            for x in range(SIZE):
                if (x, y) in filled:
                    continue
                if any((x + dx, y + dy) in filled for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))):
                    self.px[y][x] = OUTLINE

    def image(self):
        img = Image.new("RGBA", (SIZE, SIZE))
        img.putdata([c for row in self.px for c in row])
        return img


def draw_crab(bob=0, legs=0, claw=CLAW_OPEN, claw_lift=0, eyes="open", mouth="smile",
              lean=0, pull=False, sweat=None, claws=True, props=None, details=None):
    """bob: body drop in px. legs: 0/1 walk phase. lean: shift body right (feet stay put).
    eyes: open | closed | happy | confused | strain | down. mouth: smile | wavy | grit.
    pull: left claw grips low (the rope side). sweat: y of a sweat drop, or None.
    claws=False skips the raised claws (props draws its own).
    props(c, bob): extra outlined shapes (headset, controller...). details(c, bob): after outline."""
    c = Canvas()
    cy = 19 + bob

    # Legs first so the body covers their roots. Feet stay planted while the body leans.
    for i, (ax, ay) in enumerate(((9, 20), (10, 21), (12, 22))):
        lift = 1 if (i + legs) % 2 else 0
        for side in (0, 1):
            flip = (lambda x: SIZE - 1 - x) if side else (lambda x: x)
            attach = (flip(ax) + lean, ay + bob)
            knee = (flip(ax - 3) + lean // 2, ay + bob + 2)
            foot = (flip(ax - 4 + i), 27 - lift)
            c.line(*attach, *knee, SHELL_DARK, mirror=False)
            c.line(*knee, *foot, SHELL_DARK, mirror=False)

    c.ox = lean  # everything from here on leans with the body

    # Body: a wide ellipse, lighter on top and darker underneath.
    for y in range(SIZE):
        for x in range(SIZE):
            if ((x - 15.5) / 9.5) ** 2 + ((y - cy) / 4.6) ** 2 <= 1:
                shade = SHELL_LIGHT if y <= cy - 3 else SHELL_DARK if y >= cy + 3 else SHELL
                c.set(x, y, shade)

    # Arms and claws. When pulling, the left claw grips the rope low and far out.
    c.ox = 0  # claws stay inside the frame; only the body leans
    top = 8 + bob - claw_lift
    sides = () if not claws else ("right",) if pull else ("left", "right")
    for side in sides:
        put = c.set if side == "left" else (lambda x, y, col: c.set(SIZE - 1 - x, y, col))
        for x, y in ((6, 17 + bob), (5, 16 + bob), (4, 15 + bob), (4, top + 6)):
            put(x, y, SHELL)
        for row, line in enumerate(claw):
            for col, ch in enumerate(line):
                if ch == "#":
                    put(1 + col, top + row, SHELL_LIGHT if row == 0 else SHELL)
    if pull:
        for x in range(4, 7 + lean):
            c.set(x, 18 + bob, SHELL)  # arm stretched toward the rope
        for row, line in enumerate(CLAW_GRIP):
            for col, ch in enumerate(line):
                if ch == "#":
                    c.set(1 + col, 16 + bob + row, SHELL_LIGHT if row == 0 else SHELL)
    c.ox = lean

    # Eye stalks and eyes.
    for y in range(11 + bob, cy - 3):
        c.mirror_set(12, y, SHELL)
    if eyes in ("open", "confused", "down"):
        for dx in range(3):
            for dy in range(3):
                c.mirror_set(11 + dx, 8 + bob + dy, EYE_WHITE)
        # Confused: pupils look in different directions.
        left, right = {"confused": ((11, 8), (20, 10)), "down": ((12, 10), (19, 10))}.get(
            eyes, ((12, 9), (19, 9)))
        for x, y in (left, right):
            c.set(x, y + bob, PUPIL)
            c.set(x, y + bob + (1 if y < 10 else -1), PUPIL)
    elif eyes == "happy":
        for dx in range(3):
            for dy in range(2):
                c.mirror_set(11 + dx, 9 + bob + dy, SHELL)
    elif eyes == "strain":
        for dx in range(3):
            for dy in range(3):
                c.mirror_set(11 + dx, 8 + bob + dy, EYE_WHITE)
    else:
        for dx in range(3):
            c.mirror_set(11 + dx, 10 + bob, SHELL)

    if sweat is not None:
        c.set(22, sweat + bob, SWEAT)
        c.set(22, sweat + bob + 1, SWEAT)
        c.set(23, sweat + bob + 1, SWEAT)

    if props:
        c.ox = 0
        props(c, bob)
    c.outline()

    # Face details go on after the outline so they stay inside the body.
    if eyes == "closed":
        for dx in range(3):
            c.mirror_set(11 + dx, 10 + bob, OUTLINE)
    elif eyes == "happy":
        for x, y in ((11, 10), (12, 9), (13, 10)):
            c.mirror_set(x, y + bob, OUTLINE)
    elif eyes == "strain":  # squeezed shut: > <
        for x, y in ((11, 8), (12, 9), (11, 10)):
            c.mirror_set(x, y + bob, OUTLINE)
    mouth_px = {
        "smile": ((14, 1), (15, 2), (16, 2), (17, 1)),
        "wavy": ((14, 2), (15, 1), (16, 2), (17, 1)),
        "grit": ((13, 1), (14, 1), (15, 1), (16, 1), (17, 1), (18, 1)),
    }[mouth]
    for x, dy in mouth_px:
        c.set(x, cy + dy, OUTLINE)
    if mouth == "grit":
        for x in (14, 16):
            c.set(x, cy + 1, EYE_WHITE)  # clenched teeth
    c.mirror_set(10, cy + 1, BLUSH)
    if details:
        details(c, bob)
    return c.image()


# --- gaming ----------------------------------------------------------------------

HEADSET = (45, 45, 55, 255)
PLASTIC = (60, 60, 70, 255)
PLASTIC_LIGHT = (95, 95, 110, 255)
GB_BODY = (196, 196, 184, 255)
GB_SCREEN = (155, 188, 15, 255)
GB_DARK = (48, 98, 48, 255)
LED = (80, 255, 120, 255)


def rect(c, x0, y0, x1, y1, color):
    for y in range(y0, y1 + 1):
        for x in range(x0, x1 + 1):
            c.set(x, y, color)


def grip_claw(c, x, y, mirror=False):
    """A small closed claw holding something, 4x3."""
    shape = [".##.", "####", ".##."]
    for row, line in enumerate(shape):
        for col, ch in enumerate(line):
            if ch == "#":
                px = x + (3 - col if mirror else col)
                c.set(px, y + row, SHELL_LIGHT if row == 0 else SHELL)


BEANBAG = (140, 70, 180, 255)
BEANBAG_LIGHT = (180, 115, 215, 255)
BEANBAG_DARK = (105, 50, 140, 255)
CHAIR = (38, 38, 44, 255)
CHAIR_RED = (210, 45, 55, 255)
CRT = (165, 160, 145, 255)
CRT_DARK = (120, 115, 105, 255)
SCREEN_OFF = (25, 25, 30, 255)


def ellipse(c, cx, cy, rx, ry, color):
    for y in range(SIZE):
        for x in range(SIZE):
            if ((x - cx) / rx) ** 2 + ((y - cy) / ry) ** 2 <= 1:
                c.set(x, y, color(x, y) if callable(color) else color)


def draw_gamer(style, frame):
    """Side view, facing right toward the TV: sitting back, eyes up on the screen,
    controller in his claws. style: "retro" (beanbag) | "modern" (gaming chair + headset).
    The app mirrors it when the TV is on his left."""
    c = Canvas()
    mash = frame % 2
    bob = 1 if frame in (1, 2) else 0          # bouncing with excitement
    cy = (19 if style == "retro" else 17) + bob

    # The seat.
    if style == "retro":
        ellipse(c, 15, 25, 13, 5.5, lambda x, y: BEANBAG_LIGHT if y < 22 and x < 14 else
                BEANBAG_DARK if y > 27 else BEANBAG)
    else:
        rect(c, 4, 6, 7, 21, CHAIR)             # tall backrest
        rect(c, 5, 8, 6, 19, CHAIR_RED)         # racing stripe
        rect(c, 6, 21, 24, 23, CHAIR)           # seat cushion
        rect(c, 8, 21, 22, 21, CHAIR_RED)
        rect(c, 14, 24, 16, 26, CHAIR)          # gas lift
        rect(c, 9, 27, 21, 27, CHAIR)           # star base
        for x in (9, 15, 21):
            c.set(x, 28, CHAIR)                 # wheels

    # Little legs dangling off the front of the seat.
    for i, x in enumerate((17, 20, 23)):
        c.line(x, cy + 3, x + 1, cy + 6 + (i + mash) % 2, SHELL_DARK, mirror=False)
    # Body, side-on: a chunky oval.
    ellipse(c, 15, cy, 9, 5.5, lambda x, y: SHELL_LIGHT if y <= cy - 3 else
            SHELL_DARK if y >= cy + 3 else SHELL)
    # Back claw peeking over his shell.
    grip_claw(c, 7, cy - 7)
    c.set(9, cy - 4, SHELL)
    c.set(9, cy - 5, SHELL)
    # Two eye stalks, clearly apart, eyes up on the screen.
    for x, top in ((14, 7), (20, 6)):
        for y in range(top + bob, cy - 4):
            c.set(x, y, SHELL)
    rect(c, 13, 4 + bob, 15, 6 + bob, EYE_WHITE)
    rect(c, 19, 3 + bob, 21, 5 + bob, EYE_WHITE)
    # Front arm reaching to the controller, claw on the buttons.
    for x, y in ((23, cy - 1), (24, cy - 2)):
        c.set(x, y, SHELL)
    rect(c, 24, cy - 1 + mash, 30, cy + 1 + mash, PLASTIC)     # controller
    grip_claw(c, 24, cy - 3 - mash)
    if style == "modern":
        for x in range(14, 21):
            c.set(x, 1 + bob, HEADSET)                          # band over both eyes
        c.set(13, 2 + bob, HEADSET)
        c.set(21, 2 + bob, HEADSET)
        rect(c, 16, 7 + bob, 18, 9 + bob, HEADSET)              # ear cup between the stalks
        c.line(18, 9 + bob, 23, 12 + bob, HEADSET, mirror=False)  # mic boom
    c.outline()

    # Details on top of the outline.
    c.set(15, 4 + bob, PUPIL)                                   # both looking up-right
    c.set(15, 5 + bob, PUPIL)
    c.set(21, 3 + bob, PUPIL)
    c.set(21, 4 + bob, PUPIL)
    c.set(22, cy + 1, OUTLINE)                                  # grin
    c.set(23, cy + 2, OUTLINE)
    c.set(20, cy + 1, BLUSH)
    for x in (26, 28):
        c.set(x, cy + mash, PLASTIC_LIGHT)                      # buttons
    c.set(29, cy + mash, (230, 70, 70, 255))
    if style == "modern":
        c.set(17, 8 + bob, LED if frame < 2 else PLASTIC_LIGHT)
    else:
        for x, y in ((6, 22), (9, 21), (22, 23)):
            c.set(x, y, BEANBAG_LIGHT)                          # beanbag crinkles
    return c.image()


def draw_tv(style, frame):
    """The TV he's playing, on a wooden table, with the game running (32x32)."""
    c = Canvas()
    if style == "retro":
        # Low wooden table with a console on it.
        rect(c, 1, 22, 30, 23, WOOD)
        rect(c, 2, 24, 29, 24, WOOD_DARK)
        rect(c, 3, 25, 4, 29, WOOD_DARK)
        rect(c, 27, 25, 28, 29, WOOD_DARK)
        rect(c, 22, 19, 29, 21, CRT)                         # console
        c.line(12, 4, 8, 0, CRT_DARK, mirror=False)          # rabbit ears
        c.line(15, 4, 19, 0, CRT_DARK, mirror=False)
        rect(c, 3, 4, 24, 21, CRT)                           # boxy CRT
        rect(c, 20, 6, 23, 19, CRT_DARK)                     # knob panel
        rect(c, 5, 6, 18, 19, SCREEN_OFF)
        c.outline()
        # A platformer: sky, clouds, brick ground, a pipe scrolling by, hero hopping.
        rect(c, 6, 7, 17, 15, (100, 150, 255, 255))
        rect(c, 8 + frame % 2, 8, 10 + frame % 2, 8, EYE_WHITE)
        rect(c, 6, 16, 17, 18, (190, 95, 45, 255))
        for x in range(6, 18, 3):
            c.set(x, 17, (120, 55, 25, 255))
        pipe = 15 - frame * 2
        rect(c, pipe, 13, pipe + 1, 15, (60, 180, 70, 255))
        hero_y = 12 if frame in (1, 2) else 14
        rect(c, 8, hero_y, 9, hero_y + 1, (230, 50, 40, 255))
        if frame % 2:
            c.set(12, 10, (255, 220, 60, 255))                # coin
        for y in (8, 11):
            c.set(21, y, (60, 55, 50, 255))                   # knobs
        c.set(27, 20, (230, 60, 60, 255))                     # console power light
        c.px[5][5] = c.px[5][18] = CRT                        # rounded screen corners
    else:
        # Wooden TV stand with drawers.
        rect(c, 1, 22, 30, 28, WOOD)
        rect(c, 1, 22, 30, 22, (180, 120, 75, 255))
        c.line(15, 23, 15, 28, WOOD_DARK, mirror=False)
        rect(c, 7, 25, 9, 25, WOOD_DARK)
        rect(c, 21, 25, 23, 25, WOOD_DARK)
        rect(c, 2, 29, 3, 29, WOOD_DARK)
        rect(c, 28, 29, 29, 29, WOOD_DARK)
        rect(c, 22, 19, 28, 21, PLASTIC)                       # console
        rect(c, 13, 18, 18, 21, PLASTIC)                       # TV foot
        rect(c, 1, 2, 30, 17, (20, 20, 25, 255))               # flat screen bezel
        c.outline()
        # A racing game: sky, hills, a road rushing toward you, your car weaving.
        rect(c, 2, 3, 29, 7, (90, 150, 240, 255))
        rect(c, 2, 8, 29, 9, (60, 160, 80, 255))
        for y in range(9, 17):
            half = 1 + (y - 9) * 2
            rect(c, 2, y, 29, y, (60, 160, 80, 255))
            rect(c, max(2, 15 - half), y, min(29, 16 + half), y, (90, 90, 100, 255))
            if (y + frame) % 3 == 0:
                c.set(15, y, EYE_WHITE)                       # lane dashes
                c.set(16, y, EYE_WHITE)
        car = 14 + (-1, 0, 1, 0)[frame]
        rect(c, car, 14, car + 3, 15, (230, 50, 40, 255))
        c.set(car, 16, OUTLINE)
        c.set(car + 3, 16, OUTLINE)
        tree = 4 + frame
        rect(c, tree, 10, tree + 1, 11, (30, 110, 50, 255))
        rect(c, 27 - frame, 10, 28 - frame, 11, (30, 110, 50, 255))
        c.set(26, 20, (80, 140, 255, 255))                    # console light
    return c.image()


# --- sleeping in bed -------------------------------------------------------------

WOOD = (150, 95, 55, 255)
WOOD_DARK = (115, 70, 40, 255)
SHEET = (245, 245, 240, 255)
BLANKET = (70, 110, 210, 255)
BLANKET_LIGHT = (110, 150, 240, 255)
CAP = (60, 90, 190, 255)
CAP_STRIPE = (235, 235, 245, 255)


def draw_bed(frame):
    """Tucked in: his shell and sleepy face peek over the blanket (which rises as he
    breathes), eye stalks up in a striped nightcap with a pom-pom."""
    c = Canvas()
    breathe = frame % 2
    rect(c, 4, 12, 27, 16, SHEET)                    # pillow behind him
    # His shell, peeking over the blanket.
    for y in range(12, 19):
        for x in range(SIZE):
            if ((x - 15.5) / 8.5) ** 2 + ((y - 17.5) / 4) ** 2 <= 1:
                c.set(x, y, SHELL_LIGHT if y <= 14 else SHELL)
    for x in (12, 19):                               # eye stalks
        for y in range(9, 14):
            c.set(x, y, SHELL)
    rect(c, 11, 7, 13, 9, SHELL)                     # closed eyes (lids)
    rect(c, 18, 7, 20, 9, SHELL)
    # Nightcap over both eyes, flopping right to a pom-pom.
    rect(c, 10, 5, 21, 6, CAP_STRIPE)
    rect(c, 12, 3, 21, 4, CAP)
    rect(c, 16, 2, 23, 2, CAP_STRIPE)
    rect(c, 22, 3, 24, 3, CAP)
    rect(c, 24, 3 + breathe, 26, 5 + breathe, SHEET)  # pom-pom sways
    # Blanket: a rounded hump that rises on the in-breath.
    top = 18 - breathe
    for y in range(top, 24):
        for x in range(3, 29):
            edge = abs(x - 15.5)
            if y >= top + (1 if edge > 10 else 0) + (1 if edge > 12 else 0):
                c.set(x, y, BLANKET_LIGHT if (x + y) % 4 == 0 else BLANKET)
    rect(c, 5, top, 26, top, SHEET)                  # folded-over sheet
    grip_claw(c, 5, top - 2)                         # one claw holding the blanket
    rect(c, 2, 22, 29, 23, SHEET)                    # mattress edge
    rect(c, 1, 24, 30, 26, WOOD)                     # bed frame
    rect(c, 1, 26, 30, 26, WOOD_DARK)
    rect(c, 2, 27, 3, 28, WOOD_DARK)                 # legs
    rect(c, 28, 27, 29, 28, WOOD_DARK)
    c.outline()
    for x in (11, 12, 13, 18, 19, 20):               # closed-eye lines
        c.set(x, 8, OUTLINE)
    for x, y in ((14, 15), (15, 16), (16, 16), (17, 15)):  # sleepy smile
        c.set(x, y + breathe * 0, OUTLINE)
    c.set(10, 16, BLUSH)
    c.set(21, 16, BLUSH)
    return c.image()


FRAMES = {
    "walk": [
        draw_crab(bob=0, legs=0),
        draw_crab(bob=1, legs=1, claw_lift=1),
        draw_crab(bob=0, legs=1),
        draw_crab(bob=1, legs=0, claw_lift=1),
    ],
    "idle": [
        draw_crab(claw=CLAW_OPEN),
        draw_crab(claw=CLAW_HALF),
    ],
    "happy": [
        draw_crab(eyes="happy", claw_lift=2),
        draw_crab(bob=1, eyes="happy", claw=CLAW_HALF),
    ],
    "confused": [
        draw_crab(eyes="confused", mouth="wavy", claw=CLAW_HALF),
        draw_crab(eyes="confused", mouth="wavy", claw=CLAW_HALF, claw_lift=1),
    ],
    # Dragging a file: leaning away, straining, sweating. File/rope on the left;
    # the app mirrors these when the file is on the right.
    "pull": [
        draw_crab(lean=2, legs=0, pull=True, eyes="strain", mouth="grit", claw_lift=1, sweat=6),
        draw_crab(lean=3, legs=1, pull=True, eyes="strain", mouth="grit", bob=1, sweat=8),
        draw_crab(lean=2, legs=1, pull=True, eyes="strain", mouth="grit", claw_lift=2, sweat=10),
        draw_crab(lean=1, legs=0, pull=True, eyes="strain", mouth="grit", bob=1),
    ],
    "sleep": [draw_bed(0), draw_bed(1)],
    # Gaming scenes, facing right (the app mirrors them to face left).
    "game_modern": [draw_gamer("modern", f) for f in range(4)],
    "game_retro": [draw_gamer("retro", f) for f in range(4)],
}


FILE_ICON = [
    "#######",
    "#.....##",
    "#.....#.#",
    "#.....####",
    "#.------.#",
    "#........#",
    "#.------.#",
    "#........#",
    "#.------.#",
    "#........#",
    "#.----...#",
    "#........#",
    "##########",
]


def draw_file_icon():
    """The page he drags back: '#' outline, '.' paper, '-' text lines."""
    colors = {"#": OUTLINE, ".": EYE_WHITE, "-": (170, 180, 195, 255)}
    img = Image.new("RGBA", (10, len(FILE_ICON)))
    for y, row in enumerate(FILE_ICON):
        for x, ch in enumerate(row):
            if ch in colors:
                img.putpixel((x, y), colors[ch])
    return img


GLOBE_LAND = [  # "#" = land on a 16x16 globe
    "................",
    "................",
    "......###.......",
    "....#####...##..",
    "...######..###..",
    "...#####....#...",
    "....###.........",
    ".....##....##...",
    "......#...####..",
    "..........#####.",
    "...##......###..",
    "...###......#...",
    "....##..........",
    "................",
    "................",
    "................",
]


def draw_globe():
    """What he carries back from a web search."""
    ocean, ocean_light, land = (70, 150, 230, 255), (120, 190, 250, 255), (90, 190, 90, 255)
    img = Image.new("RGBA", (16, 16))
    for y in range(16):
        for x in range(16):
            d = ((x - 7.5) ** 2 + (y - 7.5) ** 2) ** 0.5
            if d <= 6.6:
                color = land if GLOBE_LAND[y][x] == "#" else ocean_light if x + y < 11 else ocean
                img.putpixel((x, y), color)
            elif d <= 7.6:
                img.putpixel((x, y), OUTLINE)
    return img


def main():
    ASSETS.mkdir(exist_ok=True)
    draw_file_icon().save(ASSETS / "file.png")
    draw_globe().save(ASSETS / "globe.png")
    for i in range(4):
        for style in ("retro", "modern"):
            draw_tv(style, i).save(ASSETS / f"tv_{style}_{i}.png")
    for name, frames in FRAMES.items():
        for i, frame in enumerate(frames):
            frame.save(ASSETS / f"{name}_{i}.png")

    # Preview sheet (8x scale) for eyeballing every frame at once.
    all_frames = [f for frames in FRAMES.values() for f in frames]
    sheet = Image.new("RGBA", (SIZE * len(all_frames), SIZE), (200, 220, 235, 255))
    for i, frame in enumerate(all_frames):
        sheet.alpha_composite(frame, (i * SIZE, 0))
    sheet.resize((sheet.width * 8, sheet.height * 8), Image.NEAREST).save(ASSETS / "preview.png")
    print(f"Wrote {len(all_frames)} frames to {ASSETS}")


if __name__ == "__main__":
    main()
