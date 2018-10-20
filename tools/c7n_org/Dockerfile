FROM pypy:2
MAINTAINER Cloud Custodian Developers http://github.com/capitalone/cloud-custodian

# Note this must be run from the root directory of the checkout
# as we install custodian w/ aws, azure, and gcp support from the same
# repo.

ADD . /src

# Install Custodian Core & AWS
WORKDIR /src
RUN pip2 install -r requirements.txt
RUN pypy setup.py develop

# Install Custodian Azure
WORKDIR /src/tools/c7n_azure
RUN pip2 install -r requirements.txt
RUN pypy setup.py develop

# Install Custodian GCP
WORKDIR /src/tools/c7n_gcp
RUN pip2 install -r requirements.txt
RUN pypy setup.py develop

# Install Custodian Org
WORKDIR /src/tools/c7n_org
RUN pypy setup.py develop
ENV LC_ALL="C.UTF-8" LANG="C.UTF-8"

ENTRYPOINT ["c7n-org"]

