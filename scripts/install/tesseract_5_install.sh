#!/bin/bash

apt-get install apt-transport-https
# echo "deb https://notesalexp.org/tesseract-ocr5/$(lsb_release -cs)/ $(lsb_release -cs) main" \
# | tee /etc/apt/sources.list.d/notesalexp.list > /dev/null
apt-get update -oAcquire::AllowInsecureRepositories=true
apt-get install notesalexp-keyring -oAcquire::AllowInsecureRepositories=true
apt-get update
yes | apt-get install tesseract-ocr
