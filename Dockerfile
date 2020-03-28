FROM debian:10 as build-env

LABEL name="custodian" \
      description="Cloud Management Rules Engine" \
      repository="http://github.com/cloud-custodian/cloud-custodian" \
      homepage="http://github.com/cloud-custodian/cloud-custodian" \
      maintainer="Custodian Community <https://cloudcustodian.io>"

RUN adduser --disabled-login custodian \
 && mkdir /output \
 && chown custodian: /output

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

RUN apt-get --yes update \
 && apt-get --yes install build-essential curl python3-venv --no-install-recommends \
 && python3 -m venv /usr/local \
 && curl -sSL https://raw.githubusercontent.com/python-poetry/poetry/master/get-poetry.py | python3 \
 && . /usr/local/bin/activate \
 && $HOME/.poetry/bin/poetry install --no-dev \
 && cd tools/c7n_azure && $HOME/.poetry/bin/poetry install && cd ../.. \
 && cd tools/c7n_gcp && $HOME/.poetry/bin/poetry install && cd ../.. \
 && cd tools/c7n_kube && $HOME/.poetry/bin/poetry install && cd ../.. 

# Distroless Container
FROM gcr.io/distroless/python3-debian10
COPY --from=build-env /src /src
COPY --from=build-env /usr/local /usr/local
COPY --from=build-env /output /output
COPY --from=build-env /etc/passwd /etc/passwd
USER custodian
WORKDIR /home/custodian
ENV LC_ALL="C.UTF-8" LANG="C.UTF-8"
VOLUME ["/home/custodian"]
ENTRYPOINT ["/usr/local/bin/custodian"]
CMD ["--help"]