# Raspberry Pi public deployment

For Debian 13 ARM64, Python 3.13, Pi `192.168.10.51`, and
`opticfinder.ddns.net`. Uses Debian-packaged Gunicorn, Nginx, Certbot, and
systemd. The local development server is not used.

Run the commands below on the Pi in Bash. Do not run them in Windows PowerShell.
Keep the existing `/mnt/techpulse/app` service and its configuration unchanged.
Deployment files must first be available in the GitHub repository you clone.

## 1. Network prerequisites

- Reserve `192.168.10.51` for the Pi in UniFi's DHCP/client settings.
- Confirm the Dream Machine has a public WAN IPv4 address. Private WAN addresses
  or `100.64.0.0/10` can indicate upstream NAT/CGNAT; resolve that with the ISP.
- Create the No-IP hostname and configure No-IP DDNS on the Dream Machine's WAN.
  Use dedicated DDNS credentials where available. Do not store them in this repo.
- The hostname's A record must resolve to your public WAN IPv4. Do not publish an
  AAAA record unless you separately configure and secure IPv6 access.
- Confirm inbound TCP 80/443 are permitted by the ISP and are not already
  forwarded to another device.
- Keep the Pi patched. Prefer an isolated VLAN with restricted access to your
  private LAN; account for the existing service's needs before changing networks.

Do not forward SSH, RPC, remote desktop, Docker services, or port 8765. Do not
use the router's DMZ-host feature. Public access here is anonymous and read-only
apart from stateless planning requests; there are no accounts or saved plans.

## 2. Install in a separate directory

First inspect existing services; if 80, 443, or 8765 is occupied, stop and resolve
the conflict without killing the other service.

```bash
sudo ss -lntup
sudo apt update
sudo apt install git python3 gunicorn nginx certbot
```

If `/opt/opticfinder` already exists, inspect it instead of overwriting it.
Otherwise:

```bash
sudo git clone https://github.com/asylvestro34/OpticFinder.git /opt/opticfinder
sudo useradd --system --user-group --no-create-home --shell /usr/sbin/nologin opticfinder
sudo -u opticfinder /usr/bin/python3 -c 'import sys; sys.path.insert(0, "/opt/opticfinder"); from opticfinder.engine import load_catalog; print(len(load_catalog()["endpoints"]))'
```

Expected output: `37`. If the account already exists, inspect it before reusing
it; do not recreate it or change an unrelated service account.
The source stays administrator-owned; the backend account cannot modify it.
No virtual environment or global pip install is needed for this Debian deployment.

## 3. Start the localhost backend

```bash
sudo install -m 644 /opt/opticfinder/deploy/opticfinder.service /etc/systemd/system/opticfinder.service
sudo systemctl daemon-reload
sudo systemctl enable --now opticfinder
sudo systemctl status opticfinder --no-pager
curl --fail -H 'Host: opticfinder.ddns.net' http://127.0.0.1:8765/health
```

Expected JSON: `{"status": "ok"}`. The backend listens only on `127.0.0.1:8765`.
Service errors: `sudo journalctl -u opticfinder -n 50 --no-pager`.

## 4. Prepare HTTP certificate validation

These are dedicated site files, not replacements for the global Nginx config.
If an `opticfinder` site/service/snippet already exists, inspect it before
installing these files. Leave other sites and services unchanged.

```bash
sudo install -d -m 755 /var/www/opticfinder-acme
sudo install -m 644 /opt/opticfinder/deploy/opticfinder.nginx.conf /etc/nginx/sites-available/opticfinder
sudo install -m 644 /opt/opticfinder/deploy/opticfinder.proxy.conf /etc/nginx/snippets/opticfinder.proxy.conf
sudo ln -s /etc/nginx/sites-available/opticfinder /etc/nginx/sites-enabled/opticfinder
sudo nginx -t && sudo systemctl enable --now nginx && sudo systemctl reload nginx
```

The bootstrap site intentionally returns HTTP 503 except for certificate
validation. It does not expose the backend over unencrypted HTTP.
Nginx's packaged default site can remain; the named site handles this hostname.

## 5. Configure the Dream Machine and host firewall

Add only these two forwards:

| WAN port | Protocol | Forward IP | Forward port |
|---|---|---|---|
| 80 | TCP | 192.168.10.51 | 80 |
| 443 | TCP | 192.168.10.51 | 443 |

UniFi Network 9.4: Settings > Policy Engine > Port Forwarding.
Network 9.3: Settings > Policy Table > Create New Policy > Port Forwarding.
Other versions may place this under routing/firewall settings.
Choose the correct WAN and allow any source for an anonymous public site.

If the Pi has an active host firewall, allow inbound TCP 80/443 using the
existing firewall manager. Do not flush nftables/iptables, reset UFW, or enable
a new firewall blindly: the Pi also runs SSH, remote desktop, RPC, and Docker.
Preserve LAN administration, allow return traffic and outbound DNS/HTTPS, and
do not open those other services to the internet. IPv6 needs its own policy.

Verify DNS from an external resolver and test from cellular data, not just Wi-Fi.
No-IP does not bypass CGNAT or blocked ISP ports. Free No-IP hostnames may need
periodic confirmation depending on your plan.

## 6. Issue the certificate and activate HTTPS

Replace the example email with your real certificate contact email:

```bash
sudo certbot certonly --webroot -w /var/www/opticfinder-acme \
  --cert-name opticfinder.ddns.net -d opticfinder.ddns.net \
  --email YOUR_EMAIL@example.com --agree-tos
```

Only after certificate issuance succeeds:

```bash
sudo install -m 644 /opt/opticfinder/deploy/opticfinder.https.conf /etc/nginx/sites-available/opticfinder
sudo nginx -t && sudo systemctl reload nginx
```

This enables HTTPS and HTTP-to-HTTPS redirects. Request bodies are capped at 8KB;
per-IP requests are limited to 5/second with a burst of 30, and 10 concurrent
proxied connections. These limits reduce casual abuse, not large-scale DDoS.
Users sharing a public IP share these limits.

Set up Nginx reloads after certificate renewal:

```bash
sudo install -d -m 755 /etc/letsencrypt/renewal-hooks/deploy
printf '%s\n' '#!/bin/sh' '/usr/sbin/nginx -t && /usr/bin/systemctl reload nginx' \
  | sudo tee /etc/letsencrypt/renewal-hooks/deploy/opticfinder-reload-nginx >/dev/null
sudo chmod 755 /etc/letsencrypt/renewal-hooks/deploy/opticfinder-reload-nginx
sudo systemctl enable --now certbot.timer
sudo certbot renew --dry-run
```

Keep TCP 80 available for renewal. Certificates and keys stay under
`/etc/letsencrypt`, never in Git.

## 7. Check the public site

```bash
curl --fail https://opticfinder.ddns.net/health
curl --fail https://opticfinder.ddns.net/api/plan \
  -H 'Content-Type: application/json' \
  -H 'Origin: https://opticfinder.ddns.net' \
  --data '{"endpoint_a":"ms130-24x","endpoint_b":"ms130-24x","interface_a":"sfp-uplink","interface_b":"sfp-uplink","speed_gbps":10,"distance_m":30,"cable_type":"OM3"}'
```

From a phone with Wi-Fi disabled, open `https://opticfinder.ddns.net`, check a
connection, and visit the reference page. A homepage alone is not enough to
verify the API. During a maintenance window, reboot the Pi and confirm both
OpticFinder and the pre-existing service recover.

Troubleshooting:
- `sudo journalctl -u opticfinder -n 50 --no-pager`
- `sudo tail -n 50 /var/log/nginx/error.log`
- `sudo nginx -t`
- `sudo ss -lntp` (backend must remain on localhost)

## Updates and rollback

Keep OS packages updated using your existing maintenance policy. For app updates:

```bash
cd /opt/opticfinder
sudo git status --short
sudo git pull --ff-only
sudo -u opticfinder /usr/bin/python3 -B -m unittest discover -s tests -q
sudo systemctl restart opticfinder
curl --fail -H 'Host: opticfinder.ddns.net' http://127.0.0.1:8765/health
```

Stop if the pull or tests fail. Review deployment-file changes separately; a
pull does not reinstall systemd/Nginx configuration. For a quick public-access
rollback, disable the two OpticFinder port-forwarding rules on the Dream Machine.
Do not stop shared Nginx or change the other Pi service.

If changing the hostname, update the service origin, both site configs, and
certificate paths, issue a certificate for the new name, then validate and reload.
