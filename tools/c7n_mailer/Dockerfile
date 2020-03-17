FROM python:3.7-slim-stretch

LABEL name="mailer" \
      description="Cloud Custodian Notification Delivery" \
      repository="http://github.com/cloud-custodian/cloud-custodian" \
      homepage="https://cloudcustodian.io" \
      maintainer="Custodian Community <https://cloudcustodian.io>"

# Transfer Custodian source into container by directory
# to minimize size
ADD setup.py README.md requirements-dev.txt requirements.txt /src/
ADD c7n /src/c7n/
ADD tools /src/tools/

WORKDIR /src
RUN adduser --disabled-login custodian
RUN apt-get --yes update && apt-get --yes upgrade \
 && apt-get --yes install build-essential \
 && pip3 install -r requirements-dev.txt \
 && apt-get --yes remove build-essential \
 && apt-get purge --yes --auto-remove -o APT::AutoRemove::RecommendsImportant=false \
 && rm -Rf /var/cache/apt/ \
 && rm -Rf /var/lib/apt/lists/* \
 && rm -Rf /src/ \
 && rm -Rf /root/.cache/

USER custodian
WORKDIR /home/custodian
ENV LC_ALL="C.UTF-8" LANG="C.UTF-8"
VOLUME ["/home/custodian"]
ENTRYPOINT ["/usr/local/bin/c7n-mailer"]
CMD ["--help"]
