#!/bin/bash

POETRY_CMD="poetry run gunicorn \
             service:app \
             -t 600 \
             --workers ${WORKER_NUM} \
             --worker-class uvicorn.workers.UvicornWorker \
             --bind 0.0.0.0:8000"

eval "$POETRY_CMD"
