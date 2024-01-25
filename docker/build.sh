#!/bin/bash

latest_tag=$(git describe --tags --abbrev=0)

docker build \
  -t tq-docparser:${latest_tag} \
  -f Dockerfile ..
