# Deploy to a Raspberry Pi (3B+ or newer) on your home network

A Pi 3B+ (quad-core, 1 GB RAM) is plenty for this app — it's Flask + SQLite served
by waitress. Data lives on the SD card, so it persists across reboots. This is the
same systemd + (optional) nginx pattern as the Oracle guide, minus the cloud
firewall steps.

Two ways to use it:
- **LAN only** (recommended, simplest, safest) — reach it from phones/laptops on
  your home Wi-Fi. No router changes. §1–§6 below.
- **From anywhere** (internet) — needs router port-forwarding + a domain + HTTPS.
  §7, with the security caveats.

Artifacts referenced here live in [`deploy/`](../deploy). They ship with
`User=ubuntu` and `/home/ubuntu/...` paths — on the Pi you'll change those to your
Pi username (`pi` below; use your own).

---

## 0. Prerequisites
- Raspberry Pi OS installed (64-bit **Bookworm** recommended — ships Python 3.11;
  Bullseye/3.9 also works). SSH enabled (Raspberry Pi Imager can preset this).
- The Pi on your network. Find it: `ping raspberrypi.local` or check your router.
- App pushed to Git (GitHub) so the Pi can `git clone`, or ready to `scp` it over.

SSH in:
```bash
ssh pi@raspberrypi.local        # or ssh pi@<PI_LAN_IP>
```

## 1. Install packages
```bash
sudo apt-get update
sudo apt-get install -y python3-venv python3-pip git sqlite3
```
(`sqlite3` is the command-line tool, used for backups later. It is a *separate*
package from Python's built-in `sqlite3` module, which the app itself uses.)

## 2. Get the app and install it
```bash
cd ~
git clone https://github.com/<you>/<repo>.git
# The app is the subject-tracker/ subfolder of that repo:
mv <repo>/subject-tracker ~/subject-tracker
cd ~/subject-tracker
python3 -m venv .venv
./.venv/bin/pip install --upgrade pip
./.venv/bin/pip install -r requirements.txt
mkdir -p ~/subject-tracker-data          # persistent SQLite location
```

## 3. Environment file (secret + DB path)
```bash
sudo cp deploy/subject-tracker.env.example /etc/subject-tracker.env
python3 -c 'import secrets; print("SUBJECT_TRACKER_SECRET=" + secrets.token_hex(32))'
sudo nano /etc/subject-tracker.env
sudo chmod 600 /etc/subject-tracker.env
```
In that file:
- paste the generated `SUBJECT_TRACKER_SECRET`,
- set `SUBJECT_TRACKER_DB=sqlite:////home/pi/subject-tracker-data/app.db` (four slashes),
- for **LAN-only plain HTTP** set `SUBJECT_TRACKER_HTTPS=0` (turn it to `1` only once
  you add HTTPS in §7).

## 4. Run it as a service (systemd + waitress, bound to the LAN)
Adapt the unit for the Pi user and bind to all interfaces so other devices can reach it:
```bash
sudo cp deploy/subject-tracker.service /etc/systemd/system/
sudo sed -i 's#User=ubuntu#User=pi#; s#Group=ubuntu#Group=pi#' /etc/systemd/system/subject-tracker.service
sudo sed -i 's#/home/ubuntu/#/home/pi/#g' /etc/systemd/system/subject-tracker.service
# LAN access without nginx: bind 0.0.0.0 instead of 127.0.0.1
sudo sed -i 's#--listen=127.0.0.1:5000#--listen=0.0.0.0:5000#' /etc/systemd/system/subject-tracker.service

sudo systemctl daemon-reload
sudo systemctl enable --now subject-tracker
sudo systemctl status subject-tracker      # active (running)
```

## 5. Open it from another device
On any device on the same Wi-Fi:
```
http://raspberrypi.local:5000      (or  http://<PI_LAN_IP>:5000)
```
Register your account at `/register`. Done — that's a working LAN deployment.

> Tip: give the Pi a **static/reserved IP** in your router's DHCP settings so the
> address doesn't change. `raspberrypi.local` (mDNS) also works on most devices.

## 6. Create your admin account
```bash
cd ~/subject-tracker
sudo systemctl stop subject-tracker        # avoid two writers on the SQLite file
SUBJECT_TRACKER_ENV=prod \
SUBJECT_TRACKER_SECRET="$(grep SECRET /etc/subject-tracker.env | cut -d= -f2)" \
SUBJECT_TRACKER_DB="$(grep DB= /etc/subject-tracker.env | cut -d= -f2)" \
./.venv/bin/python - <<'PY'
from tracker import create_app
from tracker.services.auth_service import AuthService
s = create_app().database.Session()
AuthService(s).register("boss", "a-strong-password", role="admin")
print("admin 'boss' created")
PY
sudo systemctl start subject-tracker
```

---

## 7. Optional: reach it from outside your home (with HTTPS)
Only do this if you want access away from home. It exposes the Pi to the internet,
so use HTTPS and strong passwords.

1. **Domain:** get one, or a free `*.duckdns.org` from https://www.duckdns.org, and
   keep it pointed at your home IP (DuckDNS has a cron updater for dynamic IPs).
2. **Router:** forward external TCP **80** and **443** to the Pi's LAN IP.
3. **nginx + waitress:** put nginx in front (so certbot can manage TLS). First switch
   the service back to localhost:
   ```bash
   sudo sed -i 's#--listen=0.0.0.0:5000#--listen=127.0.0.1:5000#' /etc/systemd/system/subject-tracker.service
   sudo systemctl daemon-reload && sudo systemctl restart subject-tracker
   sudo apt-get install -y nginx
   sudo cp deploy/nginx-subject-tracker.conf /etc/nginx/sites-available/subject-tracker
   sudo sed -i "s/SERVER_NAME/<your-domain>/" /etc/nginx/sites-available/subject-tracker
   sudo ln -s /etc/nginx/sites-available/subject-tracker /etc/nginx/sites-enabled/
   sudo rm -f /etc/nginx/sites-enabled/default
   sudo nginx -t && sudo systemctl reload nginx
   ```
4. **Certificate:**
   ```bash
   sudo apt-get install -y certbot python3-certbot-nginx
   sudo certbot --nginx -d <your-domain>
   ```
   Then set `SUBJECT_TRACKER_HTTPS=1` in `/etc/subject-tracker.env` and
   `sudo systemctl restart subject-tracker`.

---

## Updating
```bash
# 1. Snapshot the data first (see Backups below for why not plain cp).
sqlite3 ~/subject-tracker-data/app.db ".backup '$HOME/app-$(date +%F).db'"
# 2. Pull and restart.
cd ~/subject-tracker && git pull
./.venv/bin/pip install -r requirements.txt      # if deps changed
sudo systemctl restart subject-tracker
sudo systemctl status subject-tracker            # confirm "active (running)"
```

**Schema changes need no reset.** New defaulted columns and indexes are applied to
your existing database at startup (`tracker/schema.py`) — that is how the chapter
`position` column and the performance indexes arrived. Only a drop/retype/new
constraint would require recreating the file.

**If it fails to start after an update**, read the log first:
```bash
journalctl -u subject-tracker -e | tail -20
```
`RuntimeError: Refusing to start in production with the default SECRET_KEY` means
`/etc/subject-tracker.env` isn't being read (wrong path, or unreadable by the
service user) — not that the code is broken. Prod deliberately refuses to boot
rather than fall back to the shipped dev secret.

## Backups (do this — SD cards fail eventually)

The database runs in **WAL mode**, so recent commits may still live in the
`app.db-wal` sidecar file. A plain `cp app.db` can therefore miss the newest data
(or capture a torn state). Use one of these instead:

```bash
# Best: let SQLite write a consistent single-file snapshot, even while running.
sqlite3 ~/subject-tracker-data/app.db ".backup '$HOME/app-$(date +%F).db'"

# Also fine (compacts as it copies):
sqlite3 ~/subject-tracker-data/app.db "VACUUM INTO '$HOME/app-$(date +%F).db'"

# Or use the app's per-account "Export JSON" (per user, not the whole DB).
```

No `sqlite3` command (skipped it in §1)? Python can do the same thing — it ships
with the `sqlite3` module:
```bash
python3 - <<PY
import sqlite3, datetime
src = sqlite3.connect("/home/pi/subject-tracker-data/app.db")
dst = sqlite3.connect(f"/home/pi/app-{datetime.date.today()}.db")
with dst: src.backup(dst)          # consistent snapshot, safe while running
print("backed up")
PY
```

If you do copy files directly, stop the service first and copy **all three**:
`app.db`, `app.db-wal`, `app.db-shm`.

**Restoring:** drop the file back and restart — the app reconciles the schema on
boot (`schema.ensure_columns` / `ensure_indexes`), so a snapshot from an older
version opens without a reset:
```bash
sudo systemctl stop subject-tracker
cp ~/app-2026-08-02.db ~/subject-tracker-data/app.db
rm -f ~/subject-tracker-data/app.db-wal ~/subject-tracker-data/app.db-shm
sudo systemctl start subject-tracker
```

## Performance notes (why it's fast on a Pi)
The app tunes SQLite on every connection (see `tracker/database.py`):
- **WAL journal** — readers are never blocked by a write. Without this a single
  delete takes an exclusive lock on the whole file and *every* page load stalls
  behind it, which looks exactly like the UI hanging.
- **`synchronous=NORMAL`** — no fsync per commit. This is the single biggest win
  on SD cards, where each fsync can cost tens of milliseconds.
- **`busy_timeout=5000`** — a second writer waits its turn instead of failing
  with "database is locked".
- **Indexes on every foreign key + the date columns** — SQLite does not create
  these automatically, so without them each ownership check and join is a full
  table scan.

All of it applies to an **existing** database on the next restart: WAL is stored
in the file itself, and `schema.ensure_indexes` creates any missing indexes at
startup. No reset, no manual step.

If the Pi still feels slow, the remaining known cost is per-page query count
(N+1 relationship loading) and the 200 KB Chart.js bundle being sent on every
page — see BUILD_CONTEXT §16.

## Pi-specific notes
- **SD card longevity:** this app writes rarely, so SD wear is a non-issue for years.
  If you want extra safety, put `~/subject-tracker-data` on a USB stick/SSD and point
  `SUBJECT_TRACKER_DB` there.
- **Keep it patched:** `sudo apt-get update && sudo apt-get upgrade -y` now and then.
- **Logs:** `journalctl -u subject-tracker -f`.
- **Python:** needs 3.9+ (Bookworm's 3.11 is ideal). Nothing in this app needs a
  newer runtime, and every dependency is pure-Python or has ARM wheels.
