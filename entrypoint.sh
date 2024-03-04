#!/bin/bash

if [ "$PROD_MODE" == "True" ]; then
    POETRY_CMD="poetry run gunicorn \
                service:app \
                --timeout 7200 \
                --workers ${WORKER_NUM} \
                --worker-class uvicorn.workers.UvicornWorker \
                --bind 0.0.0.0:8000"
else
    POETRY_CMD="poetry run python front_end.py"
fi

eval "$POETRY_CMD"
