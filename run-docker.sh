#!/bin/bash

docker run \
  -d -it \
  --gpus device=1 \
  -e OCR_ALL_PAGES=False \
  -e WORKER_NUM=4 \
  -v ./model:/marker/model \
  -p 8002:8000 \
  --name pdf-parser \
  marker:1.0
