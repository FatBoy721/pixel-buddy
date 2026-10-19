"""Generate the crab's pixel-art frames into assets/.

Every frame is a 32x32 PNG built from the same parts (body, eyes, claws,
legs), so all animations stay consistent. Re-run after changing any part:

    python make_sprites.py
"""

import shutil
from pathlib import Path

from PIL import Image

SIZE = 32
ASSETS = Path(__file__).parent / "assets"

CLEAR = (0, 0, 0, 0)
OUTLINE = (14, 14, 26, 255)
SHELL = (34, 78, 222, 255)      # blue yarn
SHELL_LIGHT = (66, 112, 244, 255)
SHELL_DARK = (22, 52, 170, 255)
EYE_WHITE = (255, 255, 255, 255)
PUPIL = (20, 12, 16, 255)
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
        self.stitch_dx = self.stitch_dy = 0  # yarn texture follows the body, not the frame

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
        img.putdata([stitch(c, x - self.stitch_dx, y - self.stitch_dy)
                     for y, row in enumerate(self.px) for x, c in enumerate(row)])
        return img


def stitch(color, x, y):
    """Crochet texture on shell pixels: 2x2 stitches in rows offset by one, each with a
    lit top-left and shaded bottom-right, so he reads as knitted yarn."""
    if color not in (SHELL, SHELL_LIGHT, SHELL_DARK):
        return color
    phase = (x + y // 2) % 2
    k = 1.18 if (y % 2, phase) == (0, 0) else 0.8 if (y % 2, phase) == (1, 1) else 1
    return tuple(min(255, round(v * k)) for v in color[:3]) + (255,)


HAT = None  # set to a hat(c, bob, lean) function while baking a season


def draw_crab(bob=0, legs=0, claw=CLAW_OPEN, claw_lift=0, eyes="open", mouth="smile",
              lean=0, pull=False, sweat=None, claws=True, props=None, details=None):
    """bob: body drop in px. legs: 0/1 walk phase. lean: shift body right (feet stay put).
    eyes: open | closed | happy | confused | strain | down. mouth: smile | wavy | grit.
    pull: left claw grips low (the rope side). sweat: y of a sweat drop, or None.
    claws=False skips the raised claws (props draws its own).
    props(c, bob): extra outlined shapes (headset, controller...). details(c, bob): after outline."""
    c = Canvas()
    c.stitch_dx, c.stitch_dy = lean, bob
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
        "curl": ((14, 2), (15, 2), (16, 1), (17, 0)),  # Elvis lip curl
    }[mouth]
    for x, dy in mouth_px:
        c.set(x, cy + dy, OUTLINE)
    if mouth == "grit":
        for x in (14, 16):
            c.set(x, cy + 1, EYE_WHITE)  # clenched teeth
    if details:
        details(c, bob)
    if HAT:
        HAT(c, bob, lean)
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


# --- inspecting your hardware ----------------------------------------------------

PCB = (28, 110, 62, 255)
PCB_DARK = (18, 78, 44, 255)
GOLD = (218, 178, 70, 255)
CHIP = (40, 40, 48, 255)
SILVER = (185, 190, 200, 255)
GLASS = (168, 222, 250, 140)
GLASS_GLINT = (255, 255, 255, 255)
RIM = (95, 95, 110, 255)
HANDLE = (120, 72, 40, 255)


def draw_motherboard(c):
    """The board on the ground he's crouched over: PCB, traces, chips, RAM slot."""
    rect(c, 1, 24, 30, 30, PCB)
    rect(c, 1, 30, 30, 30, PCB_DARK)
    for y in (26, 29):                              # gold traces running across it
        for x in range(2, 30, 2):
            c.set(x, y, GOLD)
    rect(c, 4, 25, 10, 28, CHIP)                    # the big chip
    for x in range(4, 11, 2):                       # its pins
        c.set(x, 29, GOLD)
    rect(c, 13, 25, 14, 29, SILVER)                 # RAM stick in its slot
    rect(c, 16, 25, 17, 29, SILVER)
    rect(c, 20, 26, 22, 28, CHIP)                   # smaller chips
    rect(c, 25, 27, 27, 28, CHIP)
    for x in (24, 28):                              # capacitors
        c.set(x, 25, SILVER)
        c.set(x, 26, SILVER)


def draw_magnifier(c, cx, cy):
    """A round glass with a handle, drawn over whatever is under it."""
    for y in range(SIZE):
        for x in range(SIZE):
            d = ((x - cx) ** 2 + (y - cy) ** 2) ** 0.5
            if d <= 3.2:
                c.set(x, y, GLASS)
            elif d <= 4.4:
                c.set(x, y, RIM)
    c.line(cx + 3, cy + 3, cx + 6, cy + 6, HANDLE, mirror=False)
    c.line(cx + 4, cy + 3, cx + 7, cy + 6, HANDLE, mirror=False)


def eyes_looking(c, left, right, bob, down=1, side=1):
    """Two 3x3 eyes at (x, y) top-left each, with a 1x2 pupil like the rest of his
    frames. down/side nudge the pupils so he's clearly looking somewhere. Returns the
    pupil-drawing step: run it after outline(), so the pupils land inside the white
    instead of under the dark ring around it."""
    for x, y in (left, right):
        rect(c, x, y + bob, x + 2, y + 2 + bob, EYE_WHITE)
    return lambda: [rect(c, x + side, y + down + bob, x + side, y + down + 1 + bob, PUPIL)
                    for x, y in (left, right)]


def draw_inspect(frame):
    """Crouched over a motherboard, magnifying glass in his claw, squinting at the
    chips. The glass slides along the board and catches the light."""
    c = Canvas()
    bob = frame % 2
    cy = 13 + bob
    glass_x = (19, 22, 25, 22)[frame]

    # Legs braced on the board.
    for i, x in enumerate((5, 8, 11)):
        c.line(x, cy + 3, x - 1 + i, 24, SHELL_DARK, mirror=False)
    # Body, side-on, hunched right over the board.
    ellipse(c, 8, cy, 7, 4.5, lambda x, y: SHELL_LIGHT if y <= cy - 3 else
            SHELL_DARK if y >= cy + 3 else SHELL)
    # Eye stalks, both eyes down on the glass.
    for x, top in ((6, 5), (11, 4)):
        for y in range(top + bob, cy - 2):
            c.set(x, y, SHELL)
    pupils = eyes_looking(c, (5, 3), (10, 2), bob, down=1, side=1)
    # Arm reaching down-right to the magnifier.
    c.line(12, cy + 1, glass_x - 4, 18, SHELL, mirror=False)
    grip_claw(c, glass_x - 5, 17)

    draw_motherboard(c)
    c.outline()
    draw_magnifier(c, glass_x, 21)                  # glass goes on last: it's see-through
    pupils()

    c.set(13, cy + 2, OUTLINE)                      # "hmm" mouth
    c.set(14, cy + 2, OUTLINE)
    if frame % 2:                                   # glint sweeping across the glass
        c.set(glass_x - 1, 19, GLASS_GLINT)
        c.set(glass_x, 19, GLASS_GLINT)
    return c.image()


# --- installing Ollama ------------------------------------------------------------

BEZEL = (30, 30, 38, 255)
SCREEN = (18, 22, 40, 255)
CLOUD = (238, 244, 252, 255)
CLOUD_DARK = (186, 200, 220, 255)
ARROW = (90, 200, 255, 255)
BAR_FILL = (90, 220, 130, 255)
KEYS = (205, 205, 212, 255)


def draw_install(frame):
    """Sat at a desktop PC downloading his own brain: a cloud on the monitor with
    an arrow pulling it down, a progress bar filling, claws mashing the keyboard."""
    c = Canvas()
    bob = frame % 2
    cy = 19 + bob

    # Monitor on the right, on the desk.
    rect(c, 15, 3, 31, 20, BEZEL)
    rect(c, 16, 4, 30, 18, SCREEN)
    rect(c, 22, 21, 24, 24, PLASTIC)                # stand
    rect(c, 19, 25, 28, 25, PLASTIC)                # base
    # Cloud being yanked out of the internet, one pixel at a time.
    rect(c, 20, 6, 27, 8, CLOUD)
    rect(c, 22, 5, 25, 5, CLOUD)
    rect(c, 20, 9, 27, 9, CLOUD_DARK)
    for i in range(3):                              # data falling out of it
        drop_y = 10 + (frame + i * 2) % 5
        c.set(21 + i * 3, drop_y, ARROW)
    c.line(24, 10, 24, 13, ARROW, mirror=False)     # download arrow
    for dx in (-1, 0, 1):
        c.set(24 + dx, 13, ARROW)
    c.set(24, 14, ARROW)
    # Progress bar, filling across the four frames.
    rect(c, 17, 16, 29, 17, BEZEL)
    rect(c, 18, 16, 18 + frame * 3, 17, BAR_FILL)

    # The desk, and him sat behind it.
    rect(c, 0, 26, 31, 27, WOOD)
    rect(c, 0, 28, 31, 29, WOOD_DARK)
    for i, x in enumerate((4, 7, 10)):               # legs dangling under the desk
        c.line(x, cy + 3, x + (i - 1), 26, SHELL_DARK, mirror=False)
    ellipse(c, 7, cy, 6.5, 4.5, lambda x, y: SHELL_LIGHT if y <= cy - 3 else
            SHELL_DARK if y >= cy + 3 else SHELL)
    for x, top in ((5, 7), (10, 6)):                 # eye stalks, watching the download
        for y in range(top + bob, cy - 2):
            c.set(x, y, SHELL)
    pupils = eyes_looking(c, (4, 5), (9, 4), bob, down=1, side=1)  # eyes right, on the screen
    rect(c, 2, 24, 11, 25, KEYS)                     # keyboard on the desk
    c.line(12, cy, 13, 23, SHELL, mirror=False)      # arm down to it
    grip_claw(c, 10, 21 + bob)                       # claw tapping keys
    c.outline()
    pupils()

    for x in range(3, 11, 2):                        # key caps
        c.set(x, 24, PLASTIC_LIGHT)
    c.set(12, cy + 2, OUTLINE)                       # tiny grin
    c.set(13, cy + 3, OUTLINE)
    return c.image()


# --- sleeping in bed -------------------------------------------------------------

WOOD = (150, 95, 55, 255)
WOOD_DARK = (115, 70, 40, 255)
SHEET = (245, 245, 240, 255)
BLANKET = (196, 64, 58, 255)      # warm red quilt, so the blue crab stands out
BLANKET_LIGHT = (232, 106, 92, 255)
CAP = (112, 66, 168, 255)
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
    return c.image()


# --- halloween -------------------------------------------------------------------

HAT_BLACK = (40, 28, 52, 255)
HAT_PURPLE = (92, 52, 140, 255)
HAT_BAND = (255, 140, 30, 255)
PUMPKIN = (240, 120, 20, 255)
PUMPKIN_DARK = (190, 80, 10, 255)
STEM = (70, 120, 40, 255)
GLOW = (255, 220, 80, 255)
GHOST_SHEET = (236, 236, 246, 255)
GHOST_SHADE = (196, 196, 214, 255)


def witch_hat(c, bob, lean):
    """Big witch hat: wide brim resting on his eyes, tall tip bent to the right.
    Drawn on its own layer, outlined, then stamped on top of the crab."""
    layer = Canvas()
    for x in range(8, 24):
        layer.set(x, 6 + bob, HAT_BLACK)                        # brim
    for x in range(12, 20):
        layer.set(x, 5 + bob, HAT_BAND)                         # band
    cone = {4: (12, 19), 3: (13, 18), 2: (14, 18), 1: (16, 19), 0: (18, 21)}
    for y, (x0, x1) in cone.items():
        for x in range(x0, x1 + 1):
            layer.set(x, y + bob, HAT_PURPLE if x == x0 else HAT_BLACK)
    layer.outline()
    for y in range(SIZE):
        for x in range(SIZE):
            if layer.px[y][x] != CLEAR and 0 <= x + lean < SIZE:
                c.px[y][x + lean] = layer.px[y][x]


def pumpkin(c, cx, cy, rx, ry):
    """Round ribbed pumpkin with a stem, centered at (cx, cy)."""
    for y in range(SIZE):
        for x in range(SIZE):
            if ((x - cx) / rx) ** 2 + ((y - cy) / ry) ** 2 <= 1:
                c.set(x, y, PUMPKIN_DARK if abs(x - cx) in (rx // 2, rx // 2 + 1) else PUMPKIN)
    c.set(int(cx), int(cy - ry), STEM)
    c.set(int(cx) + 1, int(cy - ry) - 1, STEM)


def jack_face(c, cx, cy, lit=True):
    """Carved face, drawn after outlining so it stays crisp."""
    color = GLOW if lit else OUTLINE
    for dx, dy in ((-3, -2), (-2, -2), (-3, -1), (2, -2), (3, -2), (3, -1)):   # eyes
        c.set(int(cx) + dx, int(cy) + dy, color)
    for dx in range(-3, 4):                                                     # grin
        c.set(int(cx) + dx, int(cy) + 2 - (dx in (-3, 3)), color)


def stamp_pumpkin(c, cx, cy, rx, ry):
    """Pumpkin on its own outlined layer, stamped over the crab (covers his mouth/blush)."""
    layer = Canvas()
    pumpkin(layer, cx, cy, rx, ry)
    layer.outline()
    for y in range(SIZE):
        for x in range(SIZE):
            if layer.px[y][x] != CLEAR:
                c.px[y][x] = layer.px[y][x]


def draw_carve(frame):
    """Behind a pumpkin, scraping at it; the face appears on the last two frames."""
    def front(c, bob):
        stamp_pumpkin(c, 15.5, 24, 8, 5)
        if frame >= 2:
            jack_face(c, 15.5, 24, lit=frame == 3)
    return draw_crab(bob=frame % 2, claw=CLAW_HALF if frame % 2 else CLAW_OPEN, claw_lift=frame % 2,
                     details=front)


def draw_ghost(frame):
    """Sheet over his head: two eye holes, wavy hem, his legs poking out. Floats."""
    c = Canvas()
    lift = (0, 1, 2, 1)[frame]
    for ax, ay in ((10, 24), (12, 25), (14, 25)):                           # legs under the hem
        for x in (ax, SIZE - 1 - ax):
            c.line(x, ay - lift, x, 27 - lift, SHELL_DARK, mirror=False)
    for y in range(SIZE):
        for x in range(SIZE):
            top = ((x - 15.5) / 8.5) ** 2 + ((y - 13 + lift) / 8) ** 2 <= 1 and y <= 13 - lift
            body = 7 <= x <= 24 and 13 - lift < y <= 22 - lift + ((x + frame) // 3) % 2
            if top or body:
                c.set(x, y, GHOST_SHADE if x >= 21 else GHOST_SHEET)
    c.outline()
    for x, y in ((12, 11), (13, 11), (12, 12), (13, 12), (18, 11), (19, 11), (18, 12), (19, 12)):
        c.set(x, y - lift, PUPIL)                                            # eye holes
    return c.image()


def draw_boo(frame):
    """Ducks into a pumpkin, then pops out arms-up."""
    c = Canvas()
    if frame < 2:    # 0: just his eyes over the rim, 1: hidden, pumpkin wobbles
        if frame == 0:
            for x0 in (11, 18):
                for dx in range(3):
                    for dy in range(3):
                        c.set(x0 + dx, 13 + dy, EYE_WHITE)
        stamp_pumpkin(c, 15.5 + frame, 23, 10, 6)
        c.outline()
        if frame == 0:
            c.set(12, 14, PUPIL)
            c.set(19, 14, PUPIL)
        return c.image()
    return draw_crab(bob=-1 if frame == 2 else 0, eyes="happy", claw_lift=3 if frame == 2 else 2,
                     details=lambda c, bob: stamp_pumpkin(c, 15.5, 26, 10, 4))


# --- halloween costumes ------------------------------------------------------------
# Lookalikes only; the app never uses the movie characters' names.

STEEL = (210, 215, 225, 255)
STEEL_DARK = (150, 155, 170, 255)
KNIFE_HANDLE = (90, 55, 30, 255)
MASK = (232, 228, 214, 255)
MASK_SHADE = (196, 190, 172, 255)
HOLE = (20, 20, 24, 255)
BLOOD = (200, 30, 40, 255)
SCREAM_WHITE = (240, 240, 236, 255)


def body_colors(base, light, dark):
    """Shell colors -> outfit colors."""
    return {SHELL: base, SHELL_LIGHT: light, SHELL_DARK: dark}


JUMPSUIT = body_colors((40, 55, 95, 255), (65, 85, 135, 255), (28, 38, 70, 255))
JACKET = body_colors((80, 84, 66, 255), (104, 108, 86, 255), (58, 60, 48, 255))
ROBE = body_colors((30, 28, 34, 255), (52, 50, 58, 255), (18, 16, 22, 255))


def stamp_layer(c, layer, lean):
    layer.outline()
    for y in range(SIZE):
        for x in range(SIZE):
            if layer.px[y][x] != CLEAR and 0 <= x + lean < SIZE:
                c.px[y][x + lean] = layer.px[y][x]


def recolor_body(c, colors, y0):
    # x 5..26 only: the outer columns hold just the rope-pulling claw, which stays bare
    # like his raised claws.
    for y in range(max(y0, 0), SIZE):
        for x in range(5, SIZE - 5):
            if c.px[y][x] in colors:
                c.px[y][x] = colors[c.px[y][x]]


def fill(layer, x0, y0, x1, y1, color):
    for y in range(y0, y1 + 1):
        for x in range(x0, x1 + 1):
            layer.set(x, y, color)


def knife(layer, bob, x=27):
    """Kitchen knife held up in his right claw."""
    for y in range(0, 6):
        layer.set(x, y + bob, STEEL if y < 5 else STEEL_DARK)
    layer.set(x + 1, 1 + bob, STEEL_DARK)
    for y in range(6, 8):
        layer.set(x, y + bob, KNIFE_HANDLE)


def machete(layer, bob, x=27):
    for y in range(0, 7):
        layer.set(x, y + bob, STEEL)
        layer.set(x + 1, y + bob, STEEL_DARK if y else STEEL)
    for y in range(7, 9):
        layer.set(x, y + bob, KNIFE_HANDLE)


def slasher(c, bob, lean):
    """Blank white mask, dark hair, navy jumpsuit, kitchen knife."""
    recolor_body(c, JUMPSUIT, 15 + bob)
    layer = Canvas()
    for y in range(4, 14):                                      # wide, rounded mask
        for x in range(9, 23):
            if ((x - 15.5) / 7) ** 2 + ((y - 9) / 5.5) ** 2 <= 1:
                layer.set(x, y + bob, MASK_SHADE if x >= 20 or y >= 12 else MASK)
    for x0 in range(9, 23):                                     # hair over the top
        layer.set(x0, 4 + bob, (30, 24, 20, 255))
        if x0 in (9, 10, 21, 22) or x0 % 3 == 0:
            layer.set(x0, 5 + bob, (30, 24, 20, 255))
    for x, y in ((11, 8), (12, 8), (13, 8), (12, 9), (13, 9), (18, 8), (19, 8), (20, 8), (18, 9), (19, 9)):
        layer.set(x, y + bob, HOLE)                             # deep eye sockets
    for x in range(14, 18):
        layer.set(x, 12 + bob, MASK_SHADE)                      # thin mouth
    knife(layer, bob)
    stamp_layer(c, layer, lean)


def hockey(c, bob, lean):
    """Hockey mask with red marks, olive jacket, machete."""
    recolor_body(c, JACKET, 15 + bob)
    layer = Canvas()
    for y in range(5, 14):
        for x in range(10, 22):
            if ((x - 15.5) / 6) ** 2 + ((y - 9.5) / 5) ** 2 <= 1:
                layer.set(x, y + bob, MASK)
    for x, y in ((12, 9), (13, 9), (18, 9), (19, 9), (15, 7), (16, 7), (15, 11), (16, 11), (13, 12), (18, 12)):
        layer.set(x, y + bob, HOLE)
    for x, y in ((12, 7), (13, 6), (18, 6), (19, 7), (11, 10), (20, 10)):
        layer.set(x, y + bob, BLOOD)
    machete(layer, bob)
    stamp_layer(c, layer, lean)


def screamer(c, bob, lean):
    """Black hood, long white screaming mask, black robe, knife."""
    recolor_body(c, ROBE, 15 + bob)
    layer = Canvas()
    for y in range(2, 16):
        for x in range(8, 24):
            if ((x - 15.5) / 7.5) ** 2 + ((y - 9) / 7) ** 2 <= 1:
                layer.set(x, y + bob, ROBE[SHELL])
    for y in range(4, 15):
        for x in range(11, 21):
            if ((x - 15.5) / 4.5) ** 2 + ((y - 9.5) / 5.5) ** 2 <= 1:
                layer.set(x, y + bob, SCREAM_WHITE)
    for x, y in ((13, 6), (13, 7), (13, 8), (14, 7), (18, 6), (18, 7), (18, 8), (17, 7),
                 (15, 11), (16, 11), (15, 12), (16, 12), (15, 13), (16, 13)):
        layer.set(x, y + bob, HOLE)
    knife(layer, bob)
    stamp_layer(c, layer, lean)


# --- crocheting --------------------------------------------------------------------

YARN = (236, 120, 160, 255)
YARN_DARK = (190, 80, 120, 255)
SCARF_A = (120, 190, 220, 255)
SCARF_B = (250, 230, 140, 255)
HOOK = (200, 205, 215, 255)


def draw_crochet(frame):
    """Hook in his right claw, yarn ball on the floor, scarf growing from his left claw."""
    def work(c, bob):
        layer = Canvas()
        for x, y in ((25, 24), (26, 24), (27, 24), (24, 25), (25, 25), (26, 25), (27, 25), (28, 25),
                     (24, 26), (25, 26), (26, 26), (27, 26), (28, 26), (25, 27), (26, 27), (27, 27)):
            layer.set(x, y, YARN if (x + y) % 3 else YARN_DARK)            # yarn ball
        for y in range(4 + bob, 9 + bob):
            layer.set(27 + (y + frame) % 2 * 0, y, HOOK)                  # hook
        layer.set(26 + frame % 2, 3 + bob, HOOK)
        for y in range(11 + bob, 13 + bob + 2 * frame):                   # scarf grows each frame
            for x in (3, 4, 5):
                layer.set(x, y, SCARF_A if (y // 2) % 2 else SCARF_B)
        stamp_layer(c, layer, 0)
        for y in range(10 + bob, 24, 2):                                  # loose thread ball -> hook
            c.set(27 - (y - 10) // 7, y, YARN)
    return draw_crab(bob=frame % 2, claw=CLAW_HALF, claw_lift=frame % 2, details=work)


TUB = (130, 85, 50, 255)
TUB_DARK = (95, 60, 35, 255)
WATER = (90, 160, 220, 255)
APPLE = (210, 35, 40, 255)
BOOK_COVER = (120, 35, 45, 255)
BOOK_SPINE = (80, 20, 30, 255)
PAGE = (244, 236, 214, 255)
BOOK_INK = (150, 140, 125, 255)
TORCH = (70, 70, 80, 255)
TORCH_LENS = (255, 240, 150, 255)
TORCH_BEAM = (255, 248, 200, 255)
EYE_LIT = (255, 232, 150, 255)


def draw_apples(frame):
    """Bobbing for apples: dips into a tub (0-2), pops up with an apple (3)."""
    def tub(c, bob):
        layer = Canvas()
        fill(layer, 6, 23, 25, 28, TUB)
        for x in range(6, 26, 4):
            fill(layer, x, 23, x, 28, TUB_DARK)
        fill(layer, 7, 22, 24, 22, WATER)
        if frame == 2:                                                   # splash
            for x, y in ((8, 19), (11, 18), (20, 18), (23, 19), (15, 17)):
                layer.set(x, y, WATER)
        if frame == 3:
            for x, y in ((14, 19), (15, 19), (16, 19), (17, 19), (14, 20), (15, 20), (16, 20), (17, 20), (15, 21), (16, 21)):
                layer.set(x, y, APPLE)
            layer.set(16, 18, STEM)
        stamp_layer(c, layer, 0)
    return draw_crab(bob=(0, 3, 6, 0)[frame], eyes="happy" if frame == 3 else "closed" if frame else "open",
                     claw=CLAW_HALF, claw_lift=2 if frame == 3 else 0, details=tub)


def open_book(c, y0, flip=False):
    """Open book held up in front of him, little claws gripping the corners."""
    layer = Canvas()
    fill(layer, 8, y0, 23, y0 + 7, BOOK_COVER)
    fill(layer, 9, y0 + 1, 14, y0 + 6, PAGE)
    fill(layer, 17, y0 + 1, 22, y0 + 6, PAGE)
    fill(layer, 15, y0, 16, y0 + 7, BOOK_SPINE)
    if flip:
        fill(layer, 17, y0 - 3, 21, y0, PAGE)                        # page swinging over
    stamp_layer(c, layer, 0)
    for y in range(y0 + 2, y0 + 6, 2):                               # lines of text
        for x in (10, 11, 12, 13, 18, 19, 20, 21):
            c.set(x, y, BOOK_INK)
    for x, y in ((7, y0 + 1), (7, y0 + 2), (24, y0 + 1), (24, y0 + 2)):
        c.set(x, y, SHELL)


def chin_torch(c, bob):
    """Flashlight held upright under his face, beam fanning up between the eye stalks."""
    layer = Canvas()
    fill(layer, 15, 16 + bob, 16, 20 + bob, TORCH)
    stamp_layer(c, layer, 0)
    c.set(15, 15 + bob, TORCH_LENS)
    c.set(16, 15 + bob, TORCH_LENS)
    for y, half in ((14, 1), (13, 1), (12, 2), (11, 2)):
        for x in range(16 - half, 16 + half):
            if c.px[y + bob][x] in (CLEAR, OUTLINE):
                c.set(x, y + bob, TORCH_BEAM)
    for y in range(7 + bob, 12 + bob):                               # eyes lit from below
        for x in range(10, 22):
            if c.px[y][x] == EYE_WHITE:
                c.px[y][x] = EYE_LIT


def draw_story(frame):
    """Spooky story: reads (0), turns a page (1), then flashlight under the chin (2, 3)."""
    if frame < 2:
        return draw_crab(bob=frame, eyes="down", claws=False,
                         details=lambda c, bob: open_book(c, 15 + bob, flip=frame == 1))
    return draw_crab(eyes="open" if frame == 2 else "confused", mouth="wavy" if frame == 2 else "grit",
                     claws=False, details=lambda c, bob: (open_book(c, 22), chin_torch(c, bob)))


HALLOWEEN_LOOKS = {"witch": witch_hat, "slasher": slasher, "hockey": hockey, "screamer": screamer}


# --- Elvis outfits (worn while an Elvis voice is picked) -----------------------------

HAIR = (22, 18, 30, 255)
HAIR_SHINE = (78, 80, 120, 255)
LAME = body_colors((214, 170, 52, 255), (246, 212, 96, 255), (168, 124, 30, 255))  # gold lamé, 1957
LAME_GLINT = (255, 246, 190, 255)
SHIRT = (30, 26, 34, 255)
JUMP = body_colors((236, 236, 230, 255), (252, 252, 248, 255), (196, 196, 190, 255))  # white jumpsuit, 70s
STUDS = ((228, 186, 60, 255), (220, 50, 60, 255), (70, 120, 230, 255))
BELT = (222, 176, 52, 255)
BELT_DARK = (160, 118, 30, 255)
SHADES = (70, 46, 30, 255)


def pompadour(layer, bob):
    """Tall black quiff swept up over his eyes, curling forward at the front."""
    rows = {0: (18, 22), 1: (15, 23), 2: (13, 23), 3: (11, 22), 4: (10, 21), 5: (10, 20), 6: (10, 11)}
    for y, (x0, x1) in rows.items():
        for x in range(x0, x1 + 1):
            layer.set(x, y + bob, HAIR)
    for x, y in ((23, 3), (24, 4), (24, 5)):                       # the curl dropping over the front
        layer.set(x, y + bob, HAIR)
    for x, y in ((17, 1), (18, 1), (15, 2), (16, 2), (13, 3), (14, 3)):
        layer.set(x, y + bob, HAIR_SHINE)                          # brylcreem shine along the swoop


def elvis57(c, bob, lean):
    """1957: gold lamé suit over a dark shirt, black pompadour."""
    recolor_body(c, LAME, 15 + bob)
    cy = 19 + bob
    for x, y in ((15, cy - 4), (16, cy - 4), (15, cy - 3), (16, cy - 3)):   # dark shirt under the lapels
        if 0 <= x + lean < SIZE and c.px[y][x + lean] in LAME.values():
            c.px[y][x + lean] = SHIRT
    for x, y in ((9, cy - 1), (21, cy), (12, cy + 3), (19, cy - 3), (24, cy + 1)):  # lamé glints
        if 0 <= x + lean < SIZE and c.px[y][x + lean] in LAME.values():
            c.px[y][x + lean] = LAME_GLINT
    layer = Canvas()
    pompadour(layer, bob)
    stamp_layer(c, layer, lean)


def elvis70s(c, bob, lean):
    """70s: white jumpsuit, popped collar, rhinestones, big gold belt, gold aviators."""
    recolor_body(c, JUMP, 15 + bob)
    cy = 19 + bob
    for i, (x, y) in enumerate(((9, cy - 1), (12, cy - 2), (19, cy - 2), (22, cy - 1), (8, cy + 1), (23, cy + 1))):
        if 0 <= x + lean < SIZE and c.px[y][x + lean] in JUMP.values():
            c.px[y][x + lean] = STUDS[i % 3]                       # rhinestones
    layer = Canvas()
    for x in (8, 9, 22, 23):                                       # high popped collar, both sides
        for y in range(cy - 7, cy - 3):
            layer.set(x, y, JUMP[SHELL_LIGHT])
    for x in range(8, 24):                                         # belt
        layer.set(x, cy + 3, BELT)
    for x in range(13, 19):                                        # big buckle
        layer.set(x, cy + 2, BELT)
        layer.set(x, cy + 4, BELT)
    pompadour(layer, bob)
    stamp_layer(c, layer, lean)
    def put(x, y, color):  # straight onto the pixels: c.set would add the lean twice
        if 0 <= x + lean < SIZE:
            c.px[y][x + lean] = color
    for x in range(14, 18):
        put(x, cy + 3, BELT_DARK)                                  # buckle plate
    for x0 in (11, 18):                                            # aviators over his eyes
        for x in range(x0, x0 + 3):
            put(x, 8 + bob, BELT)
            put(x, 9 + bob, SHADES)
            put(x, 10 + bob, SHADES)
    for x in range(14, 18):
        put(x, 9 + bob, BELT)                                      # bridge
    put(12, 9 + bob, (150, 110, 80, 255))                          # lens glint


def draw_dance(frame):
    """The swivel: hips rock side to side over planted feet, legs shaking, claw jabbing up,
    lip curled."""
    lean = (-3, 0, 3, 0)[frame]
    return draw_crab(bob=frame % 2, legs=frame % 2, lean=lean, claw=CLAW_HALF if frame % 2 else CLAW_OPEN,
                     claw_lift=3 if frame % 2 == 0 else 1, eyes="happy" if frame == 3 else "open", mouth="curl")


OUTFIT_LOOKS = {"elvis57": elvis57, "elvis70s": elvis70s}
OUTFIT_STATES = ("walk", "idle", "happy", "confused", "pull", "peek", "crochet")


HALLOWEEN_HATTED = ("walk", "idle", "happy", "confused", "pull", "peek", "crochet")


def build_frames():
    return {
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
        # Peering down at you while you type: eyes down, claws up on the edge.
        "peek": [
            draw_crab(eyes="down", mouth="wavy", claw=CLAW_HALF, claw_lift=2),
            draw_crab(eyes="down", mouth="wavy", claw=CLAW_HALF, claw_lift=1, bob=1),
        ],
        # Sizing up the machine, then downloading a brain to run on it.
        # Crocheting a scarf (Heather taught him).
        "crochet": [draw_crochet(f) for f in range(4)],
        "inspect": [draw_inspect(f) for f in range(4)],
        "install": [draw_install(f) for f in range(4)],
        # Gaming scenes, facing right (the app mirrors them to face left).
        "game_modern": [draw_gamer("modern", f) for f in range(4)],
        "game_retro": [draw_gamer("retro", f) for f in range(4)],
    }


FRAMES = build_frames()


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

    # Halloween: the ghost is shared; every other state is baked once per daily look.
    global HAT
    shutil.rmtree(ASSETS / "halloween", ignore_errors=True)
    (ASSETS / "halloween").mkdir()
    for i, frame in enumerate(draw_ghost(f) for f in range(4)):
        frame.save(ASSETS / "halloween" / f"ghost_{i}.png")
    preview_rows = [[f for fs in FRAMES.values() for f in fs]]
    for look, hat in HALLOWEEN_LOOKS.items():
        HAT = hat
        frames = {k: v for k, v in build_frames().items() if k in HALLOWEEN_HATTED}
        frames |= {"carve": [draw_carve(f) for f in range(4)], "boo": [draw_boo(f) for f in range(4)],
                   "apples": [draw_apples(f) for f in range(4)], "story": [draw_story(f) for f in range(4)]}
        HAT = None
        (ASSETS / "halloween" / look).mkdir()
        for name, imgs in frames.items():
            for i, frame in enumerate(imgs):
                frame.save(ASSETS / "halloween" / look / f"{name}_{i}.png")
        preview_rows.append([f for fs in frames.values() for f in fs])
    preview_rows[1] += [draw_ghost(f) for f in range(4)]

    # Elvis outfits: worn while an Elvis voice is picked (assets/outfit/<look>/), with his dance.
    shutil.rmtree(ASSETS / "outfit", ignore_errors=True)
    for look, hat in OUTFIT_LOOKS.items():
        HAT = hat
        frames = {k: v for k, v in build_frames().items() if k in OUTFIT_STATES}
        frames["dance"] = [draw_dance(f) for f in range(4)]
        HAT = None
        (ASSETS / "outfit" / look).mkdir(parents=True)
        for name, imgs in frames.items():
            for i, frame in enumerate(imgs):
                frame.save(ASSETS / "outfit" / look / f"{name}_{i}.png")
        preview_rows.append([f for fs in frames.values() for f in fs])

    # Preview sheet (8x scale): row 0 = everyday frames, one row per Halloween look, then outfits.
    width = max(len(r) for r in preview_rows)
    sheet = Image.new("RGBA", (SIZE * width, SIZE * len(preview_rows)), (200, 220, 235, 255))
    for row, frames in enumerate(preview_rows):
        for i, frame in enumerate(frames):
            sheet.alpha_composite(frame, (i * SIZE, row * SIZE))
    sheet.resize((sheet.width * 8, sheet.height * 8), Image.NEAREST).save(ASSETS / "preview.png")
    print(f"Wrote {len(preview_rows[0])} frames + {len(HALLOWEEN_LOOKS)} Halloween looks"
          f" + {len(OUTFIT_LOOKS)} outfits to {ASSETS}")

if __name__ == "__main__":
    main()
