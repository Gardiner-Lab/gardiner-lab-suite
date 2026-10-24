"""
Removes the demo labs' and accounts' data from one module's database, and
nothing else: run inside that module's container by demo/demo.sh reset, as

    python - <module> '<json: users, user_ids, labs, lab_ids>' < demo/wipe.py

    seeds     lines, lots, plants and places of the demo labs, and all that hangs
              on them; the numbering of their codes starts again (the lab codes stay)
    stocks    the demo labs' stocks, orders and what hangs on them; numbering again
    notebook  the demo accounts' notebooks and the demo labs' library pages, with
              their revisions, files, links and shares; shares to the demo
    booking   the demo labs' rooms and equipment and every booking on them; the
              demo accounts' bookings elsewhere; their tags on others' bookings
    editor    the demo accounts' plasmids, reads, history, ladders, enzyme and
              feature lists, workspaces
    moclo     the demo accounts' cassettes, plasmids, backbones and saved items, and
              parts they added to the library; never MoClo's own "DEMO ..." library

The accounts, labs and chair group stay (demo/accounts.py makes them).
"""

import json
import os
import sqlite3
import sys

MODULE = sys.argv[1]
WHO = json.loads(sys.argv[2])
USERS, USER_IDS, LABS, LAB_IDS = WHO['users'], WHO['user_ids'], WHO['labs'], WHO['lab_ids']
removed = {}


def marks(values) -> str:
    return ','.join('?' * len(values)) or "''"


def ids(conn, sql, args=()) -> list:
    return [r[0] for r in conn.execute(sql, list(args))]


def drop(conn, table, column, values):
    values = list(values)
    for start in range(0, len(values), 500):
        chunk = values[start:start + 500]
        n = conn.execute(f'DELETE FROM {table} WHERE {column} IN ({marks(chunk)})', chunk).rowcount
        if n:
            removed[table] = removed.get(table, 0) + n


def renumber(conn, codes):
    """The demo labs' codes number from 0001 again (counters 'DEMO-L', ...)."""
    for code in codes:
        n = conn.execute('DELETE FROM counters WHERE prefix LIKE ?', (f'{code}-%',)).rowcount
        if n:
            removed['counters'] = removed.get('counters', 0) + n


def seeds(conn):
    lines = ids(conn, f'SELECT id FROM lines WHERE lab IN ({marks(LABS)})', LABS)
    lots = ids(conn, f'SELECT id FROM lots WHERE lab IN ({marks(LABS)})', LABS)
    plants = ids(conn, f'SELECT id FROM plants WHERE lab IN ({marks(LABS)})', LABS)
    records = lines + lots + plants
    observations = []
    for start in range(0, len(records), 500):
        chunk = records[start:start + 500]
        observations += ids(conn, f'SELECT id FROM observations WHERE record_id IN ({marks(chunk)})', chunk)
    drop(conn, 'attachments', 'record_id', records + observations)
    drop(conn, 'observations', 'id', observations)
    drop(conn, 'seg_tests', 'lot_id', lots)
    drop(conn, 'line_parents', 'line_id', lines)
    drop(conn, 'line_plasmids', 'line_id', lines)
    drop(conn, 'changes', 'record_id', records)
    drop(conn, 'plants', 'id', plants)
    drop(conn, 'lots', 'id', lots)
    drop(conn, 'lines', 'id', lines)
    drop(conn, 'places', 'lab', LABS)
    renumber(conn, ids(conn, f'SELECT code FROM lab_codes WHERE lab IN ({marks(LABS)})', LABS))


def stocks(conn):
    records = []
    for table in ('glycerol', 'primers', 'chemicals', 'antibodies', 'material'):
        found = ids(conn, f'SELECT id FROM {table} WHERE lab IN ({marks(LABS)})', LABS)
        records += found
        drop(conn, table, 'id', found)
    orders = ids(conn, f'SELECT id FROM orders WHERE lab IN ({marks(LABS)})', LABS)
    drop(conn, 'attachments', 'record_id', records + [str(o) for o in orders])
    drop(conn, 'changes', 'record_id', records + [str(o) for o in orders])
    drop(conn, 'elab_links', 'record_id', records)
    drop(conn, 'orders', 'id', orders)
    drop(conn, 'elab_settings', 'lab', LABS)
    renumber(conn, ids(conn, f'SELECT code FROM lab_codes WHERE lab IN ({marks(LABS)})', LABS))


def notebook(conn):
    notes = ids(conn, f"SELECT id FROM notes WHERE (space != 'library' AND owner IN ({marks(USERS)})) "
                      f"OR (space = 'library' AND type != 'library' AND lab IN ({marks(LAB_IDS)}))", USERS + LAB_IDS)
    for table in ('branches', 'attributes', 'revisions', 'attachments', 'links', 'shares', 'favorites', 'day_bookings',
                  'booking_notes'):
        drop(conn, table, 'note_id', notes)
    drop(conn, 'branches', 'parent_id', notes)
    drop(conn, 'favorites', 'username', USERS)
    drop(conn, 'shares', 'target', USERS + LAB_IDS)
    drop(conn, 'notes', 'id', notes)


def booking(conn):
    resources = ids(conn, f'SELECT id FROM resources WHERE owner_lab_id IN ({marks(LAB_IDS)})', LAB_IDS)
    bookings = ids(conn, f'SELECT id FROM bookings WHERE resource_id IN ({marks(resources)}) '
                         f'OR booked_by IN ({marks(USERS)})', resources + USERS)
    drop(conn, 'booking_people', 'booking_id', bookings)
    drop(conn, 'booking_people', 'username', USERS)
    drop(conn, 'bookings', 'id', bookings)
    drop(conn, 'resource_shares', 'resource_id', resources)
    drop(conn, 'resource_shares', 'target_id', LAB_IDS)
    drop(conn, 'resources', 'id', resources)


def editor(conn):
    sequences = ids(conn, f'SELECT id FROM sequences WHERE owner_id IN ({marks(USER_IDS)})', USER_IDS)
    drop(conn, 'reads', 'sequence_id', sequences)
    drop(conn, 'sequence_revisions', 'sequence_id', sequences)
    drop(conn, 'sequences', 'id', sequences)
    for table in ('feature_library', 'enzyme_lists', 'ladders'):
        drop(conn, table, 'owner_id', USER_IDS)
    drop(conn, 'workspaces', 'user_id', USER_IDS)


def moclo(conn):
    for table in ('cassettes', 'final_plasmids'):
        drop(conn, table, 'owner_id', USER_IDS)
    drop(conn, 'saved_items', 'user_id', USER_IDS)
    drop(conn, 'backbones', 'id', ids(conn, f"SELECT id FROM backbones WHERE owner_id IN ({marks(USER_IDS)}) "
                                            "AND name NOT LIKE 'DEMO %'", USER_IDS))
    parts_db = os.environ.get('PARTS_DATABASE_PATH')
    if parts_db and os.path.exists(parts_db):
        parts = sqlite3.connect(parts_db)
        with parts:
            drop(parts, 'parts', 'id', ids(parts, f"SELECT id FROM parts WHERE contributor IN ({marks(USERS)}) "
                                                  "AND name NOT LIKE 'DEMO %'", USERS))
        parts.close()


PATHS = {'seeds': ('SEEDS_DATABASE_PATH', '/seeds/seeds.db'), 'stocks': ('STOCKS_DATABASE_PATH', '/stocks/stocks.db'),
         'notebook': ('NOTEBOOK_DATABASE_PATH', '/notebook/notebook.db'), 'booking': ('BOOKING_DATABASE_PATH', '/booking/booking.db'),
         'editor': ('EDITOR_DATABASE_PATH', '/data/plasmid_editor.db'), 'moclo': ('DATABASE_PATH', '/data/moclo.db')}

if __name__ == '__main__':
    env, default = PATHS[MODULE]
    path = os.environ.get(env) or default
    if not os.path.exists(path):
        sys.exit(f'{MODULE}: no database at {path}')
    conn = sqlite3.connect(path, timeout=30)
    conn.execute('PRAGMA busy_timeout = 30000')
    with conn:
        globals()[MODULE](conn)
    conn.close()
    print(f'  {MODULE}: ' + (', '.join(f'{n} {t}' for t, n in sorted(removed.items())) if removed else 'nothing to remove'))
