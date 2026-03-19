#!/bin/bash

docker run \
   --name z2m-buttons \
   -v /etc/resolv.conf:/etc/resolv.conf:ro \
   --network=host \
   --env PYTHONUNBUFFERED=1 \
   --rm \
   -v $(pwd):$(pwd) \
   -w $(pwd) \
   z2m-buttons
