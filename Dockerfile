FROM python:3.7

LABEL name="custodian" \
      description="Cloud Management Rules Engine" \
      repository="http://github.com/cloud-custodian/cloud-custodian" \
      homepage="http://github.com/cloud-custodian/cloud-custodian" \
      maintainer="Custodian Community <https://cloudcustodian.io>"

ADD . /src

# Install Custodian Core & AWS
WORKDIR /src
RUN pip3 install -r requirements.txt -e .

# Install Custodian Azure
WORKDIR /src/tools/c7n_azure
RUN pip3 install -r requirements.txt -e .

# Install Custodian GCP
WORKDIR /src/tools/c7n_gcp
RUN pip3 install -r requirements.txt -e .

# Setup for EntryPoint
ENV LC_ALL="C.UTF-8" LANG="C.UTF-8"
VOLUME ["/var/log/cloud-custodian", "/etc/cloud-custodian"]
ENTRYPOINT ["/usr/local/bin/custodian"]
