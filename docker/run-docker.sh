#!/bin/bash

latest_tag=$(git describe --tags --abbrev=0)

docker run \
  -d -it \
  --gpus device=1 \
  -e OCR_ALL_PAGES=False \
  -e WORKER_NUM=4 \
  -p 8002:8000 \
  --name tq-docparser \
  tq-docparser:${latest_tag}
