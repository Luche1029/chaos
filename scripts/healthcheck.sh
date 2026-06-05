#!/bin/bash

LOGFILE="/opt/chaos/logs/healthcheck.log"
DATE=$(date '+%Y-%m-%d %H:%M:%S')

# controlla tutti i container in esecuzione
CONTAINERS=$(docker ps --format '{{.Names}}')

if [ -z "$CONTAINERS" ]; then
    echo "[$DATE] Nessun container attivo" >> $LOGFILE
else
    for CONTAINER in $CONTAINERS; do
        STATUS=$(docker inspect --format='{{.State.Health.Status}}' $CONTAINER 2>/dev/null || echo "running")
        echo "[$DATE] $CONTAINER: $STATUS" >> $LOGFILE
    done
fi

# riavvia container non in running
docker ps -a --filter "status=exited" --format '{{.Names}}' | while read NAME; do
    echo "[$DATE] Riavvio $NAME..." >> $LOGFILE
    docker start $NAME
done
