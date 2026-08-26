'''
Generate content/static/trivia/artwork.css from the comic artwork in
content/static/trivia/assets/.

The trivia screens draw live HTML text on top of hand-drawn comic frames
(speech bubbles, starbursts).  Every frame has its own idiosyncratic
interior: the usable area of category-0 is centred at 57% of its height,
category-4 at 43%.  Hand-tuning inset percentages per frame is how the
stylesheet previously grew six competing definitions of .category-label.

So measure instead.  For each frame this finds the largest rectangle that
fits inside the drawn outline and emits it as CSS custom properties next to
the background-image that it describes, which keeps the artwork and its
metrics in one place.  trivia.css consumes the properties and never needs
to know which frame it is painting.

Regenerate after changing any artwork:

    python3 scripts/trivia_artwork.py

Requires Pillow.  The generated file is committed, so an ordinary build
does not need it.
'''

from collections import deque
import os
import sys

# Anything darker than this in *every* channel is the navy comic linework.
# A plain luminance test does not work here: the interior of category-5 is a
# saturated red that is darker than the halftone dots on category-0.  The
# outline is the only thing with no bright channel at all.
INK_MAX = 100

# Ink blobs smaller than this are halftone dots and speed lines, not the
# frame outline, and must not block the flood fill.
MIN_BLOB = 250

# Below this the measured interior is too small to hold text, which means
# the frame was not detected properly rather than that the art is tight.
MIN_AREA = 0.04

# How far a pixel must sit from the flat page colour to count as drawing,
# summed over the three channels.  The art is rendered on cream, and the
# name plates waste about a fifth of their height on it.
TRIM_TOL = 26

ASSETS = os.path.join('content', 'static', 'trivia', 'assets')
TARGET = os.path.join('content', 'static', 'trivia', 'artwork.css')

# Artwork that holds live text.  The measured safe area is emitted for these.
#
# `trim` crops the flat page margin the art is drawn on.  The category
# tiles keep theirs: they butt together into one sheet, and only the
# untrimmed squares share an aspect ratio, so only they tile without
# ragged rows.  Their margin is the page colour, so it reads as one field
# rather than as six panels.
FRAMES = [
    ('category-0.webp', '.category-label.category-0', False),
    ('category-1.webp', '.category-label.category-1', False),
    ('category-2.webp', '.category-label.category-2', False),
    ('category-3.webp', '.category-label.category-3', False),
    ('category-4.webp', '.category-label.category-4', False),
    ('category-5.webp', '.category-label.category-5', False),
    ('name-nora.webp', '.person.player-nora', True),
    ('name-claire.webp', '.person.player-claire', True),
    ('name-cori.webp', '.person.player-cori', True),
    ('name-ethan.webp', '.person.player-ethan', True),
]

# Artwork that is the whole message.  These carry no text, so they only need
# the image; app.js gives the buttons an aria-label instead.
ICONS = [
    ('correct-burst.webp', '.correct, .result-correct', True),
    ('incorrect-burst.webp', '.incorrect, .result-incorrect', True),
    ('new-game.webp', '.new-game', True),
    ('next-turn.webp', '.next-turn', True),
]

# The page colour is taken from these, because they are the tiles that
# meet edge to edge: any mismatch shows up there first.
PAGE_SOURCE = 'category-0.webp'

# Line art laid over something else rather than under text.  Transparent
# where the thing underneath should show through, so it has no page colour
# and no safe area -- just a URL.
OVERLAYS = [
    ('pie-wheel.webp', '.pie', '--pie-frame'),
]

# The scoring wheel is filled with the colour of the category it stands
# for, read off the tiles so the two screens agree.
CATEGORY_FILLS = [
    'category-0.webp', 'category-1.webp', 'category-2.webp',
    'category-3.webp', 'category-4.webp', 'category-5.webp',
]

# A pixel counts as the burst's fill if its channels spread at least this
# far apart.  The cream page and the navy outline are both near-neutral;
# the fills are all strongly saturated.
FILL_CHROMA = 60


def _ink(image):
    '''Boolean grid of outline pixels, plus the image dimensions.'''
    width, height = image.size
    pixel = image.load()
    grid = [[max(pixel[x, y]) < INK_MAX for x in range(width)]
            for y in range(height)]
    return grid, width, height


def _blobs(grid, width, height):
    '''Yield each connected run of ink as a list of coordinates.'''
    seen = [[False] * width for _ in range(height)]
    for y in range(height):
        for x in range(width):
            if not grid[y][x] or seen[y][x]:
                continue
            blob, queue = [], deque([(x, y)])
            seen[y][x] = True
            while queue:
                cx, cy = queue.popleft()
                blob.append((cx, cy))
                for nx, ny in ((cx + 1, cy), (cx - 1, cy),
                               (cx, cy + 1), (cx, cy - 1)):
                    if (0 <= nx < width and 0 <= ny < height
                            and grid[ny][nx] and not seen[ny][nx]):
                        seen[ny][nx] = True
                        queue.append((nx, ny))
            yield blob


def _despeckle(grid, width, height):
    '''Erase halftone dots so they do not wall off the interior.'''
    for blob in list(_blobs(grid, width, height)):
        if len(blob) < MIN_BLOB:
            for x, y in blob:
                grid[y][x] = False
    return grid


def _interior(grid, width, height):
    '''Flood out from the centre, blocked by ink.  None if there is no frame.'''
    cx, cy = width // 2, height // 2
    if grid[cy][cx]:
        return None
    seen = [[False] * width for _ in range(height)]
    seen[cy][cx] = True
    queue, filled = deque([(cx, cy)]), 1
    while queue:
        x, y = queue.popleft()
        for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
            if (0 <= nx < width and 0 <= ny < height
                    and not seen[ny][nx] and not grid[ny][nx]):
                seen[ny][nx] = True
                filled += 1
                queue.append((nx, ny))
    # A fill that covers most of the canvas escaped through a gap in the
    # outline, so the result describes the page, not the frame.
    if filled > 0.85 * width * height:
        return None
    return seen


def _largest_rect(mask, width, height):
    '''Largest axis-aligned rectangle inside the mask, as (x, y, w, h).'''
    heights = [0] * width
    best = (0, 0, 0, 0, 0)
    for y in range(height):
        for x in range(width):
            heights[x] = heights[x] + 1 if mask[y][x] else 0
        stack = []
        for x in range(width + 1):
            column = heights[x] if x < width else 0
            start = x
            while stack and stack[-1][1] >= column:
                left, tall = stack.pop()
                area = tall * (x - left)
                if area > best[0]:
                    best = (area, left, y - tall + 1, x - left, tall)
                start = left
            stack.append((start, column))
    return best[1:]


def _content_box(image):
    '''Bounding box of the drawing, as fractions of the image.

    Every asset is drawn on a flat cream page.  Left in, that margin shows
    up as a pale square floating on the page background, and on the name
    plates it eats a fifth of the height.  Rather than cutting new files
    and keeping them in sync, measure the margin here and let CSS zoom
    past it.
    '''
    width, height = image.size
    pixel = image.load()
    corners = [pixel[0, 0], pixel[width - 1, 0],
               pixel[0, height - 1], pixel[width - 1, height - 1]]
    page = tuple(sorted(c[i] for c in corners)[1] for i in range(3))

    x0, y0, x1, y1 = width, height, 0, 0
    for y in range(height):
        for x in range(width):
            r, g, b = pixel[x, y]
            if (abs(r - page[0]) + abs(g - page[1])
                    + abs(b - page[2])) > TRIM_TOL:
                x0, y0 = min(x0, x), min(y0, y)
                x1, y1 = max(x1, x), max(y1, y)
    if x1 < x0:
        return 0.0, 0.0, 1.0, 1.0
    return (x0 / width, y0 / height,
            (x1 - x0 + 1) / width, (y1 - y0 + 1) / height)


def page_color(path):
    '''The flat colour the art is drawn on, read from its corners.'''
    from PIL import Image

    with Image.open(path) as opened:
        image = opened.convert('RGB')
        width, height = image.size
        pixel = image.load()
        corners = [pixel[0, 0], pixel[width - 1, 0],
                   pixel[0, height - 1], pixel[width - 1, height - 1]]
    return tuple(sorted(c[i] for c in corners)[1] for i in range(3))


def fill_color(path):
    '''The dominant saturated colour of a tile: its burst fill.

    Taken as the most common colour among saturated pixels, quantised so
    that the halftone dots stippled over the fill land in the same bucket
    as the flat area they sit on.
    '''
    from PIL import Image

    with Image.open(path) as opened:
        image = opened.convert('RGB')
        width, height = image.size
        pixel = image.load()

    counts = {}
    for y in range(0, height, 2):
        for x in range(0, width, 2):
            r, g, b = pixel[x, y]
            if max(r, g, b) - min(r, g, b) < FILL_CHROMA:
                continue
            key = (r // 16, g // 16, b // 16)
            entry = counts.setdefault(key, [0, 0, 0, 0])
            entry[0] += 1
            entry[1] += r
            entry[2] += g
            entry[3] += b

    if not counts:
        raise ValueError('{}: no saturated fill found'.format(path))
    best = max(counts.values(), key=lambda e: e[0])
    return (best[1] // best[0], best[2] // best[0], best[3] // best[0])


def _zoom(offset, extent):
    '''background-position that crops `offset`..`offset+extent` to the box.

    With background-size set to 100/extent, the drawn image is larger than
    the element, and a percentage position aligns that fraction of the
    image with the same fraction of the element.  Solving for the position
    that puts the content flush gives offset / (1 - extent); a full-width
    axis has nothing to slide, so it centres.
    '''
    if extent >= 0.999:
        return 50.0
    return offset / (1.0 - extent) * 100.0


def safe_area(path, trim=True):
    '''Measure a frame: its content box and the insets to its interior.'''
    from PIL import Image

    with Image.open(path) as opened:
        image = opened.convert('RGB')
        width, height = image.size
        content = _content_box(image) if trim else (0.0, 0.0, 1.0, 1.0)
        grid, width, height = _ink(image)

    mask = _interior(_despeckle(grid, width, height), width, height)
    if mask is None:
        raise ValueError('{}: no enclosed interior found'.format(path))

    x, y, w, h = _largest_rect(mask, width, height)
    if (w * h) < MIN_AREA * width * height:
        raise ValueError('{}: interior is only {:.1%} of the frame'.format(
            path, (w * h) / (width * height)))

    cx, cy, cw, ch = content

    # Insets are consumed by CSS against the element, which now shows the
    # content box rather than the whole image, so restate them in its terms.
    left = (x / width - cx) / cw
    top = (y / height - cy) / ch
    right = 1.0 - ((x + w) / width - cx) / cw
    bottom = 1.0 - ((y + h) / height - cy) / ch

    return {
        'top': max(0.0, top) * 100,
        'right': max(0.0, right) * 100,
        'bottom': max(0.0, bottom) * 100,
        'left': max(0.0, left) * 100,
        'ratio': (cw * width) / (ch * height),
        'size': (100.0 / cw, 100.0 / ch),
        'pos': (_zoom(cx, cw), _zoom(cy, ch)),
    }


def icon_box(path, trim=True):
    '''The trim for artwork that carries no text.'''
    from PIL import Image

    with Image.open(path) as opened:
        image = opened.convert('RGB')
        width, height = image.size
        cx, cy, cw, ch = (_content_box(image) if trim
                          else (0.0, 0.0, 1.0, 1.0))

    return {
        'ratio': (cw * width) / (ch * height),
        'size': (100.0 / cw, 100.0 / ch),
        'pos': (_zoom(cx, cw), _zoom(cy, ch)),
    }


def generate(assets=ASSETS):
    '''Build the stylesheet text.'''
    page = page_color(os.path.join(assets, PAGE_SOURCE))
    lines = [
        '/* Generated by scripts/trivia_artwork.py -- do not edit by hand. */',
        '/* Insets are measured from the artwork; see that script for why. */',
        '',
        ':root {',
        '  /* The flat colour {} is drawn on, so the page and the'.format(
            PAGE_SOURCE),
        '     margins of the tiles are one continuous field. */',
        '  --page: rgb({}, {}, {});'.format(*page),
    ]
    for index, tile in enumerate(CATEGORY_FILLS):
        lines.append('  --cat-{}: rgb({}, {}, {});'.format(
            index, *fill_color(os.path.join(assets, tile))))
    lines += ['}', '']

    def block(selector, name, m, safe=None):
        lines.append('{} {{'.format(selector))
        lines.append('  --frame: url("assets/{}");'.format(name))
        lines.append('  --frame-ratio: {:.4f};'.format(m['ratio']))
        lines.append('  --frame-size: {:.2f}% {:.2f}%;'.format(*m['size']))
        lines.append('  --frame-pos: {:.2f}% {:.2f}%;'.format(*m['pos']))
        if safe:
            for edge in ('top', 'right', 'bottom', 'left'):
                lines.append('  --safe-{}: {:.1f}%;'.format(edge, m[edge]))
            # Unitless width of the interior, for sizing type against it.
            # A frame with a narrow interior has to set smaller text, and
            # scaling the font by this keeps the same number of characters
            # on a line whichever frame it is.
            lines.append('  --safe-w: {:.3f};'.format(
                (100.0 - m['left'] - m['right']) / 100.0))
        lines.append('}')
        lines.append('')

    for name, selector, trim in FRAMES:
        block(selector, name,
              safe_area(os.path.join(assets, name), trim), safe=True)

    for name, selector, trim in ICONS:
        block(selector, name, icon_box(os.path.join(assets, name), trim))

    for name, selector, prop in OVERLAYS:
        lines.append('{} {{'.format(selector))
        lines.append('  {}: url("assets/{}");'.format(prop, name))
        lines.append('}')
        lines.append('')

    return '\n'.join(lines)


def main():
    css = generate()
    with open(TARGET, 'w') as handle:
        handle.write(css)
    print('wrote {} ({} frames, {} icons)'.format(
        TARGET, len(FRAMES), len(ICONS)))
    return 0


if __name__ == '__main__':
    sys.exit(main())
