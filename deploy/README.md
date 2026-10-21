# Raspberry Pi deployment with ngrok

The current deployment runs on Debian 13 ARM64 at `192.168.10.51`:

**https://overkill-trustee-conjuror.ngrok-free.dev**

Traffic flows through ngrok's HTTPS endpoint to Nginx on `127.0.0.1:8080`,
then Gunicorn on `127.0.0.1:8765`. Both local listeners stay private.
No No-IP record, router port forwarding, or local TLS certificate is needed.
The free ngrok plan displays a browser warning and has usage limits.

Run these commands on the Pi in Bash, not Windows PowerShell. These are rebuild
instructions; the live Pi is already configured. Leave `/mnt/techpulse/app`,
other services, and existing firewall rules unchanged. Change default passwords
before publishing the site, and keep the OS patched.

For No-IP, port forwarding, and locally managed certificates instead, see
[direct hosting](DIRECT-HOSTING.md).

## 1. Install the application and ngrok

Inspect existing paths, accounts, and listeners before installing anything.
If a path/account below already exists or ports 8080/8765 are occupied, stop and
inspect it rather than overwriting or stopping another service.

```bash
sudo ss -lntup
sudo apt update
sudo apt install git python3 gunicorn nginx
sudo git clone https://github.com/asylvestro34/OpticFinder.git /opt/opticfinder
sudo useradd --system --user-group --no-create-home --shell /usr/sbin/nologin opticfinder
sudo useradd --system --user-group --no-create-home --shell /usr/sbin/nologin opticfinder-ngrok
```

Install the Linux ARM64 agent using the official
[ngrok download instructions](https://ngrok.com/download/linux). This deployment
expects the executable at `/usr/local/bin/ngrok`. Confirm with:

```bash
/usr/local/bin/ngrok version
```

The source remains administrator-owned; neither service account can modify it.
No global pip install or Python virtual environment is needed.

## 2. Save the token privately

Create an ngrok account and obtain its authtoken from **Credentials > Authtokens**.
Run as your normal Pi login user. The hidden prompt keeps the token out of shell
history; do not paste tokens into Git, logs, or chat.

```bash
read -rsp 'Ngrok authtoken: ' NGROK_TOKEN; echo
ngrok config add-authtoken "$NGROK_TOKEN"
unset NGROK_TOKEN
chmod 600 ~/.config/ngrok/ngrok.yml
sudo install -d -o root -g opticfinder-ngrok -m 750 /etc/opticfinder-ngrok
sudo install -o root -g opticfinder-ngrok -m 640 \
  ~/.config/ngrok/ngrok.yml /etc/opticfinder-ngrok/ngrok.yml
sudo -u opticfinder-ngrok /usr/local/bin/ngrok config check \
  --config=/etc/opticfinder-ngrok/ngrok.yml
```

Only the token-bearing configuration stays outside the repository. The tunnel
runs under its own unprivileged account with request inspection disabled.

## 3. Install the services and localhost proxy

The three `ngrok`/`tunnel` files below use the current assigned hostname.
For another ngrok account, replace that hostname in all three files with the
one shown under **Domains** in your dashboard before installing them.
The backend origin must match the public HTTPS URL exactly.

```bash
cd /opt/opticfinder
sudo -u opticfinder python3 -B -m unittest discover -s tests -q
sudo install -m 644 deploy/opticfinder.service /etc/systemd/system/opticfinder.service
sudo install -d -m 755 /etc/systemd/system/opticfinder.service.d
sudo install -m 644 deploy/opticfinder.ngrok-origin.conf \
  /etc/systemd/system/opticfinder.service.d/origin.conf
sudo install -m 644 deploy/opticfinder.tunnel.conf /etc/nginx/sites-available/opticfinder-tunnel
sudo ln -s /etc/nginx/sites-available/opticfinder-tunnel /etc/nginx/sites-enabled/opticfinder-tunnel
sudo install -m 644 deploy/opticfinder-ngrok.service /etc/systemd/system/opticfinder-ngrok.service
sudo nginx -t
sudo systemd-analyze verify /etc/systemd/system/opticfinder-ngrok.service
sudo systemctl daemon-reload
sudo systemctl enable --now opticfinder nginx
sudo systemctl reload nginx
curl --fail -H 'Host: overkill-trustee-conjuror.ngrok-free.dev' http://127.0.0.1:8080/health
```

Stop if validation or the local health request fails. Expected JSON:
`{"status": "ok"}`. Then publish:

```bash
sudo systemctl enable --now opticfinder-ngrok
sudo systemctl status opticfinder-ngrok --no-pager
```

Nginx caps bodies at 8KB, with an aggregate limit of 5 requests/second,
a burst of 30, and 10 concurrent proxied connections across all visitors.
These conservative limits are shared, not per visitor: the local tunnel is the
proxy's client. Client-supplied forwarding headers are not trusted for limiting.
They reduce casual abuse, not large-scale DDoS.

The earlier direct-hosting bootstrap and packaged Nginx default site may still
listen on port 80 on the existing Pi; neither is used by this tunnel.
Do not open or forward ports 80, 443, 8080, 8765, SSH, or other Pi services for
this deployment. Do not reset the host firewall or stop shared Nginx.

## 4. Check the public site

```bash
curl --fail -H 'ngrok-skip-browser-warning: true' \
  https://overkill-trustee-conjuror.ngrok-free.dev/health
curl --fail https://overkill-trustee-conjuror.ngrok-free.dev/api/plan \
  -H 'ngrok-skip-browser-warning: true' \
  -H 'Content-Type: application/json' \
  -H 'Origin: https://overkill-trustee-conjuror.ngrok-free.dev' \
  --data '{"endpoint_a":"ms130-24x","endpoint_b":"ms130-24x","interface_a":"sfp-uplink","interface_b":"sfp-uplink","speed_gbps":10,"distance_m":30,"cable_type":"OM3"}'
```

From a phone on cellular data, open the site, continue past ngrok's warning,
check a connection, and visit the cable reference page. The request-header
workaround above is for command-line clients; the app cannot remove the initial
browser warning. Ngrok requires a paid plan to remove it for normal visitors.
During a maintenance window, reboot and confirm this app and the existing
service recover.

## Updates and troubleshooting

```bash
cd /opt/opticfinder
sudo git status --short
sudo git pull --ff-only
sudo -u opticfinder python3 -B -m unittest discover -s tests -q
sudo systemctl restart opticfinder
curl --fail -H 'Host: overkill-trustee-conjuror.ngrok-free.dev' http://127.0.0.1:8080/health
```

Stop if the worktree has unexpected edits, the pull fails, or tests fail.
A pull does not reinstall service/proxy files. Review those changes separately,
validate Nginx/systemd configuration, reload systemd, and restart/reload only
affected services. Maintain the ngrok agent using its official update procedure.

Inspect service status with `sudo systemctl status opticfinder opticfinder-ngrok nginx --no-pager`
and logs with `sudo journalctl -u opticfinder -u opticfinder-ngrok -n 50 --no-pager`.
Do not share logs/configuration without checking for secrets.
Use `sudo nginx -t` and `sudo ss -lntp` to check the proxy and loopback listeners.

To remove public access without disturbing other services:

```bash
sudo systemctl disable --now opticfinder-ngrok
```

To rotate the token, revoke it in ngrok, repeat the private token installation,
and restart `opticfinder-ngrok`. For a hostname change, update the origin
override, tunnel unit, and Nginx tunnel site together before restarting.
