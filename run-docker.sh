#!/bin/bash

docker run --gpus device=1 -d -it -v ./model:/marker/model -p 8002:8000 --name pdf-parser marker:1.0