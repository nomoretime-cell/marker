#!/bin/bash

docker run \
  -d -it \
  --gpus device=1 \
  -e OCR_ALL_PAGES=False \
  -e WORKER_NUM=4 \
  -p 8002:8000 \
  --name pdf-parser \
  marker:1.0-model