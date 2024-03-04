#!/bin/bash

latest_tag=$(git describe --tags --abbrev=0)

docker run \
  -d -it \
  --gpus device=1 \           # GPU索引
  -e PROD_MODE=False \        # 是否是生产模式：非生产模式将启动 Gradio 前端
  -e OCR_ALL_PAGES=False \    # 是否针对文本强制使用OCR
  -e WORKER_NUM=4 \           # 进程数量
  -p 8002:8000 \              # 批量任务端口
  -p 8102:8100 \              # 非生产模式下 Gradio 端口
  --name tq-docparser \       # 容器名称
  tq-docparser:${latest_tag}  # v1.1.0-rc4
