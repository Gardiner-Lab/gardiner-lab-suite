# The tools' icons, in the style of Trellis Tools' own (make_icon.py): two flat colours, brown and
# green, round strokes, depth by line weight, cut-out gaps and leaf veins.
# python docs/icon/make_tool_icons.py writes them to portal/pages/icons/, which the sign-in
# service serves at /account/icons/<name>.svg, and a preview page next to itself.
import math
import os

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, '..', '..', 'portal', 'pages', 'icons')
BROWN, GREEN = '#8b5a2b', '#2f8f46'
LEAF = 'M0 0C3-4.4 9.4-5 12.6 0C9.4 5 3 4.4 0 0Z'
VEIN = 'M1.5 0H10'


def leaf(tf):
    """A green leaf (its vein cut out by the icon's mask), and the vein for that mask."""
    return (f'<path transform="{tf}" d="{LEAF}" fill="{GREEN}"/>',
            f'<path transform="{tf}" d="{VEIN}" stroke="black" stroke-width=".9" stroke-linecap="round"/>')


def icon(name, title, body, veins='', width=64):
    """An icon 64 high, and 64 wide unless it is a long one (MoClo's row of parts)."""
    mask = (f'<defs><mask id="veins" maskUnits="userSpaceOnUse" x="0" y="0" width="{width}" height="64">'
            f'<rect width="{width}" height="64" fill="white"/>{veins}</mask></defs>') if veins else ''
    return name, (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} 64" role="img" aria-label="{title}">\n'
                  f'  <title>{title}</title>\n  {mask}\n  {body}\n</svg>\n')


def arc(cx, cy, r, a0, a1):
    """An arc from angle a0 to a1 (degrees, clockwise from 3 o'clock), and its end point and direction."""
    x0, y0 = cx + r * math.cos(math.radians(a0)), cy + r * math.sin(math.radians(a0))
    x1, y1 = cx + r * math.cos(math.radians(a1)), cy + r * math.sin(math.radians(a1))
    large = 1 if (a1 - a0) % 360 > 180 else 0
    return f'M{x0:.2f} {y0:.2f}A{r} {r} 0 {large} 1 {x1:.2f} {y1:.2f}', (x1, y1), math.radians(a1 + 90)


def head(x, y, angle, size=5.2):
    """An arrowhead at (x, y), pointing along angle (radians)."""
    pts = [(x + size * math.cos(angle), y + size * math.sin(angle)),
           (x + size * 0.75 * math.cos(angle + 2.2), y + size * 0.75 * math.sin(angle + 2.2)),
           (x + size * 0.75 * math.cos(angle - 2.2), y + size * 0.75 * math.sin(angle - 2.2))]
    return 'M' + 'L'.join(f'{px:.2f} {py:.2f}' for px, py in pts) + 'Z'


icons = []

# MoClo: three DNA parts, each a ladder of two strands, joined by their four-base overhangs (Golden
# Gate); a long icon, half as wide again as the others.
parts = []
for (t0, t1, b0, b1), colour in (((6, 35, 6, 29), BROWN), ((38, 63, 32, 57), GREEN), ((66, 90, 60, 90), BROWN)):
    rungs = ''.join(f'M{x:.1f} 23V41' for x in [max(t0, b0) + 2.2 + 3 * k for k in range(12)] if x < min(t1, b1) - 1.2)
    parts.append(f'<path d="M{t0 + 2} 20H{t1 - 2}M{b0 + 2} 44H{b1 - 2}" stroke="{colour}" stroke-width="4.6" stroke-linecap="round"/>'
                 f'<path d="{rungs}" stroke="{colour}" stroke-width="1.9" stroke-linecap="round"/>')
icons.append(icon('moclo', 'MoClo Library Tool', ''.join(parts), width=96))

# Plasmid Editor: a plasmid, a feature on it (green arrow), and a cut site.
ring = f'<circle cx="32" cy="33" r="18" fill="none" stroke="{BROWN}" stroke-width="4.2"/>'
d, (ex, ey), ang = arc(32, 33, 18, 190, 285)
feature = (f'<path d="{d}" fill="none" stroke="{GREEN}" stroke-width="7" stroke-linecap="butt"/>'
           f'<path d="{head(ex, ey, ang, 9)}" fill="{GREEN}"/>')
# The cut site on the left, away from where a Q's tail would be.
cx, cy = 32 + 18 * math.cos(math.radians(160)), 33 + 18 * math.sin(math.radians(160))
dx, dy = math.cos(math.radians(160)), math.sin(math.radians(160))
cut = f'<path d="M{cx - 6 * dx:.2f} {cy - 6 * dy:.2f}L{cx + 6 * dx:.2f} {cy + 6 * dy:.2f}" stroke="{BROWN}" stroke-width="2.4" stroke-linecap="round"/>'
icons.append(icon('editor', 'Plasmid Editor', ring + feature + cut))

# Lab Notebook: a notebook, its spine, a leaf on the cover.
lf, vn = leaf('translate(26.5 38) rotate(-40) scale(1.55)')
icons.append(icon('notebook', 'Lab Notebook',
                  f'<rect x="13" y="8" width="38" height="48" rx="4" fill="none" stroke="{BROWN}" stroke-width="4.2"/>'
                  f'<path d="M21 8V56" stroke="{BROWN}" stroke-width="2.4"/>'
                  f'<path d="M27 15H44M27 20H40" stroke="{BROWN}" stroke-width="1.6" stroke-linecap="round"/>'
                  f'<g mask="url(#veins)">{lf}</g>', vn))

# Seed Bank: a seed in the ground, sprouting.
l1, v1 = leaf('translate(32 24) rotate(205) scale(1.45)')
l2, v2 = leaf('translate(32 20) rotate(-30) scale(1.55)')
icons.append(icon('seeds', 'Seed Bank',
                  f'<path d="M10 55h44" stroke="{BROWN}" stroke-width="3" stroke-linecap="round"/>'
                  f'<ellipse cx="32" cy="48" rx="9" ry="5.6" transform="rotate(-12 32 48)" fill="{BROWN}"/>'
                  f'<path d="M32 44C30 37 34.5 30 32 20" fill="none" stroke="{GREEN}" stroke-width="3.2" stroke-linecap="round"/>'
                  f'<g mask="url(#veins)">{l1}{l2}</g>', v1 + v2))

# Lab Stocks: a tube, capped, with green in it.
icons.append(icon('stocks', 'Lab Stocks',
                  f'<path d="M26.5 31H37.5V46.5A5.5 5.5 0 0 1 26.5 46.5Z" fill="{GREEN}"/>'
                  f'<path d="M23.5 17V46.5A8.5 8.5 0 0 0 40.5 46.5V17" fill="none" stroke="{BROWN}" stroke-width="4.2" stroke-linecap="round"/>'
                  f'<rect x="20" y="8" width="24" height="9" rx="2.5" fill="{BROWN}"/>'
                  f'<path d="M30 24H34M30 28H32.5" stroke="{BROWN}" stroke-width="1.6" stroke-linecap="round"/>'))

# Booking: a calendar, ticked.
icons.append(icon('booking', 'Booking',
                  f'<rect x="10" y="13" width="44" height="43" rx="5" fill="none" stroke="{BROWN}" stroke-width="4.2"/>'
                  f'<path d="M10 25H54" stroke="{BROWN}" stroke-width="3"/>'
                  f'<path d="M22 8V17M42 8V17" stroke="{BROWN}" stroke-width="4.2" stroke-linecap="round"/>'
                  f'<path d="M21 39.5L29 47L44 32" fill="none" stroke="{GREEN}" stroke-width="5" stroke-linecap="round" stroke-linejoin="round"/>'))

# Dashboard: a key, a leaf in its bow.
lk, vk = leaf('translate(17.5 24.5) rotate(-35) scale(.85)')
icons.append(icon('dashboard', 'Dashboard',
                  f'<circle cx="22" cy="22" r="11" fill="none" stroke="{BROWN}" stroke-width="4.2"/>'
                  f'<path d="M30 30L52 52M41 41L46 36M47 47L51.5 42.5" stroke="{BROWN}" stroke-width="4.2" stroke-linecap="round"/>'
                  f'<g mask="url(#veins)">{lk}</g>', vk))

# Backups: an archive box, a green arrow coming round (restore).
d, (ex, ey), ang = arc(32, 39, 8.5, -60, 210)
icons.append(icon('backups', 'Backups',
                  f'<rect x="8" y="11" width="48" height="11" rx="3" fill="none" stroke="{BROWN}" stroke-width="4"/>'
                  f'<path d="M12 22V51A4 4 0 0 0 16 55H48A4 4 0 0 0 52 51V22" fill="none" stroke="{BROWN}" stroke-width="4" stroke-linejoin="round"/>'
                  f'<path d="{d}" fill="none" stroke="{GREEN}" stroke-width="3.6" stroke-linecap="round"/>'
                  f'<path d="{head(ex, ey, ang, 6)}" fill="{GREEN}"/>'))

os.makedirs(OUT, exist_ok=True)
for name, svg in icons:
    open(os.path.join(OUT, f'{name}.svg'), 'w', encoding='utf8').write(svg)
rel = os.path.relpath(OUT, HERE).replace(os.sep, '/')
cards = ''.join(f'<div style="text-align:center;width:150px"><img src="{rel}/{n}.svg" height="96"><div style="display:flex;gap:10px;justify-content:center;margin:6px 0">'
                f'<img src="{rel}/{n}.svg" height="32"><img src="{rel}/{n}.svg" height="16"></div>'
                f'<div style="font-size:13px;color:#374151">{svg.split("<title>")[1].split("</title>")[0]}</div></div>' for n, svg in icons)
open(os.path.join(HERE, 'tool_icons.html'), 'w', encoding='utf8').write(
    '<body style="margin:0;padding:18px;font-family:system-ui;background:#f8fafc">'
    f'<div style="display:flex;gap:10px;align-items:center;margin-bottom:14px;font-size:24px;font-weight:700"><img src="{rel}/../trellis.svg" width="40">Trellis Tools</div>'
    f'<div style="display:flex;flex-wrap:wrap;gap:16px">{cards}</div></body>')
print(len(icons), 'icons written to', os.path.normpath(OUT))
