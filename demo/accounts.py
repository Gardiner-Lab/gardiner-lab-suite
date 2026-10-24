"""
The demo's labs and accounts, made as the server's operator (no administrator
password needed): run inside the sign-in service, by demo/demo.sh.

    Demo Chair Group   Demo Lab and Demo Partner Lab, which see each other's
                       seeds, stocks and shared equipment
    demo               lab admin of Demo Lab: the account people learn with
    demo-partner       in Demo Partner Lab: owns what the chair group shares

Run again, it changes nothing but the two passwords (set back to DEMO_PASSWORD).
Its last line, WHO {...}, says who the demo is, for demo/wipe.py.
The two are teaching accounts: their passwords cannot be changed from the
dashboard, so one person cannot lock the others out. With DEMO_SHOW_ON_LOGIN=1
the sign-in page offers the demo login to anyone.
"""

import json
import os
import sys

sys.path.insert(0, '/srv/portal')

import directory  # noqa: E402
import labs  # noqa: E402

PASSWORD = os.environ.get('DEMO_PASSWORD') or 'trellis-demo'
CHAIR_GROUP = 'Demo Chair Group'
LABS = ('Demo Lab', 'Demo Partner Lab')
ACCOUNTS = (('demo', 'Demo Lab', 'lab_admin'), ('demo-partner', 'Demo Partner Lab', 'member'))


def main() -> None:
    group = next((g for g in labs.chair_groups() if g['name'] == CHAIR_GROUP), None) \
        or labs.create_chair_group(CHAIR_GROUP, 'demo setup')
    made = {name: labs.by_name(name) or labs.create(name, 'demo setup') for name in LABS}
    for lab in made.values():
        labs.set_chair_group(lab['id'], group['id'])
    for username, lab, role in ACCOUNTS:
        if directory.find(username) is None:
            directory.create(username, PASSWORD)
            said = 'made'
        else:
            directory.set_password(username, PASSWORD)
            said = 'password set'
        labs.add(username, made[lab]['id'], role)
        print(f'  {username}: {said}, {role.replace("_", " ")} of {lab}')
    labs.set_teaching_accounts([a[0] for a in ACCOUNTS],
                               PASSWORD if os.environ.get('DEMO_SHOW_ON_LOGIN') == '1' else None)
    print(f'  {CHAIR_GROUP}: {", ".join(LABS)}')
    # Who the demo is, for demo/wipe.py: the modules know people by name or id, labs by name or id.
    print('WHO ' + json.dumps({'users': [a[0] for a in ACCOUNTS], 'labs': list(LABS),
                               'user_ids': [directory.find(a[0])['id'] for a in ACCOUNTS],
                               'lab_ids': [made[name]['id'] for name in LABS]}))


if __name__ == '__main__':
    main()
