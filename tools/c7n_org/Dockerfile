FROM python:3.7-slim-stretch

LABEL name="c7n-org" \
      description="Cloud Custodian Organization Runner" \
      repository="http://github.com/cloud-custodian/cloud-custodian" \
      homepage="http://github.com/cloud-custodian/cloud-custodian" \
      maintainer="Custodian Community <https://cloudcustodian.io>"

# Transfer Custodian source into container by directory
# to minimize size.
# Note: build root is the root of the checkout.
ADD setup.py README.rst requirements.txt /src/
ADD c7n /src/c7n/
ADD tools /src/tools/

WORKDIR /src

RUN apt-get --yes update && apt-get --yes upgrade \
 && apt-get --yes install build-essential \
 && pip3 install -r requirements.txt  . \
 && pip3 install -r tools/c7n_gcp/requirements.txt tools/c7n_gcp \
 && pip3 install -r tools/c7n_azure/requirements.txt tools/c7n_azure \
 && pip3 install tools/c7n_org \
 && apt-get --yes remove build-essential \
 && apt-get purge --yes --auto-remove -o APT::AutoRemove::RecommendsImportant=false \
 && rm -Rf /var/cache/apt/ \
 && rm -Rf /var/lib/apt/lists/* \
 && rm -Rf /src/ \
 && rm -Rf /root/.cache/

ENV LC_ALL="C.UTF-8" LANG="C.UTF-8"
ENTRYPOINT ["/usr/local/bin/c7n-org"]
