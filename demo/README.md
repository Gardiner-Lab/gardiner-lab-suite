# The teaching demo

A demo chair group, two labs and two accounts, filled with one connected piece
of work in every tool: for people who want to see how Trellis Tools works
before using it for real, or for teaching a class.

```bash
make demo          # or demo/demo.sh load: make the accounts and labs, fill them
make demo-reset    # remove the demo's data and fill it again, e.g. before a class
make demo-wipe     # remove the demo's data and leave it empty
```

Run them on the server, in the suite's folder, with the suite running. They
need Docker (as for the suite) and Python 3, nothing else.

## Who

| Account        | Password       | In                                   | Sees                                           |
|----------------|----------------|--------------------------------------|------------------------------------------------|
| `demo`         | `trellis-demo` | Demo Lab, as its lab admin           | everything below; adds equipment, manages the lab |
| `demo-partner` | `trellis-demo` | Demo Partner Lab, as a member        | its own lab, and what Demo Lab shares          |

Both labs are in the **Demo Chair Group**, so each sees the other's seeds,
stocks and shared equipment, without changing them. Give learners `demo`;
sign in as `demo-partner` to show the other side of sharing.

The two are **shared teaching accounts**: their passwords cannot be changed
from the dashboard, so one person cannot lock the others out. Choose another
password with `DEMO_PASSWORD=... make demo`. To offer the demo to anyone on the
sign-in page ("Just looking? Try the demo lab", with a button that fills it in),
load it with `DEMO_SHOW_ON_LOGIN=1 make demo`; loading it again without that
takes the offer away.

## What is in it

Demo Lab builds a red fluorescent reporter (tRFP) and puts it into Arabidopsis.
Dates are counted back from the day it is loaded, so plants have the right ages
and bookings fall in the current week.

- **MoClo**: three transcription units from MoClo's own demo parts, a Level 1
  plasmid (35S:tRFP) and a Level 2 plasmid with all three; two of them saved on
  the dashboard's *Saved constructs*.
- **Plasmid Editor**: both plasmids, linked to MoClo; two sequencing reads of
  clone 2, judged and confirmed; a home-made gel ladder (shared in the chair
  group); an enzyme list.
- **Lab Stocks**: glycerol stocks of the plasmids (E. coli, and Agrobacterium for
  dipping), primers, chemicals (Silwet has run out), antibodies, leaf DNA from
  the T1 plants, and orders: urgent, ordered, received. The partner lab's
  Hygromycin and anti-GFP show, read-only.
- **Seed Bank**: two places; Col-0 from NASC, dipped; T1 seeds selected on
  Basta (4 of 20 survive); an independent event founded from one; T2 seeds
  segregating 3:1; a T2 drought trial (12 control, 12 drought) scored for
  height, flowering time and fluorescence, so the phenotype summary compares
  the treatments; a homozygous T3; a cross with the partner lab's *myb21-1*
  mutant (their plant as the father). Every record has its family tree, from
  the plasmid and its stocks on.
- **Lab Notebook**: day pages for each step (cloning, sequencing, dipping, T1
  selection, the trial), with links to the plasmids, stocks and seeds; a
  protocol in the library, starred; the trial page shared with `demo-partner`,
  who can add to it; the partner's own page about the cross; and a page for
  each day with a booking.
- **Booking**: a confocal microscope and a PCR machine (shared with the chair
  group) and a meeting room; bookings this week and next, with people tagged,
  and a weekly lab meeting. The partner books the microscope too.

## Resetting

`make demo-reset` removes everything the demo labs and accounts made, in every
tool, and loads the demo again. It touches nothing else: other labs' records,
MoClo's own demo parts library and everyone's accounts stay as they are. The
demo labs keep their codes (`DEMO-`), and their numbering starts again at 0001.
Setting the passwords again signs out anyone signed in as the demo.

What it removes, tool by tool, is listed at the top of [wipe.py](wipe.py).

## How it works

- [accounts.py](accounts.py) runs inside the sign-in service, as the server's
  operator: it makes the chair group, labs and accounts with the suite's own
  functions, so no administrator password is needed.
- [load.py](load.py) signs in as the two accounts and makes everything through
  the tools' own web API, as a person would, so the demo always follows the
  tools' rules. It stops if the demo already has data.
- [wipe.py](wipe.py) runs inside each tool's container and removes the demo's
  rows from its database.

`load.py` also runs from another computer against a server whose demo accounts
exist: `python3 demo/load.py --url https://lab.example.org`.
