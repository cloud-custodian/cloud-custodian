FROM python:3.6-alpine

RUN apk add --no-cache git
RUN git clone https://github.com/capitalone/cloud-custodian --depth=1 && \
    cd cloud-custodian && \
    pip install -e .
RUN cd cloud-custodian/tools/c7n_mailer && \
    pip install -r ./requirements.txt && \
    pip install -e .
ENTRYPOINT ["c7n-mailer"]
