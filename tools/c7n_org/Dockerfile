FROM python:3.7

LABEL name="custodian" \
      description="Cloud Management Rules Engine" \
      repository="http://github.com/cloud-custodian/cloud-custodian" \
      homepage="http://github.com/cloud-custodian/cloud-custodian" \
      maintainer="Custodian Community <https://cloudcustodian.io>"

# Note this must be run from the root directory of the checkout
# as we install custodian w/ aws, azure, and gcp support from the same
# repo.

ADD . /src

# Install Custodian Core & AWS
WORKDIR /src
RUN pip2 install -r requirements.txt -e .

# Install Custodian Azure
WORKDIR /src/tools/c7n_azure
RUN pip2 install -r requirements.txt -e .

# Install Custodian GCP
WORKDIR /src/tools/c7n_gcp
RUN pip2 install -r requirements.txt -e .

# Install Custodian Org
WORKDIR /src/tools/c7n_org
RUN pip2 install -e .
ENV LC_ALL="C.UTF-8" LANG="C.UTF-8"

ENTRYPOINT ["c7n-org"]

