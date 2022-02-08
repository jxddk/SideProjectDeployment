#!/bin/sh

# recommended by EFF - check for cert renewal every 12 hours
trap exit TERM; while :; do certbot renew; sleep 12h & wait ${!}; done;
