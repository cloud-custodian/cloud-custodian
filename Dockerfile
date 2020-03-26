FROM python:3.8-slim-buster

LABEL name="custodian" \
      description="Cloud Management Rules Engine" \
      repository="http://github.com/cloud-custodian/cloud-custodian" \
      homepage="http://github.com/cloud-custodian/cloud-custodian" \
      maintainer="Custodian Community <https://cloudcustodian.io>"

# Transfer Custodian source into container by directory
# to minimize size
ADD pyproject.toml poetry.lock README.md /src/
ADD c7n /src/c7n/
ADD tools/c7n_gcp /src/tools/c7n_gcp
ADD tools/c7n_azure /src/tools/c7n_azure
ADD tools/c7n_kube /src/tools/c7n_kube
ADD tools/c7n_org /src/tools/c7n_org
ADD tools/c7n_mailer /src/tools/c7n_mailer

WORKDIR /src

RUN adduser --disabled-login custodian
RUN apt-get --yes update \
 && apt-get --yes install build-essential curl --no-install-recommends \
 && python3 -m venv /usr/local \
 && curl -sSL https://raw.githubusercontent.com/python-poetry/poetry/master/get-poetry.py | python3 \
 && . /usr/local/bin/activate \
 && $HOME/.poetry/bin/poetry install --no-dev \
 && cd tools/c7n_azure && $HOME/.poetry/bin/poetry install && cd ../.. \
 && cd tools/c7n_gcp && $HOME/.poetry/bin/poetry install && cd ../.. \
 && cd tools/c7n_kube && $HOME/.poetry/bin/poetry install && cd ../.. \
 && apt-get --yes remove build-essential \
 && apt-get purge --yes --auto-remove -o APT::AutoRemove::RecommendsImportant=false \
 && rm -Rf /var/cache/apt/ \
 && rm -Rf /var/lib/apt/lists/* \
 && rm -Rf /root/.cache/ \
 && rm -Rf /root/.poetry \
 && mkdir /output \
 && chown custodian: /output

USER custodian
WORKDIR /home/custodian
ENV LC_ALL="C.UTF-8" LANG="C.UTF-8"
VOLUME ["/home/custodian"]
ENTRYPOINT ["/usr/local/bin/custodian"]
CMD ["--help"]
