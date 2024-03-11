#!/bin/bash

latest_tag=$(git describe --tags --abbrev=0)

docker run \
  -d -it \
  --gpus device=1 \
  -e ENABLE_GRADIO=True \
  -e OCR_ALL_PAGES=False \
  -e WORKER_NUM=1 \
  -p 8002:8000 \
  -p 8102:8100 \
  --name tq-docparser \
  tq-docparser:${latest_tag}
