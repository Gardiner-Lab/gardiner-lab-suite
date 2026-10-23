# Trellis Tools' icon: a DNA double helix as a trellis, with a vine climbing it.
# python docs/icon/make_icon.py writes trellis.svg (and a preview page) next to itself;
# copy trellis.svg to portal/pages/, which serves it at /account/trellis.svg.
"""Trellis Tools' icon: a trellis that is a DNA double helix - two wooden strands, base pairs as its
cross-slats - with a vine climbing it. Writes trellis.svg and preview.html."""
import math
import re
import os

HERE = os.path.dirname(os.path.abspath(__file__))
TOP, BOTTOM, CX, AMP = 9.5, 55.5, 32.0, 15.0
TURNS = 1.5                       # how many twists, bottom to top


def strand_x(y, phase):
    t = (BOTTOM - y) / (BOTTOM - TOP) * TURNS * 2 * math.pi
    return CX + AMP * math.sin(t + phase)


def depth(y, phase):
    """In front (+1) or behind (-1): the cosine of the twist."""
    t = (BOTTOM - y) / (BOTTOM - TOP) * TURNS * 2 * math.pi
    return math.cos(t + phase)


def strand_segments(phase):
    """The strand as runs in front and runs behind, so the strands cross over and under."""
    runs, cur, front = [], [], None
    y = BOTTOM
    while y >= TOP - 0.01:
        f = depth(y, phase) >= 0
        pt = (strand_x(y, phase), y)
        if front is None:
            front = f
        if f != front:
            cur.append(pt)
            runs.append((front, cur))
            cur, front = [pt], f
        else:
            cur.append(pt)
        y -= 0.5
    runs.append((front, cur))
    return runs


def path(points):
    return 'M' + 'L'.join(f'{x:.2f} {y:.2f}' for x, y in points)


back, fore = [], []
# Starting (and ending) at their widest: the trellis stands on a wide base.
for phase in (math.pi / 2, 3 * math.pi / 2):
    for front, pts in strand_segments(phase):
        (fore if front else back).append(path(pts))

# Base pairs: the slats, where the strands are well apart.
rungs = []
n = 9
for i in range(n):
    y = BOTTOM - 2.5 - i * (BOTTOM - TOP - 5) / (n - 1)
    a, b = strand_x(y, math.pi / 2), strand_x(y, 3 * math.pi / 2)
    if abs(a - b) > 6:
        rungs.append((min(a, b) + 1.6, max(a, b) - 1.6, y, i % 2))

# The vine: up the middle, winding the other way, with leaves on alternate sides.
vine = []
y = 57.5
while y >= 13:
    t = (57.5 - y) / 44.5 * 2.2 * math.pi
    vine.append((CX + 6.0 * math.sin(-t + 0.6), y))
    y -= 0.5
LEAF = 'M0 0C3-4.4 9.4-5 12.6 0C9.4 5 3 4.4 0 0Z'
leaves = []
for k, frac in enumerate((0.12, 0.27, 0.42, 0.57, 0.72, 0.86)):
    x, yy = vine[int(frac * (len(vine) - 1))]
    side = -1 if k % 2 == 0 else 1
    angle = (200 + k * 4) if side < 0 else (-25 - k * 3)
    scale = 1.0 - k * 0.06
    leaves.append(f'<g transform="translate({x:.2f} {yy:.2f}) rotate({angle}) scale({scale:.2f})">'
                  f'<path d="{LEAF}" fill="url(#leaf)"/><path d="M1 0H10.5" stroke="#14532d" stroke-width=".7" '
                  f'stroke-linecap="round" opacity=".5"/></g>')
fx, fy = vine[-1]

# Two colours, flat: brown for the trellis, green for the plant. Where something passes in
# front, a thin gap is cut in what is behind it (masks), so the over-and-under still reads.
BROWN, GREEN, GAP = '#8b5a2b', '#2f8f46', 1.1
leaf_tf = re.findall(r'transform="([^"]+)"', ''.join(leaves))
tendril = f'M{fx:.2f} {fy:.2f}c-.6-2.4.9-4.6 3.1-4.6 1.9 0 2.9 1.6 2.2 3-.6 1.1-2.1 1.1-2.4.1'
FORE_W, VINE_W = 4.6, 3.0


def plant(colour, extra=0.0):
    """The vine, its leaves and its tendril; with extra, a little wider all round (for the gap)."""
    out = [f'<path d="{path(vine)}" fill="none" stroke="{colour}" stroke-width="{VINE_W + 2 * extra:.2f}" stroke-linecap="round"/>',
           f'<path d="{tendril}" fill="none" stroke="{colour}" stroke-width="{1.6 + 2 * extra:.2f}" stroke-linecap="round"/>']
    for tf in leaf_tf:
        out.append(f'<path transform="{tf}" d="{LEAF}" fill="{colour}"'
                   + (f' stroke="{colour}" stroke-width="{2 * extra:.2f}" stroke-linejoin="round"' if extra else '') + '/>')
    return ''.join(out)


fore_d = ''.join(fore)
veins = ''.join(f'<path transform="{tf}" d="M1.5 0H10" stroke="black" stroke-width=".9" stroke-linecap="round"/>' for tf in leaf_tf)
svg = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64" role="img" aria-label="Trellis Tools">
  <title>Trellis Tools</title>
  <defs>
    <!-- gaps: behind the front strands and the plant; behind the plant; the leaves' veins -->
    <mask id="behind-all" maskUnits="userSpaceOnUse" x="0" y="0" width="64" height="64">
      <rect width="64" height="64" fill="white"/>
      <path d="{fore_d}" fill="none" stroke="black" stroke-width="{FORE_W + 2 * GAP:.2f}" stroke-linecap="round"/>
      {plant('black', GAP)}
    </mask>
    <mask id="behind-plant" maskUnits="userSpaceOnUse" x="0" y="0" width="64" height="64">
      <rect width="64" height="64" fill="white"/>{plant('black', GAP)}
    </mask>
    <mask id="veins" maskUnits="userSpaceOnUse" x="0" y="0" width="64" height="64">
      <rect width="64" height="64" fill="white"/>{veins}
    </mask>
  </defs>
  <!-- the trellis, a double helix: strands behind and the base pairs as slats, then the strands in front -->
  <path mask="url(#behind-all)" d="{''.join(back)}" fill="none" stroke="{BROWN}" stroke-width="2.4" stroke-linecap="round"/>
  <g mask="url(#behind-plant)" stroke="{BROWN}" stroke-linecap="round" fill="none">
    {''.join(f'<path d="M{a:.2f} {y:.2f}H{b:.2f}" stroke-width="1.5"/>' for a, b, y, alt in rungs)}
  </g>
  <path mask="url(#behind-plant)" d="{fore_d}" fill="none" stroke="{BROWN}" stroke-width="{FORE_W}" stroke-linecap="round"/>
  <path d="M8 58.4h48" stroke="{BROWN}" stroke-width="3" stroke-linecap="round"/>
  <!-- the plant, climbing it, in front -->
  <g mask="url(#veins)">{plant(GREEN)}</g>
</svg>
"""
open(os.path.join(HERE, 'trellis.svg'), 'w', encoding='utf8').write(svg)
cells = ''.join(f'<div style="text-align:center"><img src="trellis.svg" width="{n}" height="{n}">'
                f'<div style="font-size:11px;color:#6b7280">{n}px</div></div>' for n in (256, 96, 48, 32, 16))
open(os.path.join(HERE, 'preview.html'), 'w', encoding='utf8').write(
    '<body style="margin:0;padding:20px;font-family:system-ui;background:#f8fafc;display:flex;gap:28px;align-items:flex-end">'
    + cells + '<div style="padding:10px 16px;background:#1f2937;border-radius:8px"><img src="trellis.svg" width="48"></div>'
    '<div style="display:flex;align-items:center;gap:10px;font-size:34px;font-weight:700;color:#111827">'
    '<img src="trellis.svg" width="46">Trellis Tools</div></body>')
print(f'{len(svg)} bytes')
