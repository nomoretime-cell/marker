#!/bin/bash

docker run --gpus device=1 -d -it -e OCR_ALL_PAGES=False -v ./model:/marker/model -p 8002:8000 --name pdf-parser marker:1.0