# HTTPS

The suite is served over **https** on its port (`SUITE_PORT`, 8080 by
default): `https://<this machine>:8080/`. Plain `http://` to the same port is
sent on to `https://`, so old bookmarks keep working.

## The lab's certificate

`install.sh` (or `./scripts/make-certs.sh` on its own) makes two certificates:

| File | What it is |
| --- | --- |
| `certs/lab-suite-ca.crt` | The lab's own **certificate authority**. Computers trust this, once. |
| `certs/suite.crt`, `certs/suite.key` | This machine's certificate, signed by the authority. The proxy serves it. |
| `certs-ca/lab-suite-ca.key` | The authority's key. It never leaves this machine, and the proxy never sees it. |

The machine's certificate is for `localhost`, `127.0.0.1` and the machine's
name, short and full. Add other names or addresses (its IP address, or the
name the university's DNS gives it) to `SUITE_HOSTNAMES` in `.env`,
comma-separated, then run `./scripts/make-certs.sh` and `make restart-proxy`.
It lasts 825 days. `install.sh` makes a new one when the names change or it
has less than 30 days left. The authority lasts ten years.

**Keep a copy of `certs-ca/` somewhere safe** (not in the lab's shared
backup: it is a key). With it, a reinstalled machine keeps the same authority
and nobody has to trust anything again; without it, a new authority is made
and every computer trusts that one instead.

## Trusting it, once per computer

Until a computer trusts the lab's authority, its browser warns that the
connection is not private. To trust it, download the authority's certificate
from the suite. No sign-in is needed:

    https://<this machine>:8080/lab-suite-ca.crt

(The browser warns once on the way there; continue to the site.) Then:

**Windows** (Chrome, Edge). No administrator rights are needed:

1. Open the downloaded `lab-suite-ca.crt` and choose **Install Certificate…**
2. **Current User**, Next.
3. **Place all certificates in the following store**, Browse, **Trusted Root
   Certification Authorities**, OK, Next, Finish.
4. Windows asks whether to install a certificate from "Trellis Tools
   authority": **Yes**.
5. Close the browser completely and open it again.

**macOS** (Safari, Chrome, Edge):

1. Open `lab-suite-ca.crt`; it goes into Keychain Access, **login** keychain.
2. Double-click "Trellis Tools authority", open **Trust**, and set
   **When using this certificate** to **Always Trust**. Close the window and
   give your password.

**Firefox** (any system) keeps its own list. Either set
`security.enterprise_roots.enabled` to `true` in `about:config`, so it uses the
system's (after the steps above), or: Settings, Privacy & Security,
Certificates, **View Certificates…**, Authorities, **Import…**, choose the file,
and tick **Trust this CA to identify websites**.

**Linux** (Chrome, Chromium): Settings, Privacy and security, Security,
**Manage certificates**, Authorities, **Import**, and tick **Trust this
certificate for identifying websites**.

**Phones and tablets** (for labels' QR codes): open the address on the device,
download the certificate, and install it as a CA certificate (Android:
Settings, Security, Encryption & credentials, Install a certificate, CA
certificate; iPhone and iPad: install the profile in Settings, then turn it on
under General, About, **Certificate Trust Settings**).

The authority only vouches for this suite's machine: it was made here, and
its key never leaves `certs-ca/`.

## A certificate from the university instead

A certificate from UU's IT for the machine's name needs no trusting on any
computer. Put it in `certs/suite.crt` (with any intermediate certificates
after it, in the same file) and its key in `certs/suite.key`, then:

    touch certs/.provided      # make-certs.sh leaves them alone from now on
    make restart-proxy

## A public address

To reach the suite from outside the lab at a name of its own, say
`https://lab.example.org`:

1. **The name and the port.** The name points at this machine, and port 443
   is open to it (at UU, through IT). Set `SUITE_PORT=443` in `.env`, so the
   address needs no port, and `docker compose up -d`.
2. **A certificate for that name** that every browser trusts: one from UU IT
   or a public authority such as Let's Encrypt, put in as above. The lab's own
   authority is fine inside the lab, but visitors from outside will not have
   trusted it.
3. **The dashboard's Hosting tab** (administrators): set the public address,
   and decide who may register. Label QR codes then open that address, and on
   it browsers are told to use https only (HSTS, for a year from each visit;
   only on that name, never on `localhost` or the machine's own name). The tab
   also checks, each time it is opened, the certificate the proxy serves for
   the address, sign-in cookies, registration, administrators still on the
   published default password, and the last backup.

Password guessing is limited twice: the proxy lets any one address try to sign
in or register at most 10 times a minute (a burst of 10 more), and the sign-in
service stops an address after 10 wrong passwords for one account, for 15
minutes (`SIGNIN_GUESSES`, `SIGNIN_GUESS_MINUTES`). Only that address waits:
someone guessing cannot lock the person out. If the suite sits behind another
proxy (a university load balancer), tell nginx its address first
(`set_real_ip_from`, `real_ip_header`), or every visitor shares it.

## Checking

`make check` connects over https trusting the lab's authority, so it also
checks that the certificate is valid for `localhost`. It checks that plain
http is sent on to https, and that the authority's certificate can be
downloaded without signing in.
