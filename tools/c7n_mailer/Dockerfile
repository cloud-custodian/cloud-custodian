FROM python:3.7-slim-strech
LABEL name="mailer" \
      description="Cloud Custodian Notification Delivery" \
      repository="http://github.com/cloud-custodian/cloud-custodian" \
      homepage="https://cloudcustodian.io" \
      maintainer="Custodian Community <https://cloudcustodian.io>"

# Assemble custodian bits by parent dir.
ADD setup.py README.rst requirements.txt /src/
ADD c7n /src/c7n/
ADD tools /src/tools/

WORKDIR /src

RUN apt-get --yes update && apt-get --yes upgrade \
 && apt-get --yes install python-dev build-essential \
 && pip3 install -r requirements.txt  . \
 && pip3 install -r tools/c7n_azure/requirements.txt tools/c7n_azure \
 && pip3 install -r tools/c7n_mailer/requirements.txt tools/c7n_mailer \
 && apt-get --yes remove build-essential python-dev \
 && apt-get purge --yes --auto-remove -o APT::AutoRemove::RecommendsImportant=false \
 && rm -Rf /var/cache/apt/ \
 && rm -Rf /var/lib/apt/lists/* \
 && rm -Rf /src/

ENV LC_ALL="C.UTF-8" LANG="C.UTF-8"
ENTRYPOINT ["c7n-mailer"]
