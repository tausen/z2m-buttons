#!/bin/bash

docker run -d \
   --name z2m-buttons \
   -v /etc/resolv.conf:/etc/resolv.conf:ro \
   --network=host \
   --restart=unless-stopped \
   --env PYTHONUNBUFFERED=1 \
   z2m-buttons
