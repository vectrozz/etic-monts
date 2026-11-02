# Host nginx + certificates

Production has a single nginx: the one installed on the VPS, shared with other
sites. Etic'Monts only adds one vhost. Already in place on emb.boblabs.eu —
these steps are for a new server.

```bash
# 1. ACME webroot snippet (once per server, shared by all vhosts)
mkdir -p /var/www/certbot
cp deploy/nginx/acme.conf /etc/nginx/snippets/acme.conf

# 2. Certificate (webroot: nginx keeps running, other sites unaffected).
#    Before the certificate exists, temporarily keep only the :80 server block.
certbot certonly --webroot -w /var/www/certbot -d emb.boblabs.eu

# 3. Vhost
cp deploy/nginx/emb.boblabs.eu.conf /etc/nginx/sites-available/emb.conf
ln -s /etc/nginx/sites-available/emb.conf /etc/nginx/sites-enabled/emb.conf
nginx -t && systemctl reload nginx

# 4. Auto-renewal: the certbot snap ships a systemd timer
systemctl list-timers | grep certbot      # snap.certbot.renew.timer
certbot renew --dry-run
```

The vhost proxies to `127.0.0.1:8085`; change both the vhost and `APP_PORT`
in `.env` together if that port is taken.
