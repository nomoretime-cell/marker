FROM python:3.11.5

WORKDIR /marker
# copy project
COPY marker/ /marker/marker
COPY *.py poetry.lock pyproject.toml ./
COPY local-prod.env local.env
COPY nltk.tar.gz /tmp/nltk.tar.gz
RUN mkdir -p /root/nltk_data && \
    tar xzf /tmp/nltk.tar.gz -C /

# ocrmypdf dependencies
RUN apt-get update && \
    yes | apt-get install tesseract-ocr && \
    yes | apt-get install ghostscript

# install poetry
RUN pip install poetry
# install nltk
RUN pip install nltk
# install poetry dependencies
RUN poetry config installer.max-workers 20
# RUN poetry install --no-root --no-dev
RUN poetry install --no-interaction --no-ansi -vvv --no-root --no-dev && \
    rm -rf /root/.cache/pypoetry/artifacts /root/.cache/pypoetry/cache

CMD ["poetry", "run", "python3", "service.py"]
