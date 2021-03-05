# Dockerfiles are generated from tools/dev/dockerpkg.py

FROM ubuntu:20.04 as build-env

# pre-requisite distro deps, and build env setup
RUN adduser --disabled-login --gecos "" custodian
RUN apt-get --yes update
RUN apt-get --yes install build-essential curl python3-venv python3-dev --no-install-recommends
RUN python3 -m venv /usr/local
RUN curl -sSL https://raw.githubusercontent.com/python-poetry/poetry/master/get-poetry.py | python3

WORKDIR /src

# Add core & aws packages
ADD pyproject.toml poetry.lock README.md /src/
ADD c7n /src/c7n/
RUN . /usr/local/bin/activate && $HOME/.poetry/bin/poetry install --no-dev
RUN . /usr/local/bin/activate && pip install -q wheel
RUN . /usr/local/bin/activate && pip install -q aws-xray-sdk psutil jsonpatch

# Add provider packages
ADD tools/c7n_gcp /src/tools/c7n_gcp
RUN rm -R tools/c7n_gcp/tests
ADD tools/c7n_azure /src/tools/c7n_azure
RUN rm -R tools/c7n_azure/tests_azure
ADD tools/c7n_kube /src/tools/c7n_kube
RUN rm -R tools/c7n_kube/tests
ADD tools/c7n_openstack /src/tools/c7n_openstack
RUN rm -R tools/c7n_openstack/tests

# Install requested providers
ARG providers="azure gcp kube openstack"
RUN . /usr/local/bin/activate && \
    for pkg in $providers; do cd tools/c7n_$pkg && \
    $HOME/.poetry/bin/poetry install && cd ../../; done

RUN mkdir /output

FROM ubuntu:20.04

LABEL name="cli" \
      repository="http://github.com/cloud-custodian/cloud-custodian"

COPY --from=build-env /src /src
COPY --from=build-env /usr/local /usr/local
COPY --from=build-env /output /output

RUN DEBIAN_FRONTEND=noninteractive apt-get --yes update \
        && apt-get --yes install python3 python3-venv --no-install-recommends \
        && rm -Rf /var/cache/apt \
        && rm -Rf /var/lib/apt/lists/* \
        && rm -Rf /var/log/*

RUN adduser --disabled-login --gecos "" custodian
USER custodian
WORKDIR /home/custodian
ENV LC_ALL="C.UTF-8" LANG="C.UTF-8"
VOLUME ["/home/custodian"]
ENTRYPOINT ["/usr/local/bin/custodian"]
CMD ["--help"]
