#!/bin/sh

# make some self-signed certs for served domains - these can be replaced by
# certbot later. nginx can't start if it points to non-existent cert files!
# make sure that openssl saves the keys to the same path and filename as certbot
mkdir -p /etc/nginx/ssl/live/localhost/
for DOMAIN in $DOMAINS
do
  if [ -f /etc/nginx/ssl/live/$DOMAIN/privkey.pem ]
  then
    echo $DOMAIN already has certs, skipping
  else
    mkdir -p /etc/nginx/ssl/live/$DOMAIN/
    apk add openssl
    openssl req -x509 -nodes -days 365 -newkey rsa:2048 -keyout /etc/nginx/ssl/live/$DOMAIN/privkey.pem -out /etc/nginx/ssl/live/$DOMAIN/fullchain.pem
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
