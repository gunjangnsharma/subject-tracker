# Deploy to Oracle Cloud "Always Free"

Host the **production** environment on an Oracle Cloud Always-Free VM. This keeps
your **SQLite** data (it lives on the VM's persistent boot volume — no code
change, no external database). Roughly 20–30 minutes end to end.

Artifacts referenced here live in [`deploy/`](../deploy):
`subject-tracker.service`, `nginx-subject-tracker.conf`, `subject-tracker.env.example`.

> The two things that trip everyone up on Oracle are covered in **steps 2 and 4**:
> you must open the ports in **both** the cloud Security List **and** the VM's own
> firewall (the images ship blocking everything but SSH).

---

## 0. Prerequisites
- An Oracle Cloud account (the Always-Free tier; a card is required to sign up but
  Always-Free resources are never charged).
- Your app pushed to a Git host (e.g. GitHub) so the VM can `git clone` it — or be
  ready to `scp` the folder up. (Commands below assume GitHub; swap in your URL.)
- Optional but recommended for HTTPS: a domain name, or a free one from
  [DuckDNS](https://www.duckdns.org) (`something.duckdns.org`).

## 1. Create the VM
- Console → **Compute → Instances → Create instance**.
- **Shape:** `VM.Standard.A1.Flex` (Ampere/ARM) — pick e.g. 1 OCPU / 6 GB (Always-Free
  eligible). ARM is fine; every dependency here is pure-Python or has ARM wheels.
- **Image:** Canonical **Ubuntu 22.04/24.04** (simplest firewall story).
- **SSH keys:** upload your public key.
- Create, then note the instance's **Public IP address**.

## 2. Open ports at the cloud level (Security List)
- Console → **Networking → Virtual Cloud Networks → (your VCN) → Subnet →
  Security List → Add Ingress Rules**. Add two rules:
  - Source `0.0.0.0/0`, IP Protocol `TCP`, Destination port **80**
  - Source `0.0.0.0/0`, IP Protocol `TCP`, Destination port **443**

## 3. SSH in
```bash
ssh ubuntu@<PUBLIC_IP>
```

## 4. Open the VM's own firewall (the classic Oracle gotcha)
Ubuntu Oracle images keep an `iptables` REJECT rule that blocks 80/443. Open them
and persist:
```bash
sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 80 -j ACCEPT
sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 443 -j ACCEPT
sudo apt-get update && sudo apt-get install -y iptables-persistent
sudo netfilter-persistent save
```
*(Oracle Linux image instead of Ubuntu? Use firewalld:
`sudo firewall-cmd --permanent --add-service=http --add-service=https && sudo firewall-cmd --reload`.)*

## 5. Install system packages
```bash
sudo apt-get install -y python3-venv python3-pip nginx git
```

## 6. Get the app and install it
```bash
cd ~
git clone https://github.com/<you>/<repo>.git
# The app lives in the subject-tracker/ subfolder of that repo:
mv <repo>/subject-tracker ~/subject-tracker   # or clone so the app ends up at ~/subject-tracker
cd ~/subject-tracker
python3 -m venv .venv
./.venv/bin/pip install --upgrade pip
./.venv/bin/pip install -r requirements.txt
mkdir -p ~/subject-tracker-data              # persistent SQLite location
```

## 7. Configure environment (secret + DB path)
```bash
sudo cp deploy/subject-tracker.env.example /etc/subject-tracker.env
# Put a real secret in it:
python3 -c 'import secrets; print("SUBJECT_TRACKER_SECRET=" + secrets.token_hex(32))'
sudo nano /etc/subject-tracker.env          # paste the secret; check the DB path
sudo chmod 600 /etc/subject-tracker.env
```
The DB path in that file is `sqlite:////home/ubuntu/subject-tracker-data/app.db`
(four slashes = absolute path). Data survives restarts and redeploys.

## 8. Run it as a service (systemd + waitress)
```bash
sudo cp deploy/subject-tracker.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now subject-tracker
sudo systemctl status subject-tracker       # should be "active (running)"
curl -sI http://127.0.0.1:5000/login        # 200 / Server: waitress
```
If it fails to start, `journalctl -u subject-tracker -e` shows why (a common cause
is the default secret — prod refuses to boot without a real `SUBJECT_TRACKER_SECRET`).

## 9. Put nginx in front
```bash
sudo cp deploy/nginx-subject-tracker.conf /etc/nginx/sites-available/subject-tracker
sudo sed -i "s/SERVER_NAME/<your-domain-or-PUBLIC_IP>/" /etc/nginx/sites-available/subject-tracker
sudo ln -s /etc/nginx/sites-available/subject-tracker /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t && sudo systemctl reload nginx
```
Now `http://<PUBLIC_IP>/` should load the login page.

## 10. HTTPS (recommended)
Requires a **domain** (or DuckDNS) pointing an A record at `<PUBLIC_IP>`:
```bash
sudo apt-get install -y certbot python3-certbot-nginx
sudo certbot --nginx -d <your-domain>        # obtains + installs the cert, adds redirect
```
Then make sure `SUBJECT_TRACKER_HTTPS=1` in `/etc/subject-tracker.env` and:
```bash
sudo systemctl restart subject-tracker
```
Auto-renewal is installed by certbot (a systemd timer). Test: `sudo certbot renew --dry-run`.

*(No domain yet? Skip step 10 and set `SUBJECT_TRACKER_HTTPS=0` to run plain HTTP —
fine for a quick trial, not for real use.)*

## 11. Create your admin account
Open `https://<your-domain>/register` to make your normal account, then promote one
to admin from the server:
```bash
cd ~/subject-tracker
sudo systemctl stop subject-tracker          # avoid two writers on the SQLite file
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
*(Or register `boss` in the browser first, then just flip its role in a similar
one-off script.)*

---

## Updating to a new version
```bash
cd ~/subject-tracker
git pull                                     # (from wherever you cloned)
./.venv/bin/pip install -r requirements.txt  # if deps changed
sudo systemctl restart subject-tracker
```

## Backups
The database runs in **WAL mode**, so recent commits may still be in the
`app.db-wal` sidecar — a plain `cp app.db` can miss the newest data. Take a
consistent snapshot instead (works while the service is running):
```bash
sqlite3 ~/subject-tracker-data/app.db ".backup '$HOME/backups/app-$(date +%F).db'"
```
If you copy files directly, stop the service and copy `app.db`, `app.db-wal` and
`app.db-shm` together.

Or use the app's **Export JSON** per account. Schema change with no migration?
Adding a defaulted column or an index needs nothing — the app reconciles those at
startup. For anything else: stop the service, delete `app.db`, start again (dev
data is disposable; back up first).

## Operate
- Logs: `journalctl -u subject-tracker -f`
- Restart / stop: `sudo systemctl restart|stop subject-tracker`
- nginx logs: `/var/log/nginx/{access,error}.log`

## Notes & limits
- SQLite + a single process is perfect for personal/low-traffic use. If you ever
  expect real concurrency, switch `SUBJECT_TRACKER_DB` to Postgres (add the
  `psycopg` driver) — SQLAlchemy makes it a one-line change.
- The VM's boot volume is persistent, so your data and the app survive reboots.
- Keep the OS patched: `sudo apt-get update && sudo apt-get upgrade -y` occasionally.
