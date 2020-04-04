FROM debian:10-slim as build-env

# pre-requisite distro deps, and build env setup
RUN adduser --disabled-login custodian
RUN apt-get --yes update
RUN apt-get --yes install build-essential curl python3-venv python3-dev --no-install-recommends
RUN python3 -m venv /usr/local
RUN curl -sSL https://raw.githubusercontent.com/python-poetry/poetry/master/get-poetry.py | python3

WORKDIR /src

# Add core & aws packages
ADD pyproject.toml poetry.lock README.md /src/
ADD c7n /src/c7n/
RUN . /usr/local/bin/activate && $HOME/.poetry/bin/poetry install --no-dev
RUN . /usr/local/bin/activate && pip install -q aws-xray-sdk psutil jsonpatch

# Add provider packagees
ADD tools/c7n_gcp /src/tools/c7n_gcp
ADD tools/c7n_azure /src/tools/c7n_azure
ADD tools/c7n_kube /src/tools/c7n_kube

# Install requested providers
ARG providers="azure gcp kube"
RUN . /usr/local/bin/activate && for pkg in $providers; do cd tools/c7n_$pkg && $HOME/.poetry/bin/poetry install && cd ../../; done

RUN mkdir /output

# Distroless Container
FROM gcr.io/distroless/python3-debian10

LABEL name="custodian" \
      description="Cloud Management Rules Engine" \
      repository="http://github.com/cloud-custodian/cloud-custodian" \
      homepage="http://github.com/cloud-custodian/cloud-custodian" \
      maintainer="Custodian Community <https://cloudcustodian.io>"

COPY --from=build-env /src /src
COPY --from=build-env /usr/local /usr/local
COPY --from=build-env /etc/passwd /etc/passwd
COPY --from=build-env /etc/group /etc/group
COPY --from=build-env /output /output

USER custodian
WORKDIR /home/custodian
ENV LC_ALL="C.UTF-8" LANG="C.UTF-8"
VOLUME ["/home/custodian"]
ENTRYPOINT ["/usr/local/bin/custodian"]
CMD ["--help"]
