'''
Harmonise the flat page colour every trivia asset is drawn on.

The artwork was generated in batches, and the batches disagree about the
cream they sit on: the category tiles are rgb(254,244,220) but the name
plates are around rgb(253,242,209) and next-turn is rgb(253,245,228).  Up
to 12 levels apart in the blue channel.

That does not matter while each image floats in its own padded box, but
once the page is painted the same colour as the art -- so the category
tiles can meet edge to edge as one sheet -- every asset that disagrees
draws a faint rectangle around itself.

This rewrites the assets in place so they all share one page colour, taken
from the category tiles because those are the ones that tile.  The
correction is weighted by how close a pixel already is to that asset's own
page colour, so anti-aliased pixels along the linework are carried with it
instead of leaving a halo.

    python3 scripts/trivia_normalize_art.py          # report only
    python3 scripts/trivia_normalize_art.py --write  # rewrite in place

The assets are in git; `git checkout content/static/trivia/assets/` undoes
this.  Re-run scripts/trivia_artwork.py afterwards.
'''

import importlib.util
import os
import sys

MODULE = importlib.util.spec_from_file_location(
    'trivia_artwork', os.path.join(os.path.dirname(__file__),
                                   'trivia_artwork.py'))
artwork = importlib.util.module_from_spec(MODULE)
MODULE.loader.exec_module(artwork)

# Beyond this distance from the asset's own page colour a pixel is drawing
# and is left alone.  Twice the trim tolerance, so the correction fades out
# across the anti-aliased boundary rather than stopping at a hard edge.
FALLOFF = artwork.TRIM_TOL * 2


def normalize(path, target, write=False):
    '''Shift one asset's page colour to `target`.  Returns pixels touched.'''
    from PIL import Image

    with Image.open(path) as opened:
        image = opened.convert('RGB')

    source = artwork.page_color(path)
    if source == target:
        return 0

    shift = [target[i] - source[i] for i in range(3)]
    pixels = image.load()
    width, height = image.size
    touched = 0

    for y in range(height):
        for x in range(width):
            r, g, b = pixels[x, y]
            distance = (abs(r - source[0]) + abs(g - source[1])
                        + abs(b - source[2]))
            if distance >= FALLOFF:
                continue
            weight = 1.0 - distance / FALLOFF
            pixels[x, y] = (
                min(255, max(0, round(r + shift[0] * weight))),
                min(255, max(0, round(g + shift[1] * weight))),
                min(255, max(0, round(b + shift[2] * weight))),
            )
            touched += 1

    if write:
        # Lossy at high quality.  Lossless quadrupled these files (a 28KB
        # asset became 128KB) for artwork that is halftone gradients, not
        # flat panels.  q=95 leaves the backdrop exactly flat, which is
        # the whole point of the pass -- verified by re-reading the
        # corners afterwards.
        image.save(path, 'WEBP', quality=95, method=6)
    return touched


def main(argv):
    write = '--write' in argv
    assets = artwork.ASSETS
    target = artwork.page_color(os.path.join(assets, artwork.PAGE_SOURCE))
    print('page colour: rgb({}, {}, {})  (from {})'.format(
        *target, artwork.PAGE_SOURCE))

    total = 0
    for name, _, _ in artwork.FRAMES + artwork.ICONS:
        path = os.path.join(assets, name)
        before = os.path.getsize(path)
        source = artwork.page_color(path)
        touched = normalize(path, target, write)
        total += touched
        after = os.path.getsize(path)
        note = '' if touched else '  (already matches)'
        print('  {:<22} rgb{}  {:>7} px  {:>6} -> {:>6} bytes{}'.format(
            name, source, touched, before, after, note))

    if not write:
        print('\nreport only; pass --write to rewrite in place')
    else:
        print('\nrewrote {} pixels; re-run scripts/trivia_artwork.py'.format(
            total))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
