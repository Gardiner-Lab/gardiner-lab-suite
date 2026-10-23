# Small icons for inside the modules - on buttons, headings, lists - in Trellis Tools' style: brown
# and green, round lines (as make_icon.py and make_tool_icons.py). They stand in for emoji.
# python docs/icon/make_glyphs.py writes them to portal/pages/glyphs/; design/sync.sh copies them into
# each module (static/trellis/glyphs/). Shown with class="tt-glyph", about the height of a capital.
import os

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, '..', '..', 'portal', 'pages', 'glyphs')
B, G = '#8b5a2b', '#2f8f46'


def svg(title, body):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" role="img" aria-label="{title}">'
            f'<title>{title}</title><g fill="none" stroke-linecap="round" stroke-linejoin="round">{body}</g></svg>\n')


def page(mark, title):
    """A page with its corner turned, and a mark that says what kind of file it is."""
    return svg(title, f'<path d="M6 3h8l4 4v14H6z" stroke="{B}" stroke-width="1.8"/><path d="M14 3v4h4" stroke="{B}" stroke-width="1.5"/>{mark}')


GLYPHS = {
    # the Seed Bank's three records
    'line': svg('Line', f'<path d="M7 3c0 4.5 10 4.5 10 9s-10 4.5-10 9" stroke="{B}" stroke-width="2"/>'
                        f'<path d="M17 3c0 4.5-10 4.5-10 9s10 4.5 10 9" stroke="{G}" stroke-width="2"/>'
                        f'<path d="M9 6.6h6M9 17.4h6" stroke="{B}" stroke-width="1.4"/>'),
    'seedlot': svg('Seed lot', f'<ellipse cx="9" cy="15" rx="4.6" ry="3.4" transform="rotate(-25 9 15)" fill="{B}" stroke="none"/>'
                               f'<ellipse cx="16" cy="17" rx="4" ry="3" transform="rotate(20 16 17)" fill="{B}" stroke="none" opacity=".8"/>'
                               f'<path d="M10.5 12c.3-3 2-5 4.5-6" stroke="{G}" stroke-width="1.8"/>'
                               f'<path d="M15 6c1.6-.4 3 .2 3.6 1.4-1.6.6-3 .3-3.6-1.4z" fill="{G}" stroke="{G}" stroke-width="1"/>'),
    'plant': svg('Plant', f'<path d="M4 20.5h16" stroke="{B}" stroke-width="2"/>'
                          f'<path d="M12 20V10" stroke="{G}" stroke-width="2"/>'
                          f'<path d="M12 12C8.5 12.5 5.8 10.6 5.4 6.8 9 6.5 11.6 8.4 12 12z" fill="{G}" stroke="{G}" stroke-width="1"/>'
                          f'<path d="M12 10c.6-3.4 3.2-5.4 6.8-5.2-.2 3.6-2.6 5.6-6.8 5.2z" fill="{G}" stroke="{G}" stroke-width="1"/>'),
    'plasmid': svg('Plasmid', f'<circle cx="12" cy="12" r="7.5" stroke="{B}" stroke-width="2"/>'
                              f'<path d="M5.6 8.2A7.5 7.5 0 0 1 15.6 5.4" stroke="{G}" stroke-width="3.4"/>'
                              f'<path d="M14.4 3.4l2.6 2-3 1.8z" fill="{G}" stroke="{G}" stroke-width="1"/>'),
    # things done
    'label': svg('Label', f'<path d="M3.5 12.2 11.8 4h7.7v7.7l-8.3 8.3a1.4 1.4 0 0 1-2 0l-5.7-5.7a1.4 1.4 0 0 1 0-2z" stroke="{B}" stroke-width="1.9"/>'
                          f'<circle cx="15.6" cy="8" r="1.7" fill="{G}" stroke="none"/>'),
    'trash': svg('Delete', f'<path d="M4 6.5h16M9.5 6.5V4h5v2.5" stroke="{B}" stroke-width="1.8"/>'
                           f'<path d="M6 6.5l1 13.5h10l1-13.5" stroke="{B}" stroke-width="1.8"/>'
                           f'<path d="M10 10.5v6M14 10.5v6" stroke="{G}" stroke-width="1.7"/>'),
    'ratio': svg('Segregation test', f'<circle cx="5.5" cy="7" r="2.2" fill="{G}" stroke="none"/><circle cx="5.5" cy="13" r="2.2" fill="{G}" stroke="none"/>'
                                     f'<circle cx="5.5" cy="19" r="2.2" fill="{G}" stroke="none"/>'
                                     f'<circle cx="12" cy="10" r="1.1" fill="{B}" stroke="none"/><circle cx="12" cy="16" r="1.1" fill="{B}" stroke="none"/>'
                                     f'<circle cx="18.5" cy="13" r="2.4" stroke="{B}" stroke-width="1.8"/>'),
    'link': svg('Link', f'<path d="M10.5 13.5a4 4 0 0 0 5.7 0l3-3a4 4 0 0 0-5.7-5.7l-1.4 1.4" stroke="{B}" stroke-width="2"/>'
                        f'<path d="M13.5 10.5a4 4 0 0 0-5.7 0l-3 3a4 4 0 0 0 5.7 5.7l1.4-1.4" stroke="{G}" stroke-width="2"/>'),
    'notebook': svg('Notebook', f'<rect x="5" y="3" width="14.5" height="18" rx="2" stroke="{B}" stroke-width="1.8"/>'
                                f'<path d="M8.5 3v18" stroke="{B}" stroke-width="1.4"/>'
                                f'<path d="M11.5 15c.5-3.6 2.7-5.6 5.4-5.8-.2 3.2-2.3 5.6-5.4 5.8z" fill="{G}" stroke="{G}" stroke-width="1"/>'),
    'print': svg('Print', f'<path d="M7 9V3.5h10V9" stroke="{B}" stroke-width="1.8"/>'
                          f'<rect x="3.5" y="9" width="17" height="8" rx="2" stroke="{B}" stroke-width="1.8"/>'
                          f'<path d="M7.5 14.5h9V21h-9z" fill="#fff" stroke="{G}" stroke-width="1.8"/>'),
    'open': svg('Open', f'<path d="M3.5 18.5V6a1.5 1.5 0 0 1 1.5-1.5h4.2l2 2.2H18A1.5 1.5 0 0 1 19.5 8.2V10" stroke="{B}" stroke-width="1.8"/>'
                        f'<path d="M3.5 18.5 6.2 11h15.3l-2.8 7.5z" fill="{G}" stroke="{G}" stroke-width="1.6" fill-opacity=".25"/>'),
    'save': svg('Save', f'<path d="M4 14v4.5A1.5 1.5 0 0 0 5.5 20h13a1.5 1.5 0 0 0 1.5-1.5V14" stroke="{B}" stroke-width="1.9"/>'
                        f'<path d="M12 3.5v11M7.5 10.5l4.5 4.5 4.5-4.5" stroke="{G}" stroke-width="2"/>'),
    'history': svg('History', f'<path d="M4.5 12a7.5 7.5 0 1 0 2.2-5.3" stroke="{B}" stroke-width="1.9"/>'
                              f'<path d="M4 3.5v3.7h3.7" stroke="{B}" stroke-width="1.9"/>'
                              f'<path d="M12 7.5V12l3 2" stroke="{G}" stroke-width="2"/>'),
    'add': svg('Add', f'<path d="M12 5v14M5 12h14" stroke="{G}" stroke-width="2.4"/>'),
    'stocks': svg('Lab Stocks', f'<path d="M9.5 9.5h5v7.5a2.5 2.5 0 0 1-5 0z" fill="{G}" stroke="none"/>'
                                f'<path d="M8 6v11a4 4 0 0 0 8 0V6" stroke="{B}" stroke-width="1.9"/>'
                                f'<path d="M6.5 3h11v3h-11z" fill="{B}" stroke="{B}" stroke-width="1.2"/>'),
    'cube': svg('3D', f'<path d="M12 3 20 7.5v9L12 21l-8-4.5v-9z" stroke="{B}" stroke-width="1.8"/>'
                      f'<path d="M4 7.5 12 12l8-4.5M12 12v9" stroke="{G}" stroke-width="1.8"/>'),
    'attach': svg('Attachment', f'<path d="M15.5 7 8.6 13.9a2.2 2.2 0 0 0 3.1 3.1l7-7a4 4 0 0 0-5.7-5.7l-7 7a5.8 5.8 0 0 0 8.2 8.2l5.3-5.3" stroke="{B}" stroke-width="1.8"/>'),
    'image': svg('Image', f'<rect x="3.5" y="5" width="17" height="14" rx="2" stroke="{B}" stroke-width="1.8"/>'
                          f'<path d="M5 17l5-5.5 3.5 3.5 2-2 3.5 4" stroke="{G}" stroke-width="1.8"/><circle cx="15.5" cy="9" r="1.5" fill="{B}" stroke="none"/>'),
    # the notebook: its pages, what goes into them, sharing
    'calendar': svg('Day', f'<rect x="3.5" y="5" width="17" height="15.5" rx="2" stroke="{B}" stroke-width="1.8"/>'
                           f'<path d="M3.5 9.5h17M8 3v4M16 3v4" stroke="{B}" stroke-width="1.8"/><rect x="13" y="13" width="4" height="4" rx=".8" fill="{G}" stroke="none"/>'),
    'folder': svg('Folder', f'<path d="M3.5 18V6a1.5 1.5 0 0 1 1.5-1.5h4.2l2 2.2H19a1.5 1.5 0 0 1 1.5 1.5V18a1.5 1.5 0 0 1-1.5 1.5H5A1.5 1.5 0 0 1 3.5 18z" stroke="{B}" stroke-width="1.8"/>'
                            f'<path d="M3.5 10h17" stroke="{G}" stroke-width="1.8"/>'),
    'protocol': svg('Protocol', f'<path d="M9.5 3.5h5M10.3 3.5v5.5L4.8 18.3A1.5 1.5 0 0 0 6.1 20.5h11.8a1.5 1.5 0 0 0 1.3-2.2L13.7 9V3.5" stroke="{B}" stroke-width="1.8"/>'
                                f'<path d="M7.5 15h9l1.7 3.4a.8.8 0 0 1-.7 1.1H6.5a.8.8 0 0 1-.7-1.1z" fill="{G}" stroke="none"/>'),
    'library': svg('Library', f'<path d="M5 4h3.5v16H5zM10 4h3.5v16H10z" stroke="{B}" stroke-width="1.7"/>'
                              f'<path d="M15.3 5.2l3.2-.9 3.7 14.8-3.2.9z" stroke="{G}" stroke-width="1.7"/>'),
    'steps': svg('Steps', f'<path d="M4 6.5l1.6 1.6L8.5 5M4 12.5l1.6 1.6 2.9-3.1M4 18.5l1.6 1.6 2.9-3.1" stroke="{G}" stroke-width="1.8"/>'
                          f'<path d="M11.5 7h8.5M11.5 13h8.5M11.5 19h8.5" stroke="{B}" stroke-width="1.8"/>'),
    'gear': svg('Settings', f'<path d="M12 2.8v2.6M12 18.6v2.6M2.8 12h2.6M18.6 12h2.6M5.5 5.5l1.8 1.8M16.7 16.7l1.8 1.8M5.5 18.5l1.8-1.8M16.7 7.3l1.8-1.8" stroke="{B}" stroke-width="2"/>'
                            f'<circle cx="12" cy="12" r="5.2" stroke="{B}" stroke-width="1.9"/><circle cx="12" cy="12" r="2" fill="{G}" stroke="none"/>'),
    'pencil': svg('Mark up', f'<path d="M15 4.5l4.5 4.5L9 19.5l-5.3.8.8-5.3z" stroke="{B}" stroke-width="1.8"/>'
                             f'<path d="M13 6.5l4.5 4.5" stroke="{B}" stroke-width="1.6"/><path d="M4.5 15l4.5 4.5-5.3.8z" fill="{G}" stroke="{G}" stroke-width="1"/>'),
    'camera': svg('Photo', f'<path d="M3.5 8.5A1.5 1.5 0 0 1 5 7h2.5l1.5-2.5h6L16.5 7H19a1.5 1.5 0 0 1 1.5 1.5v9.5A1.5 1.5 0 0 1 19 19.5H5A1.5 1.5 0 0 1 3.5 18z" stroke="{B}" stroke-width="1.8"/>'
                           f'<circle cx="12" cy="13" r="3.6" stroke="{G}" stroke-width="2"/>'),
    'person': svg('Person', f'<circle cx="12" cy="8" r="3.6" stroke="{B}" stroke-width="1.9"/><path d="M5 20c.6-4 3.4-6 7-6s6.4 2 7 6" stroke="{B}" stroke-width="1.9"/>'),
    'people': svg('Shared', f'<circle cx="9" cy="8.5" r="3.2" stroke="{B}" stroke-width="1.8"/><path d="M3 19.5c.5-3.5 3-5.3 6-5.3s5.5 1.8 6 5.3" stroke="{B}" stroke-width="1.8"/>'
                            f'<circle cx="16.5" cy="7.5" r="2.7" stroke="{G}" stroke-width="1.8"/><path d="M16.8 12.6c2.4.2 4 1.8 4.4 4.6" stroke="{G}" stroke-width="1.8"/>'),
    'lab': svg('Lab', f'<path d="M3.5 9.5 12 4l8.5 5.5z" fill="{G}" stroke="{G}" stroke-width="1.4"/>'
                      f'<path d="M6 11v6.5M10 11v6.5M14 11v6.5M18 11v6.5M3.5 20h17" stroke="{B}" stroke-width="1.9"/>'),
    'leaf': svg('Plant material', f'<path d="M5 19C4.5 10.5 9.5 5 19.5 4.5 19.5 14 14 19.5 5 19z" fill="{G}" stroke="{G}" stroke-width="1"/>'
                                  f'<path d="M4 20.5c3.5-4.8 7.3-8.6 11.5-11.5" stroke="{B}" stroke-width="1.8"/>'),
    'antibody': svg('Antibody', f'<path d="M12 21v-8.5M12 12.5 6.5 6M12 12.5 17.5 6" stroke="{B}" stroke-width="2.2"/>'
                                f'<path d="M6.5 6 4 3.5M17.5 6 20 3.5" stroke="{G}" stroke-width="2.6"/><path d="M8.6 9.3 6.2 11.4M15.4 9.3l2.4 2.1" stroke="{G}" stroke-width="1.8"/>'),
    # Lab Stocks: orders, boxes, safety
    'cart': svg('Order', f'<path d="M2.5 4h2.6l2.3 10.5h10.4L20 7.5H6.2" stroke="{B}" stroke-width="1.9"/>'
                         f'<circle cx="9" cy="19" r="1.7" fill="{G}" stroke="none"/><circle cx="16.5" cy="19" r="1.7" fill="{G}" stroke="none"/>'),
    'box': svg('Box', f'<path d="M3.5 8 12 4l8.5 4v9L12 21l-8.5-4z" stroke="{B}" stroke-width="1.8"/>'
                      f'<path d="M3.5 8 12 12l8.5-4M12 12v9" stroke="{B}" stroke-width="1.5"/><path d="M7.8 6 16.3 10" stroke="{G}" stroke-width="2"/>'),
    'shield': svg('Safety', f'<path d="M12 3 19.5 6v5.5c0 4.6-3.2 8.2-7.5 9.5-4.3-1.3-7.5-4.9-7.5-9.5V6z" stroke="{B}" stroke-width="1.9"/>'
                            f'<path d="M8.5 12l2.5 2.5 4.5-5" stroke="{G}" stroke-width="2"/>'),
    'hazard': svg('Hazard', f'<path d="M12 3.5 21 19.5H3z" stroke="{B}" stroke-width="1.9"/>'
                            f'<path d="M12 9.5v5" stroke="{G}" stroke-width="2.2"/><circle cx="12" cy="17" r="1.2" fill="{G}" stroke="none"/>'),
    'alert': svg('Urgent', f'<circle cx="12" cy="12" r="8.5" stroke="{B}" stroke-width="1.9"/>'
                           f'<path d="M12 7.5v5.5" stroke="{G}" stroke-width="2.4"/><circle cx="12" cy="16.3" r="1.3" fill="{G}" stroke="none"/>'),
    # MoClo: refreshing, fixing, uploading, measuring, tips
    'refresh': svg('Refresh', f'<path d="M19.5 12a7.5 7.5 0 1 1-2.2-5.3" stroke="{B}" stroke-width="1.9"/>'
                              f'<path d="M20 4v4.6h-4.6" stroke="{G}" stroke-width="2"/>'),
    'wrench': svg('Fix', f'<path d="M14.5 4.3a4.6 4.6 0 0 0 5.2 6.3l-8.9 8.9a2 2 0 0 1-2.9-2.9l8.9-8.9a4.6 4.6 0 0 0-2.3-3.4z" stroke="{B}" stroke-width="1.8"/>'
                         f'<path d="M15.6 4 13.2 6.4l1.6 2.8 2.8 1.6L20 8.4" stroke="{G}" stroke-width="1.8"/>'),
    'upload': svg('Upload', f'<path d="M4 14v4.5A1.5 1.5 0 0 0 5.5 20h13a1.5 1.5 0 0 0 1.5-1.5V14" stroke="{B}" stroke-width="1.9"/>'
                            f'<path d="M12 15V4M7.5 8.5 12 4l4.5 4.5" stroke="{G}" stroke-width="2"/>'),
    'ruler': svg('Length', f'<rect x="2.5" y="8" width="19" height="8" rx="1.5" stroke="{B}" stroke-width="1.8"/>'
                           f'<path d="M6.5 8v3.5M10.5 8v2.5M14.5 8v3.5M18.5 8v2.5" stroke="{G}" stroke-width="1.6"/>'),
    'tip': svg('Tip', f'<path d="M9 17h6M10 20.5h4" stroke="{B}" stroke-width="1.8"/>'
                      f'<path d="M12 3a6 6 0 0 0-3.5 10.9c.4.3.5.7.5 1.2V16h6v-.9c0-.5.2-.9.5-1.2A6 6 0 0 0 12 3z" stroke="{B}" stroke-width="1.8"/>'
                      f'<path d="M12 7.5v4" stroke="{G}" stroke-width="2"/>'),
    # what other tools put into a day
    'cut': svg('Virtual digest', f'<circle cx="7" cy="17.5" r="2.8" stroke="{B}" stroke-width="1.8"/><circle cx="17" cy="17.5" r="2.8" stroke="{B}" stroke-width="1.8"/>'
                                 f'<path d="M8.8 15.3 17.5 3.5M15.2 15.3 6.5 3.5" stroke="{G}" stroke-width="1.9"/>'),
    'primer': svg('Primers', f'<path d="M3 15.5h18" stroke="{B}" stroke-width="2"/><path d="M3 11h11" stroke="{G}" stroke-width="2.2"/>'
                             f'<path d="M14 8l3 3-3 3" stroke="{G}" stroke-width="2.2"/><path d="M6 15.5v-2M10 15.5v-2" stroke="{B}" stroke-width="1.2"/>'),
    'trace': svg('Sequencing read', f'<path d="M3 19.5h18" stroke="{B}" stroke-width="1.7"/>'
                                    f'<path d="M3 19c2-1 2.2-12 4-12s1.8 12 3.5 12" stroke="{G}" stroke-width="1.8"/>'
                                    f'<path d="M10 19c1.7-1 1.9-8 3.5-8s1.8 8 3.5 8 1.8-5 4-5" stroke="{B}" stroke-width="1.8"/>'),
    'part': svg('Part', f'<path d="M5 9h14M7 15h14" stroke="{G}" stroke-width="3"/><path d="M7.5 10.5v3M10.5 10.5v3M13.5 10.5v3M16.5 10.5v3" stroke="{B}" stroke-width="1.4"/>'),
    'cassette': svg('Cassette', f'<rect x="2.5" y="8.5" width="6" height="7" rx="1.3" fill="{B}" stroke="none"/>'
                                f'<rect x="9.5" y="8.5" width="5" height="7" rx="1.3" fill="{G}" stroke="none"/>'
                                f'<rect x="15.5" y="8.5" width="6" height="7" rx="1.3" fill="{B}" stroke="none"/>'),
    # kinds of file
    'pdf': page(f'<path d="M8.5 14h7" stroke="{G}" stroke-width="3.2"/>', 'PDF'),
    'doc': page(f'<path d="M9 11h6M9 14h6M9 17h4" stroke="{G}" stroke-width="1.5"/>', 'Document'),
    'slides': page(f'<rect x="8.5" y="11" width="7" height="5.5" rx=".6" stroke="{G}" stroke-width="1.5"/>', 'Slides'),
    'sheet': page(f'<path d="M8.5 11h7v6.5h-7zM8.5 14.2h7M12 11v6.5" stroke="{G}" stroke-width="1.3"/>', 'Spreadsheet'),
    'archive': page(f'<path d="M12 4v2M12 8v2M12 12v2" stroke="{G}" stroke-width="1.8"/><rect x="10.5" y="15" width="3" height="3.5" rx=".6" stroke="{G}" stroke-width="1.4"/>', 'Archive'),
    'text': page(f'<path d="M9 11h6M9 14h6M9 17h6" stroke="{B}" stroke-width="1.3"/>', 'Text'),
}

os.makedirs(OUT, exist_ok=True)
for name, body in GLYPHS.items():
    open(os.path.join(OUT, f'{name}.svg'), 'w', encoding='utf8').write(body)
rel = os.path.relpath(OUT, HERE).replace(os.sep, '/')
open(os.path.join(HERE, 'glyphs.html'), 'w', encoding='utf8').write(
    '<body style="margin:0;padding:16px;font-family:system-ui;background:#faf8f4;display:flex;flex-wrap:wrap;gap:14px">'
    + ''.join(f'<div style="width:118px;text-align:center;font-size:12px;color:#2b2620"><img src="{rel}/{n}.svg" width="48" height="48"><br>'
              f'<span style="display:inline-flex;gap:6px;align-items:center;margin-top:4px"><img src="{rel}/{n}.svg" width="16">{n}</span></div>'
              for n in GLYPHS) + '</body>')
print(len(GLYPHS), 'glyphs written to', os.path.normpath(OUT))
