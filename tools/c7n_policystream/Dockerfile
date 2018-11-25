FROM ubuntu:cosmic

LABEL name="c7n-policystream" \
      description="Custodian policy changes streamed from Git" \
      repository="http://github.com/capitalone/cloud-custodian" \
      homepage="http://github.com/capitalone/cloud-custodian" \
      maintainer="Kapil Thangavelu <http://twitter.com/kapilvt>"

# Note this must be run from the root directory of the checkout
# as we install custodian w/ aws, azure, and gcp support from the same
# repo.

RUN apt-get update && apt-get install -y libgit2-dev python3-pip

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

# Install PolicyStream Tool
WORKDIR /src/tools/c7n_policystream
RUN pip3 install -r requirements.txt -e .
ENV LC_ALL="C.UTF-8" LANG="C.UTF-8"
VOLUME ["/repos/"]
ENTRYPOINT ["c7n-policystream"]

