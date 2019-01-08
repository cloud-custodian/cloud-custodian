FROM python:2.7

ADD . /src
WORKDIR /src
RUN pip install -r requirements.txt -e .
RUN python setup.py develop

# Install Custodian Azure
WORKDIR /src/tools/c7n_azure
RUN pip install -r requirements.txt -e .
RUN python setup.py develop

# Install Custodian GCP
WORKDIR /src/tools/c7n_gcp
RUN pip install -r requirements.txt -e .
RUN python setup.py develop

RUN pip install future

VOLUME ["/var/log/cloud-custodian", "/etc/cloud-custodian"]

ENTRYPOINT ["/usr/local/bin/custodian"]
