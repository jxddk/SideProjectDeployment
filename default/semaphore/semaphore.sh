#!/bin/sh
export FILE=/data/data.txt
if [ "$1" == "respond" ]; then
    if test -f "$FILE"; then
        cat "$FILE"
        rm "$FILE"
    fi;
else
    python /deployment/semaphore.py;
fi;
