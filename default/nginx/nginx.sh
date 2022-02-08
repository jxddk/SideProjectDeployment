#!/bin/sh

# make some self-signed certs for served domains - these can be replaced by
# certbot later. nginx can't start if it points to non-existent cert files!
# make sure that openssl saves the keys to the same path and filename as certbot
mkdir -p /etc/nginx/ssl/live/localhost/

# selects domain names based on NGINX configuration, wherever an SSL key is defined
for domain in "$(grep -Erhiwo "/etc/nginx/ssl/live/(.*)/privkey.pem" "/deployment/nginx" "/etc/nginx/nginx.conf" | cut -d "/" -f 6 | sort | uniq)"; do
  domains="${domains:+$domains}$domain"
done
echo Found domains: $domains

for domain in $domains
do
  if [ -f /etc/nginx/ssl/live/$domain/privkey.pem ]
  then
    echo $domain already has certs, skipping
  else
    mkdir -p /etc/nginx/ssl/live/$domain/
    apk add openssl
    echo Generating certs for $domain
    openssl req -x509 -nodes -days 365 -newkey rsa:2048 -keyout /etc/nginx/ssl/live/$domain/privkey.pem -out /etc/nginx/ssl/live/$domain/fullchain.pem -subj "$CSR_SUBJ"
  fi
done
chmod -R 444 /etc/nginx/ssl/live/

# reload the configuration every 6 hours (in case certbot has renewed something)
while true
  do
    nginx -s reload
    sleep 6h
done &

# Overriding the entrypoint with Docker Compose also clears the image command,
# so we call the original entrypoint with its original default argument.
# If you also find this annoying: https://github.com/docker/compose/issues/3140
/docker-entrypoint.sh nginx -g "daemon off;"
