FROM python:3.11.5

WORKDIR /marker
# copy project
COPY . .
# copy local.env
COPY local-prod.env local.env

# install pdf interpreter (ghostscript)
RUN cd scripts/install/ && \
    sh ghostscript_install.sh && \
    cd ../..

# install poetry
RUN pip install poetry
# install nltk
RUN pip install nltk

COPY nltk.tar.gz /tmp/nltk.tar.gz
RUN mkdir -p /root/nltk_data && \
    tar xzf /tmp/nltk.tar.gz -C /

# install poetry dependencies
RUN poetry config installer.max-workers 10
# RUN poetry install --no-root --no-dev
RUN poetry install --no-interaction --no-ansi -vvv

CMD ["poetry", "run", "python3", "service.py"]
