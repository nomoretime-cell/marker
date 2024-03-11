#!/bin/bash

if [ "$ENABLE_GRADIO" == "True" ]; then
    POETRY_FRONT_END_CMD="poetry run python front_end.py"
    eval "$POETRY_FRONT_END_CMD" &
fi

POETRY_GUNICORN_CMD="poetry run gunicorn \
            service:app \
            --timeout 7200 \
            --workers ${WORKER_NUM} \
            --worker-class uvicorn.workers.UvicornWorker \
            --bind 0.0.0.0:8000"

eval "$POETRY_GUNICORN_CMD"
