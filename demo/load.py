"""
Fills the demo labs (demo/accounts.py) with one connected piece of work, through
the suite's own web API as their two accounts, so every feature has something to
show. Run by demo/demo.sh; on its own:

    python3 demo/load.py --url https://lab.example.org [--password ...] [--insecure]

The story: Demo Lab builds a red fluorescent reporter (tRFP) and puts it into
Arabidopsis.

    MoClo         three transcription units from the demo parts library, a Level 1
                  plasmid (35S:tRFP) and a Level 2 plasmid with all three
    Plasmid Ed.   both plasmids, linked to MoClo; sequencing reads on the Level 1
                  plasmid, checked and confirmed; a home-made gel ladder; an enzyme list
    Lab Stocks    glycerol stocks of the plasmids (E. coli and Agrobacterium),
                  primers, chemicals (one run out), antibodies, leaf samples, orders
    Seed Bank     places; Col-0 from a stock centre, dipped; T1 selection on Basta;
                  an independent event founded; a 3:1 segregation; a T2 drought
                  trial scored for height, flowering and fluorescence; a homozygous
                  T3; a cross with the partner lab's mutant
    Notebook      day pages for each step, linking the plasmids, stocks and seeds;
                  a protocol in the library; a page shared with the partner
    Booking       the lab's confocal and PCR machine (shared with the chair group),
                  a meeting room; bookings this week, with people tagged

The partner lab (demo-partner) has its own mutant line, stocks and a booking,
which Demo Lab sees through the chair group but does not change.

It stops if the demo already has data: reset first (demo/demo.sh reset).
"""

import argparse
import os
import sys
from datetime import date, datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from suite_client import Suite, SuiteError  # noqa: E402

TODAY = date.today()


def day(n: int) -> str:
    """n days ago (negative: ahead), as YYYY-MM-DD."""
    return (TODAY - timedelta(days=n)).isoformat()


def at(days_ahead: int, hour: int, minute: int = 0) -> str:
    return datetime.combine(TODAY + timedelta(days=days_ahead), datetime.min.time()).replace(
        hour=hour, minute=minute).isoformat(timespec='minutes')


def soon(hours: int = 2):
    """The next whole hour today with `hours` free before 20:00, else tomorrow at 9: (start, end)."""
    now = datetime.now()
    start = now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
    if start.hour + hours > 20 or start.date() != now.date():
        start = datetime.combine(now.date() + timedelta(days=1), datetime.min.time()).replace(hour=9)
    return start.isoformat(timespec='minutes'), (start + timedelta(hours=hours)).isoformat(timespec='minutes')


def say(text: str) -> None:
    print(f'  {text}', flush=True)


def link(kind: str, ident: str, text: str) -> str:
    """A link in a notebook page to a plasmid (by id), a stock or a seed record (by code)."""
    return f'<a data-{kind}="{ident}">{text}</a>'


def text(html: str) -> dict:
    return {'type': 'text', 'html': html}


def steps(title: str, items, done: int = 0) -> dict:
    return {'type': 'steps', 'title': title, 'items': [{'text': t, 'done': i < done} for i, t in enumerate(items)]}


def table(title: str, columns, rows) -> dict:
    return {'type': 'table', 'title': title, 'columns': [{'name': c, 'kind': 'text'} for c in columns],
            'rows': [{'cells': [str(c) for c in r]} for r in rows]}


class Demo:
    def __init__(self, demo: Suite, partner: Suite):
        self.demo, self.partner = demo, partner
        self.ids = {}

    # --- MoClo --------------------------------------------------------------------------

    def moclo(self):
        parts = {p['name']: p['id'] for p in self.demo.get('/api/parts?limit=500')['parts']}
        backbones = {b['name']: b['id'] for b in self.demo.get('/api/backbones')['backbones']}
        need = ['DEMO p35S (short)', 'DEMO tRFP (CDS)', 'DEMO t35S', 'DEMO pMAS', 'DEMO CDS reporter', 'DEMO pNOS',
                'DEMO CDS tag', 'DEMO end-linker A (CGCT->GTCA)', 'DEMO start-linker B (GTCA->GGAG)',
                'DEMO end-linker B (CGCT->TAGC)', 'DEMO start-linker C (TAGC->GGAG)']
        missing = [n for n in need if n not in parts] + [b for b in ('DEMO L1 acceptor (BsaI)', 'DEMO L2 acceptor (BpiI)')
                                                         if b not in backbones]
        if missing:
            raise SuiteError(f'MoClo\'s demo library is missing {", ".join(missing)} (it is made as MoClo first starts)')

        def cassette(name, names):
            made = self.demo.post('/api/cassettes', {'name': name, 'part_ids': [parts[n] for n in names]})['cassette']
            say(f'MoClo cassette {name}')
            return made['id']

        tu = cassette('35S:tRFP', ['DEMO p35S (short)', 'DEMO tRFP (CDS)', 'DEMO t35S'])
        tu1 = cassette('TU1 35S:tRFP (to TU2)', ['DEMO p35S (short)', 'DEMO tRFP (CDS)', 'DEMO t35S',
                                                 'DEMO end-linker A (CGCT->GTCA)'])
        tu2 = cassette('TU2 MAS:reporter', ['DEMO start-linker B (GTCA->GGAG)', 'DEMO pMAS', 'DEMO CDS reporter',
                                            'DEMO t35S', 'DEMO end-linker B (CGCT->TAGC)'])
        tu3 = cassette('TU3 NOS:tag', ['DEMO start-linker C (TAGC->GGAG)', 'DEMO pNOS', 'DEMO CDS tag', 'DEMO t35S'])
        l1 = self.demo.post('/api/plasmids', {'name': 'pDEMO-L1 35S:tRFP', 'backbone_id': backbones['DEMO L1 acceptor (BsaI)'],
                                              'cassette_ids': [tu]})['plasmid']
        l2 = self.demo.post('/api/plasmids', {'name': 'pDEMO-L2 tRFP-reporter-tag', 'backbone_id': backbones['DEMO L2 acceptor (BpiI)'],
                                              'cassette_ids': [tu1, tu2, tu3]})['plasmid']
        say('MoClo plasmids pDEMO-L1 35S:tRFP and pDEMO-L2 tRFP-reporter-tag')
        for kind, item, title in (('plasmid', l2['id'], l2['name']), ('construct', tu, '35S:tRFP')):
            self.demo.post('/api/me/saved', {'item_type': kind, 'ref_id': item, 'title': title,
                                             'summary': {'note': 'Saved by the demo'}})
        say('two saved to the dashboard tab Saved constructs')
        self.ids.update(moclo_l1=l1['id'], moclo_l2=l2['id'])

    # --- Plasmid Editor --------------------------------------------------------------------

    def editor(self):
        l1 = self.demo.post('/editor/api/moclo/import', {'kind': 'plasmid', 'id': self.ids['moclo_l1']})['sequence']
        l2 = self.demo.post('/editor/api/moclo/import', {'kind': 'plasmid', 'id': self.ids['moclo_l2']})['sequence']
        self.ids.update(l1=l1['id'], l1_name=l1['name'], l2=l2['id'], l2_name=l2['name'])
        say(f'Plasmid Editor: {l1["name"]} ({len(l1["sequence"])} bp) and {l2["name"]} ({len(l2["sequence"])} bp)')
        # Two Sanger reads of clone 2: one clean, one with a base call to look at.
        seq = l1['sequence'].upper()
        start = max(0, seq.find('ATG') - 60)
        read1 = seq[start:start + 780]
        read2 = list(seq[start + 500:start + 1250])
        read2[180] = {'A': 'G', 'C': 'T', 'G': 'A', 'T': 'C'}.get(read2[180], 'A')
        fasta = f'>clone2_35S-F\n{read1}\n>clone2_tRFP-R\n{"".join(read2)}\n'.encode()
        reads = self.demo.post(f'/editor/api/sequences/{l1["id"]}/reads', files=[('file', 'clone2_reads.fasta', fasta, 'text/plain')],
                               form={'clone_number': '2'})['reads']
        self.ids.update(reads=[r['id'] for r in reads])
        say('two sequencing reads of clone 2 aligned (judged once its glycerol stock is made)')
        self.demo.post('/editor/api/tools/ladders', {
            'name': 'Demo 1 kb ladder (home-made)', 'description': 'Our own mix: pUC19 and lambda digests. Shared in the chair group.',
            'bands': [{'size': s} for s in (10000, 8000, 6000, 5000, 4000, 3000, 2000, 1500, 1000, 750, 500, 250)]})
        say('a home-made gel ladder')
        try:
            self.demo.post('/editor/api/tools/enzyme-lists', {'name': 'Demo cloning enzymes',
                                                              'enzymes': ['BsaI', 'BpiI', 'EcoRI', 'HindIII', 'XbaI', 'NotI']})
            say('an enzyme list')
        except SuiteError as exc:
            say(f'(no enzyme list: {exc})')

    # --- Lab Stocks -----------------------------------------------------------------------

    def stocks(self):
        try:
            self.demo.put('/stocks/api/lab', {'code': 'DEMO'})
        except SuiteError as exc:
            say(f'(lab code kept: {exc})')
        plural = {'glycerol': 'glycerol', 'primer': 'primers', 'chemical': 'chemicals', 'antibody': 'antibodies'}
        add = lambda kind, data, who=None: (who or self.demo).post(f'/stocks/api/{plural[kind]}', data)['record']  # noqa: E731
        g1 = add('glycerol', {'plasmid_id': self.ids['l1'], 'plasmid_name': self.ids['l1_name'], 'clone': '2', 'host': 'DH5α',
                              'host_system': 'E. coli', 'selection': 'Kanamycin', 'location': '−80 °C freezer 1 / box 3 / A1',
                              'made_on': day(110), 'biosafety': 'I', 'harmful': 'no', 'plant_markers': 'BASTA',
                              'notes': 'Clone 2: both reads match.'})
        g2 = add('glycerol', {'plasmid_id': self.ids['l1'], 'plasmid_name': self.ids['l1_name'], 'clone': '2',
                              'host': 'GV3101 (pMP90)', 'host_system': 'Agrobacterium / Rhizobium',
                              'selection': 'Kanamycin, Rifampicin, Gentamicin', 'location': '−80 °C freezer 1 / box 3 / A2',
                              'made_on': day(80), 'biosafety': 'I', 'harmful': 'no', 'notes': 'For floral dipping.'})
        g3 = add('glycerol', {'plasmid_id': self.ids['l2'], 'plasmid_name': self.ids['l2_name'], 'clone': '1', 'host': 'DH5α',
                              'host_system': 'E. coli', 'selection': 'Spectinomycin', 'location': '−80 °C freezer 1 / box 3 / A3',
                              'made_on': day(95), 'biosafety': 'I', 'harmful': 'no', 'status': 'in stock'})
        self.ids.update(g1=g1['code'], g2=g2['code'], g3=g3['code'])
        # The reads judged sufficient for clone 2, kept as g1; the plasmid confirmed.
        for read, note in zip(self.ids['reads'], ('', 'One base differs, at a low-quality call: the trace shows the right base.')):
            self.demo.post(f'/editor/api/sequences/reads/{read}/verdict', {'verdict': 'sufficient', 'note': note,
                                                                           'glycerol_stock': g1['code'], 'clone_number': '2'})
        self.demo.post(f'/editor/api/sequences/{self.ids["l1"]}/confirm', {'glycerol_stock': g1['code'], 'clone_number': '2'})
        say(f'{self.ids["l1_name"]}: reads judged sufficient, confirmed, kept as {g1["code"]}')
        primers = [('35S-F', 'CCACGTCTTCAAAGCAAGTGG', 'forward', 'p35S', 'sequencing, genotyping'),
                   ('tRFP-R', 'CTTGAAGCGCATGAACTCCTTG', 'reverse', 'tRFP', 'genotyping T1 plants'),
                   ('M13-F (-20)', 'GTAAAACGACGGCCAGT', 'forward', 'vector', 'sequencing'),
                   ('M13-R', 'CAGGAAACAGCTATGAC', 'reverse', 'vector', 'sequencing')]
        made = [add('primer', {'name': n, 'sequence': s, 'direction': d, 'target': t, 'purpose': p, 'concentration': '100 µM',
                               'location': '−20 °C box P1', 'supplier': 'IDT', 'ordered_on': day(120)}) for n, s, d, t, p in primers]
        self.ids.update(primers=[p['code'] for p in made])
        chemicals = [{'name': 'Glufosinate-ammonium (Basta)', 'cas': '77182-82-2', 'size': '100 mg', 'room': 'Lab 2.12, poison cabinet',
                      'notes': 'Sigma-Aldrich 45520. T1 selection: 10 mg/L on plates, or sprayed.'},
                     {'name': 'Kanamycin sulfate', 'cas': '25389-94-0', 'size': '5 g', 'room': 'Lab 2.12, fridge 1',
                      'notes': 'Duchefa K0126. 50 mg/L for E. coli and Agrobacterium.'},
                     {'name': 'Silwet L-77', 'size': '30 mL', 'room': 'Lab 2.12', 'status': 'out',
                      'notes': 'Lehle Seeds VIS-30. Surfactant for floral dip, 0.02%.'},
                     {'name': 'Murashige & Skoog medium incl. vitamins', 'size': '1 kg', 'room': 'Media kitchen',
                      'notes': 'Duchefa M0222.'}]
        made = [add('chemical', c) for c in chemicals]
        self.ids.update(basta=made[0]['code'], silwet=made[2]['code'])
        a1 = add('antibody', {'short_code': 'αRFP', 'description': 'anti-RFP, rabbit polyclonal. Western 1:2000.', 'type': 'primary',
                              'host': 'rabbit', 'producer': 'Abcam', 'product_number': 'ab62341', 'notes': '4 °C fridge 2, box Ab'})
        add('antibody', {'short_code': 'αRb-HRP', 'description': 'anti-rabbit IgG, HRP-conjugated. 1:10000.', 'type': 'secondary',
                         'host': 'goat', 'producer': 'Sigma-Aldrich', 'product_number': 'A0545', 'notes': '4 °C fridge 2, box Ab'})
        self.ids.update(anti_rfp=a1['code'])
        say(f'Lab Stocks: 3 glycerol stocks, 4 primers, 4 chemicals (Silwet run out), 2 antibodies')
        orders = [{'item': 'Silwet L-77, 30 mL', 'category': 'chemical', 'quantity': '1', 'supplier': 'Lehle Seeds',
                   'product_number': 'VIS-30', 'urgent': True, 'notes': 'For the next floral dip.'},
                  {'item': 'Basta-resistant genotyping primers (bar-F/bar-R)', 'category': 'primer', 'quantity': '2 × 25 nmol',
                   'supplier': 'IDT'},
                  {'item': 'Phusion High-Fidelity DNA Polymerase', 'category': 'enzyme', 'quantity': '100 U', 'supplier': 'NEB',
                   'product_number': 'M0530S'}]
        made = [self.demo.post('/stocks/api/orders', o) for o in orders]
        for order, status in zip(made[1:], ('ordered', 'received')):
            order_id = (order.get('order') or order).get('id')
            try:
                self.demo.put(f'/stocks/api/orders/{order_id}', {'status': status})
                if status == 'received':
                    pass
            except SuiteError as exc:
                say(f'(order left as requested: {exc})')
        say('three orders: one urgent request, one ordered, one received')

    def plant_material(self, plants):
        """Leaf samples of the T1 plants, for genotyping (after the seed bank has them)."""
        try:
            self.demo.post('/stocks/api/material/many', {
                'items': [{'name': f'T1 leaf DNA, plant {p}', 'from_plant': p} for p in plants],
                'shared': {'tissue': 'leaf', 'species': 'Arabidopsis thaliana', 'material': 'DNA', 'location': '−20 °C box DNA-1',
                           'collected_on': day(36), 'collected_by': 'demo', 'experiment': 'T1 genotyping'}})
            say(f'Lab Stocks: {len(plants)} tubes of T1 leaf DNA')
        except SuiteError as exc:
            say(f'(no plant material: {exc})')

    # --- Seed Bank ------------------------------------------------------------------------

    def seeds(self):
        s = self.demo
        try:
            s.put('/seeds/api/lab', {'code': 'DEMO'})
        except SuiteError as exc:
            say(f'(seed bank lab code kept: {exc})')
        places = s.post('/seeds/api/places', {'name': 'Growth chamber 3', 'kind': 'growth chamber',
                                              'conditions': '16 h light, 22 °C, 60% humidity'})['places']
        s.post('/seeds/api/places', {'name': 'Greenhouse B', 'kind': 'greenhouse', 'conditions': 'natural light + 16 h, 20–25 °C'})
        places = {p['name']: p['id'] for p in s.get('/seeds/api/places')['places']}
        chamber, greenhouse = places['Growth chamber 3'], places['Greenhouse B']
        say('Seed Bank: places Growth chamber 3 and Greenhouse B')

        col = s.post('/seeds/api/lines', {'name': 'Col-0', 'species': 'Arabidopsis thaliana', 'kind': 'wild type',
                                          'collection': 'wildtype', 'stock_center_number': 'N1092',
                                          'description': 'Columbia, the reference accession.'})['record']
        tr = s.post('/seeds/api/lines', {
            'name': '35S:tRFP', 'species': 'Arabidopsis thaliana', 'kind': 'transgenic', 'background': 'Col-0',
            'parents': [{'id': col['code'], 'role': 'background'}],
            'plasmids': [{'id': self.ids['l1'], 'name': self.ids['l1_name']}],
            'biosafety': 'I', 'gmo_type': 'T-DNA insertion', 'gene_expression': 'marker line', 'selection_marker': 'BASTA',
            'construction': 'Agrobacterium floral dip (GV3101)', 'description': 'Red fluorescent reporter, ubiquitous.'})['record']
        col_lot = s.post('/seeds/api/lots', {'line': col['code'], 'source': 'NASC (N1092)', 'amount': '~2000 seeds',
                                             'location': '4 °C seed cabinet / box 1', 'germination': 98})['record']
        say(f'lines {col["code"]} Col-0 and {tr["code"]} 35S:tRFP; seed lot {col_lot["code"]} from NASC')

        # Col-0 sown, dipped, and harvested as T1 seeds of the transgenic line.
        dipped = s.post(f'/seeds/api/lots/{col_lot["code"]}/sow', {'count': 6, 'sown_on': day(110), 'place': chamber,
                                                                   'location': 'shelf 1, tray A'})['record']['plants']
        t1 = s.post(f'/seeds/api/plants/{dipped[0]["code"]}/harvest', {'line': tr['code'], 'harvested_on': day(62),
                                                                       'amount': '~3000 seeds', 'location': '4 °C seed cabinet / box 2',
                                                                       'notes': 'Dipped twice, a week apart.'})['record']
        s.post('/seeds/api/plants/change', {'plants': [p['code'] for p in dipped[1:]], 'status': 'discarded'})
        say(f'Col-0 dipped with {self.ids["g2"]}; T1 seeds {t1["code"]}')

        # T1 on Basta: four survive; one founds the independent event #3.
        t1_plants = [p['code'] for p in s.post(f'/seeds/api/lots/{t1["code"]}/sow', {
            'count': 20, 'sown_on': day(55), 'place': chamber, 'location': 'Basta plate 1, then tray B',
            'treatment': 'Basta 10 mg/L'})['record']['plants']]
        keep = [t1_plants[i] for i in (2, 6, 11, 17)]
        s.post('/seeds/api/plants/change', {'plants': [p for p in t1_plants if p not in keep], 'status': 'dead'})
        for p in keep:
            s.post(f'/seeds/api/plant/{p}/observations', {'trait': 'resistance (Basta)', 'value': 'resistant', 'observed_on': day(45)})
            s.post(f'/seeds/api/plant/{p}/observations', {'trait': 'fluorescence (RFP)', 'value': 'strong' if p != keep[3] else 'weak',
                                                          'observed_on': day(40)})
        event = s.post(f'/seeds/api/plants/{keep[0]}/found-line', {'name': '35S:tRFP #3',
                                                                   'description': 'Independent T1 event from plant 3: strong RFP, single insertion.'})['record']
        t2 = s.post(f'/seeds/api/plants/{keep[0]}/harvest', {'harvested_on': day(30), 'amount': '~800 seeds',
                                                            'location': '4 °C seed cabinet / box 2', 'germination': 95})['record']
        s.post(f'/seeds/api/plants/{keep[1]}/harvest', {'harvested_on': day(30), 'amount': '~600 seeds',
                                                       'location': '4 °C seed cabinet / box 2'})
        s.post(f'/seeds/api/lots/{t2["code"]}/seg-tests', {'tested_on': day(26), 'selection': 'Basta', 'resistant': 74, 'sensitive': 26,
                                                          'expected': '3:1', 'notes': 'Single insertion.'})
        self.plant_material(keep)
        say(f'T1 on Basta: 4 of 20 survive; event {event["code"]} founded; T2 seeds {t2["code"]} segregate 3:1')

        # T2 drought trial: 12 control, 12 drought, scored.
        control = s.post(f'/seeds/api/lots/{t2["code"]}/sow', {'count': 12, 'sown_on': day(26), 'place': chamber,
                                                               'location': 'shelf 2, tray A', 'treatment': 'control'})['record']['plants']
        drought = s.post(f'/seeds/api/lots/{t2["code"]}/sow', {'count': 12, 'sown_on': day(26), 'place': chamber,
                                                               'location': 'shelf 2, tray B', 'treatment': 'drought'})['record']['plants']
        control = [p['code'] for p in control][-12:]
        drought = [p['code'] for p in s.get(f'/seeds/api/lot/{t2["code"]}')['record']['plants'] if p['treatment'] == 'drought']
        heights = ([24.5, 26.0, 22.5, 27.5, 25.0, 23.5, 26.5, 24.0, 25.5, 22.0, 27.0, 23.0],
                   [16.0, 14.5, 18.0, 13.5, 15.5, 17.0, 12.5, 16.5, 14.0, 19.0, 15.0, 13.0])
        flowering = ([26, 27, 25, 28, 26, 27, 25, 26, 28, 27, 26, 25], [23, 24, 22, 25, 23, 24, 22, 23, 25, 24, 23, 22])
        rfp = (['strong'] * 9 + ['none'] * 3, ['strong'] * 8 + ['weak'] * 1 + ['none'] * 3)
        for group, h, f, r in ((control, *[x[0] for x in (heights, flowering, rfp)]), (drought, *[x[1] for x in (heights, flowering, rfp)])):
            s.post('/seeds/api/score', {'trait': 'height', 'unit': 'cm', 'observed_on': day(1),
                                        'values': [{'plant': p, 'value': str(v)} for p, v in zip(group, h)]})
            s.post('/seeds/api/score', {'trait': 'flowering time', 'unit': 'days', 'observed_on': day(2),
                                        'values': [{'plant': p, 'value': str(v)} for p, v in zip(group, f)]})
            s.post('/seeds/api/score', {'trait': 'fluorescence (RFP)', 'observed_on': day(5),
                                        'values': [{'plant': p, 'value': v, 'notes': 'no RFP: segregant' if v == 'none' else ''}
                                                   for p, v in zip(group, r)]})
        s.put(f'/seeds/api/plants/{control[1]}', {'selected': True, 'zygosity': 'homozygous'})
        s.put(f'/seeds/api/plants/{control[4]}', {'selected': True})
        t3 = s.post(f'/seeds/api/plants/{control[1]}/harvest', {'harvested_on': day(0), 'amount': '~1500 seeds',
                                                               'location': '4 °C seed cabinet / box 2', 'zygosity': 'homozygous'})['record']
        s.post(f'/seeds/api/lots/{t3["code"]}/seg-tests', {'tested_on': day(0), 'selection': 'Basta', 'resistant': 96, 'sensitive': 0,
                                                          'expected': '1:0', 'notes': 'All resistant: homozygous.'})
        say(f'T2 drought trial: 24 plants scored for height, flowering and RFP; homozygous T3 {t3["code"]}')
        # Col-0 growing in the greenhouse, as a control for the cross.
        s.post(f'/seeds/api/lots/{col_lot["code"]}/sow', {'count': 6, 'sown_on': day(30), 'place': greenhouse,
                                                          'location': 'bench 4', 'treatment': 'control'})
        self.ids.update(col=col['code'], tr=tr['code'], col_lot=col_lot['code'], dipped=dipped[0]['code'], t1=t1['code'],
                        t1_keep=keep, event=event['code'], t2=t2['code'], control=control, drought=drought, t3=t3['code'])

    def partner_seeds(self):
        p = self.partner
        place = p.post('/seeds/api/places', {'name': 'Greenhouse P', 'kind': 'greenhouse', 'conditions': '18 °C nights, 24 °C days'})
        line = p.post('/seeds/api/lines', {'name': 'myb21-1', 'species': 'Arabidopsis thaliana', 'kind': 'mutant', 'background': 'Col-0',
                                           'collection': 'SALK', 'stock_center_number': 'SALK_042711C', 'gmo_type': 'T-DNA insertion',
                                           'gene_expression': 'knock-out', 'mutation_info': 'T-DNA in exon 2 of MYB21 (AT3G27810).',
                                           'selection_marker': 'Kanamycin'})['record']
        lot = p.post('/seeds/api/lots', {'line': line['code'], 'source': 'ABRC (SALK_042711C)', 'amount': '~500 seeds',
                                         'location': 'Partner lab seed box 1', 'zygosity': 'homozygous'})['record']
        plants = p.post(f'/seeds/api/lots/{lot["code"]}/sow', {'count': 8, 'sown_on': day(34), 'place': place['id'],
                                                               'location': 'bench 1'})['record']['plants']
        p.post('/seeds/api/score', {'trait': 'flowering time', 'unit': 'days', 'observed_on': day(3),
                                    'values': [{'plant': x['code'], 'value': str(v)} for x, v in zip(plants, (29, 30, 28, 31, 29, 30, 30, 28))]})
        self.ids.update(partner_line=line['code'], partner_lot=lot['code'], partner_plant=plants[0]['code'])
        say(f'Partner lab: line {line["code"]} myb21-1 (SALK), 8 plants in Greenhouse P')
        # Demo Lab's T2 plant crossed with the partner's mutant (the father): the F1 is Demo Lab's.
        f1 = self.demo.post(f'/seeds/api/plants/{self.ids["control"][4]}/cross', {
            'father': plants[0]['code'], 'name': '35S:tRFP #3 × myb21-1', 'harvested_on': day(1), 'amount': '~120 seeds',
            'location': '4 °C seed cabinet / box 3'})['record']
        self.ids.update(f1=f1['code'])
        say(f'cross 35S:tRFP #3 × myb21-1 (the partner lab\'s plant as father): F1 seeds {f1["code"]}')

    def partner_stocks(self):
        p = self.partner
        p.post('/stocks/api/chemicals', {'name': 'Hygromycin B (50 mg/mL)', 'cas': '31282-04-9', 'size': '20 mL',
                                         'room': 'Partner lab, fridge', 'notes': 'Roche 10843555001.'})
        p.post('/stocks/api/antibodies', {'short_code': 'αGFP', 'description': 'anti-GFP, mouse monoclonal (clones 7.1 and 13.1).',
                                          'type': 'primary', 'host': 'mouse', 'producer': 'Roche', 'product_number': '11814460001'})
        say('Partner lab: Hygromycin B and an anti-GFP antibody (Demo Lab sees them, read-only)')

    # --- Booking -------------------------------------------------------------------------

    def booking(self):
        b = self.demo
        lab = b.get('/booking/api/me')['person']['labs'][0]['id']          # Demo Lab, which the demo account runs
        made = {}
        for data in ({'name': 'Confocal microscope (Leica SP8)', 'kind': 'Microscope', 'location': 'Imaging room 1.04',
                      'description': 'Book at least a day ahead. Lasers: 405, 488, 552, 638 nm. Training needed.',
                      'colour': '#2a7480', 'capacity': 1},
                     {'name': 'PCR machine (Bio-Rad C1000)', 'kind': 'Thermocycler', 'location': 'Lab 2.12',
                      'colour': '#b4532a', 'capacity': 1},
                     {'name': 'Meeting room 2.14', 'kind': 'Meeting room', 'location': 'Second floor',
                      'description': 'Projector, whiteboard, 10 seats.', 'colour': '#7a4a8f', 'capacity': 10}):
            r = b.post('/booking/api/resources', {**data, 'owner_lab_id': lab})
            made[data['name']] = (r.get('resource') or r)['id']
        say('Booking: a confocal microscope, a PCR machine and a meeting room (shared with the chair group)')
        confocal, pcr, room = made.values()
        bookings = [
            (b, {'resource_id': confocal, 'start': at(1, 10), 'end': at(1, 12), 'title': 'RFP in T2 roots',
                 'notes': 'Control vs drought, 6 plants each.', 'people': ['demo-partner']}),
            (b, {'resource_id': pcr, 'start': soon()[0], 'end': soon()[1], 'title': 'Genotyping T2 (35S-F / tRFP-R)'}),
            (b, {'resource_id': pcr, 'start': at(4, 9), 'end': at(4, 11), 'title': 'Colony PCR, pDEMO-L2'}),
            (self.partner, {'resource_id': confocal, 'start': at(2, 13), 'end': at(2, 16), 'title': 'myb21-1 flowers'}),
        ]
        for week in range(3):
            bookings.append((b, {'resource_id': room, 'start': at(3 + 7 * week, 10), 'end': at(3 + 7 * week, 11),
                                 'title': 'Lab meeting', 'people': ['demo-partner']}))
        for who, data in bookings:
            try:
                who.post('/booking/api/bookings', data)
            except SuiteError as exc:
                say(f'(booking skipped: {exc})')
        say(f'{len(bookings)} bookings this week and the next: microscope, PCR, weekly lab meeting (people tagged)')

    # --- Lab Notebook -------------------------------------------------------------------

    def notebook(self):
        n = self.demo
        me = n.get('/notebook/api/me')
        i = self.ids
        plasmid = link('plasmid', i['l1'], i['l1_name'])
        l2 = link('plasmid', i['l2'], i['l2_name'])
        protocol = n.post('/notebook/api/notes', {
            'parent_id': me['library'], 'title': 'Floral dip transformation (Arabidopsis)', 'type': 'protocol', 'content': [
                text('<p>Clough &amp; Bent (1998), simplified. For <i>Agrobacterium</i> GV3101 carrying a binary vector.</p>'),
                steps('Steps', ['Grow plants until the first flowers open; clip the first bolts for more inflorescences.',
                                'Grow the Agrobacterium culture overnight (LB + antibiotics, 28 °C) to OD600 ~1.5.',
                                'Spin down; resuspend in 5% sucrose + 0.02% Silwet L-77.',
                                'Dip the inflorescences for 10 s; keep the plants covered and dark for 24 h.',
                                'Dip again a week later; harvest the seeds when the siliques are dry.']),
                text('<p><b>Selection:</b> sow the T1 seeds on soil, spray Basta (glufosinate) at 7 and 10 days.</p>')]})['note']
        n.put(f'/notebook/api/favorites/{protocol["id"]}')
        say('Notebook: protocol "Floral dip transformation" in the library, starred')

        def page(when, title, content):
            note = n.post('/notebook/api/days', {'date': when})['note']
            child = n.post('/notebook/api/notes', {'parent_id': note['id'], 'title': title, 'content': content})['note']
            return child

        page(day(118), 'Cloning pDEMO-L1 35S:tRFP', [
            text(f'<p>Golden Gate (BsaI) of p35S + tRFP + t35S into the Level 1 acceptor: {plasmid}. '
                 f'Colonies picked; clone 2 sent for sequencing with {link("stock", i["primers"][0], "35S-F")} and '
                 f'{link("stock", i["primers"][1], "tRFP-R")}.</p>'),
            table('Reaction', ['Component', 'Amount'], [['Acceptor (75 ng/µL)', '1 µL'], ['Each part (2:1)', '1 µL'],
                                                        ['BsaI-HFv2', '0.5 µL'], ['T4 ligase', '0.5 µL'], ['Buffer', '1.5 µL'],
                                                        ['Water', 'to 15 µL']])])
        page(day(110), 'Sequencing results and glycerol stocks', [
            text(f'<p>Both reads of clone 2 match {plasmid} (one low-quality call checked on the trace). Kept as '
                 f'{link("stock", i["g1"], i["g1"])} (E. coli). Multigene plasmid {l2} also kept '
                 f'({link("stock", i["g3"], i["g3"])}).</p>')])
        dip = page(day(80), 'Floral dip of Col-0', [
            text(f'<p>Dipped six Col-0 plants ({link("seed", i["col_lot"], i["col_lot"])}) with '
                 f'{link("stock", i["g2"], i["g2"])} (GV3101). Following the library protocol.</p>'),
            steps('Dip', ['Culture to OD600 1.5', 'Resuspend in sucrose + Silwet', 'Dip 10 s', 'Second dip in a week'], done=3)])
        page(day(55), 'T1 selection on Basta', [
            text(f'<p>Sowed 20 T1 seeds of {link("seed", i["t1"], i["t1"])} with Basta '
                 f'({link("stock", i["basta"], "glufosinate")}). Four survived; plant {link("seed", i["t1_keep"][0], i["t1_keep"][0])} '
                 f'founds the independent event {link("seed", i["event"], i["event"])}.</p>'),
            table('Survivors', ['Plant', 'RFP', 'Kept for'], [[i['t1_keep'][0], 'strong', 'event #3, T2 seeds'],
                                                             [i['t1_keep'][1], 'strong', 'T2 seeds'],
                                                             [i['t1_keep'][2], 'strong', 'genotyping'],
                                                             [i['t1_keep'][3], 'weak', 'genotyping']])])
        trial = page(day(26), 'T2 drought trial: sowing', [
            text(f'<p>T2 seeds {link("seed", i["t2"], i["t2"])} segregate 3:1 on Basta (74:26): a single insertion. '
                 'Sowed 12 plants per treatment in Growth chamber 3; drought: watering stopped at day 10.</p>'),
            steps('Plan', ['Sow 12 control + 12 drought', 'Stop watering the drought tray at day 10',
                           'Score flowering time', 'Score height at day 25', 'Image roots on the confocal'], done=4)])
        page(day(1), 'T2 drought trial: results', [
            text(f'<p>Drought plants are shorter (about 15 cm against 25 cm) and flower 3 days earlier: see the phenotype '
                 f'summary of {link("seed", i["t2"], i["t2"])}. Plant {link("seed", i["control"][1], i["control"][1])} is '
                 f'homozygous: its seeds {link("seed", i["t3"], i["t3"])} are all Basta-resistant.</p>')])
        say('Notebook: day pages for cloning, sequencing, dipping, T1 selection and the T2 trial')
        try:
            n.post(f'/notebook/api/notes/{trial["id"]}/shares', {'target_type': 'person', 'target': 'demo-partner'})
            say('the T2 trial page shared with demo-partner, who can add to it')
        except SuiteError as exc:
            say(f'(not shared: {exc})')
        # The partner's own page, about the cross.
        pn = self.partner
        note = pn.post('/notebook/api/days', {'date': day(3)})['note']
        pn.post('/notebook/api/notes', {'parent_id': note['id'], 'title': 'Pollen for the cross with Demo Lab', 'content': [
            text(f'<p>Gave pollen of {link("seed", i["partner_plant"], i["partner_plant"])} (myb21-1) for Demo Lab\'s cross '
                 f'{link("seed", i["f1"], i["f1"])}.</p>')]})
        self.ids.update(protocol=protocol['id'], dip=dip['id'])

    def run(self, only=None):
        for name in ('moclo', 'editor', 'stocks', 'seeds', 'partner_seeds', 'partner_stocks', 'booking', 'notebook'):
            if only and name not in only:
                continue
            print(f'{name.replace("_", " ").title()}:', flush=True)
            getattr(self, name)()


def main():
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser(description='Fill the demo labs with example work.')
    parser.add_argument('--url', default=os.environ.get('SUITE_URL', 'https://localhost:8080'))
    parser.add_argument('--password', default=os.environ.get('DEMO_PASSWORD', 'trellis-demo'))
    parser.add_argument('--insecure', action='store_true', help="don't check the certificate (a local install's own)")
    args = parser.parse_args()
    verify = not args.insecure
    demo = Suite(args.url, verify).sign_in('demo', args.password)
    partner = Suite(args.url, verify).sign_in('demo-partner', args.password)
    if demo.get('/seeds/api/lines')['lines'] or demo.get('/editor/api/sequences?mine=1').get('sequences'):
        sys.exit('The demo already has data: reset it first (demo/demo.sh reset).')
    Demo(demo, partner).run()
    print(f'Done. Sign in at {args.url} as demo (password {args.password}).')


if __name__ == '__main__':
    try:
        main()
    except SuiteError as exc:
        sys.exit(f'Stopped: {exc}')
