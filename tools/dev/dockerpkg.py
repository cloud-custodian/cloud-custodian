# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
#
"""
Build Docker Artifacts

On build this is loosely modeled after https://github.com/docker/build-push-action
  - same in that we auto add labels from github action metadata.
  - differs in that we use `dev` for latest.
  - differs in that latest refers to last tagged revision.

We also support running functional tests and image cve scanning before pushing.
"""

import logging
from pathlib import Path

import click

log = logging.getLogger("dockerpkg")

PHASE_1_INSTALL_TMPL = """
ADD tools/c7n_{pkg}/pyproject.toml /src/tools/c7n_{pkg}/
RUN if [[ " ${{providers[*]}} " =~ "{pkg}" ]]; then \
   uv sync --package c7n_{pkg} --frozen --inexact --no-install-workspace; \
fi
"""

PHASE_2_INSTALL_TMPL = """
ADD tools/c7n_{pkg} /src/tools/c7n_{pkg}
RUN if [[ " ${{providers[*]}} " =~ "{pkg}" ]]; then \
   uv sync --package c7n_{pkg} --frozen --inexact; \
fi
"""

default_providers = ["gcp", "azure", "kube", "openstack", "tencentcloud", "oci", "awscc"]

PHASE_1_PKG_INSTALL_DEP = """\
# We include `pyproject.toml` and `uv.lock` first to allow
# cache of dependency installs.
"""
PHASE_2_PKG_INSTALL_ROOT = """\
# Now install the root of each provider
"""
PHASE_1_PKG_INSTALL_DEP += "".join(
    [PHASE_1_INSTALL_TMPL.format(pkg=pkg) for pkg in default_providers]
)

PHASE_2_PKG_INSTALL_ROOT += "".join(
    [PHASE_2_INSTALL_TMPL.format(pkg=pkg) for pkg in default_providers]
)


BOOTSTRAP_STAGE = """\
# Dockerfiles are generated from tools/dev/dockerpkg.py
FROM {base_build_image} AS build-env

SHELL ["/bin/bash", "-c"]

# pre-requisite distro deps, and build env setup
RUN apt-get --yes update
RUN apt-get --yes install --no-install-recommends build-essential \
    curl python3-venv python3-dev adduser
RUN adduser --disabled-login --gecos "" custodian
# wheel installation cache
RUN --mount=type=cache,target=/root/.cache/uv
COPY --from=ghcr.io/astral-sh/uv:{uv_version} /uv /uvx /bin/
ARG PATH="/root/.local/bin:$PATH"

WORKDIR /src
"""


BUILD_STAGE = BOOTSTRAP_STAGE + """\
# Add core & aws packages
ARG providers="{providers}"

# copy pyproject.tomls for all packages
ADD pyproject.toml uv.lock README.md /src/
RUN uv sync --frozen --inexact --no-install-workspace

{PHASE_1_PKG_INSTALL_DEP}

# copy packages
ADD c7n /src/c7n/
RUN uv sync --frozen --inexact

{PHASE_2_PKG_INSTALL_ROOT}

RUN mkdir /output
"""

TARGET_UBUNTU_STAGE = """\
FROM {base_target_image}

LABEL name="{name}" \\
      repository="http://github.com/cloud-custodian/cloud-custodian"

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get --yes update \\
        && apt-get --yes install python3 python3-venv adduser {packages} --no-install-recommends \\
        && rm -Rf /var/cache/apt \\
        && rm -Rf /var/lib/apt/lists/* \\
        && rm -Rf /var/log/*

# These should remain below any other commands because they will invalidate
# the layer cache
COPY --from=build-env /src /src
COPY --from=build-env /usr/local /usr/local
COPY --from=build-env /output /output


RUN adduser --disabled-login --gecos "" custodian
USER custodian
WORKDIR /home/custodian
ENV LC_ALL="C.UTF-8" LANG="C.UTF-8"
VOLUME ["/home/custodian"]
ENTRYPOINT ["{entrypoint}"]
CMD ["--help"]
"""


TARGET_DISTROLESS_STAGE = """\
FROM {base_target_image}

LABEL name="{name}" \\
      repository="http://github.com/cloud-custodian/cloud-custodian"

COPY --from=build-env /src /src
COPY --from=build-env /usr/local /usr/local
COPY --from=build-env /etc/passwd /etc/passwd
COPY --from=build-env /etc/group /etc/group
COPY --chown=custodian:custodian --from=build-env /output /output
COPY --chown=custodian:custodian --from=build-env /home/custodian /home/custodian

USER custodian
WORKDIR /home/custodian
ENV LC_ALL="C.UTF-8" LANG="C.UTF-8"
VOLUME ["/home/custodian"]
ENTRYPOINT ["{entrypoint}"]
CMD ["--help"]
"""

TARGET_CLI = """\
LABEL "org.opencontainers.image.title"="cli"
LABEL "org.opencontainers.image.description"="Cloud Management Rules Engine"
LABEL "org.opencontainers.image.documentation"="https://cloudcustodian.io/docs"
"""

BUILD_KUBE = """\
# Install c7n-kube
ADD tools/c7n_kube /src/tools/c7n_kube
RUN uv sync --locked --package c7n_kube
"""

TARGET_KUBE = """\
LABEL "org.opencontainers.image.title"="kube"
LABEL "org.opencontainers.image.description"="Cloud Custodian Kubernetes Hooks"
LABEL "org.opencontainers.image.documentation"="https://cloudcustodian.io/docs"
"""

BUILD_ORG = """\
# Install c7n-org
ADD tools/c7n_org /src/tools/c7n_org
RUN uv sync --locked --inexact --package c7n_org
"""

TARGET_ORG = """\
LABEL "org.opencontainers.image.title"="org"
LABEL "org.opencontainers.image.description"="Cloud Custodian Management Rules Engine"
LABEL "org.opencontainers.image.documentation"="https://cloudcustodian.io/docs"
"""

BUILD_MAILER = """\
# Install c7n-mailer
ADD tools/c7n_mailer /src/tools/c7n_mailer
RUN uv sync --locked --all-extras --package c7n_mailer
"""

TARGET_MAILER = """\
LABEL "org.opencontainers.image.title"="mailer"
LABEL "org.opencontainers.image.description"="Cloud Custodian Notification Delivery"
LABEL "org.opencontainers.image.documentation"="https://cloudcustodian.io/docs"
"""

BUILD_POLICYSTREAM = """\
# Install c7n-policystream
ADD tools/c7n_policystream /src/tools/c7n_policystream
RUN uv sync --locked --package c7n_policystream
"""

TARGET_POLICYSTREAM = """\
LABEL "org.opencontainers.image.title"="policystream"
LABEL "org.opencontainers.image.description"="Custodian policy changes streamed from Git"
LABEL "org.opencontainers.image.documentation"="https://cloudcustodian.io/docs"
"""


class Image:

    defaults = dict(
        base_build_image="ubuntu:24.04",
        base_target_image="ubuntu:24.04",
        uv_version="0.7.6",
        packages="",
        providers=" ".join(default_providers),
        PHASE_1_PKG_INSTALL_DEP=PHASE_1_PKG_INSTALL_DEP,
        PHASE_2_PKG_INSTALL_ROOT=PHASE_2_PKG_INSTALL_ROOT,
    )

    def __init__(self, metadata, build, target):
        self.metadata = metadata
        self.build = build
        self.target = target

    @property
    def repo(self):
        return self.metadata.get("repo", self.metadata["name"])

    @property
    def tag_prefix(self):
        return self.metadata.get("tag_prefix", "")

    def render(self):
        output = []
        output.extend(self.build)
        output.extend(self.target)
        template_vars = dict(self.defaults)
        template_vars.update(self.metadata)
        return "\n".join(output).format(**template_vars)

    def clone(self, metadata, target=None):
        d = dict(self.metadata)
        d.update(metadata)
        return Image(d, self.build, target or self.target)


ImageMap = {
    "docker/c7n": Image(
        dict(
            name="cli",
            repo="c7n",
            description="Cloud Management Rules Engine",
            entrypoint="/src/.venv/bin/custodian",
        ),
        build=[BUILD_STAGE],
        target=[TARGET_UBUNTU_STAGE, TARGET_CLI],
    ),
    "docker/c7n-kube": Image(
        dict(
            name="kube",
            repo="c7n",
            description="Cloud Custodian Kubernetes Hooks",
            entrypoint="/usr/local/bin/c7n-kates",
        ),
        build=[BUILD_STAGE, BUILD_KUBE],
        target=[TARGET_UBUNTU_STAGE, TARGET_KUBE],
    ),
    "docker/c7n-org": Image(
        dict(
            name="org",
            repo="c7n-org",
            description="Cloud Custodian Organization Runner",
            entrypoint="/usr/local/bin/c7n-org",
        ),
        build=[BUILD_STAGE, BUILD_ORG],
        target=[TARGET_UBUNTU_STAGE, TARGET_ORG],
    ),
    "docker/mailer": Image(
        dict(
            name="mailer",
            description="Cloud Custodian Notification Delivery",
            entrypoint="/usr/local/bin/c7n-mailer",
        ),
        build=[BUILD_STAGE, BUILD_MAILER],
        target=[TARGET_UBUNTU_STAGE, TARGET_MAILER],
    ),
    "docker/policystream": Image(
        dict(
            name="policystream",
            description="Custodian policy changes streamed from Git",
            entrypoint="/usr/local/bin/c7n-policystream",
        ),
        build=[BUILD_STAGE, BUILD_POLICYSTREAM],
        target=[TARGET_UBUNTU_STAGE, TARGET_POLICYSTREAM],
    ),
}


@click.group()
def cli():
    """Custodian Docker Packaging Tool

    slices, dices, and blends :-)
    """
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s:%(levelname)s %(message)s"
    )
    logging.getLogger("docker").setLevel(logging.INFO)
    logging.getLogger("urllib3").setLevel(logging.INFO)


@cli.command()
def generate():
    """Generate dockerfiles"""
    for df_path, image in ImageMap.items():
        print(df_path)
        p = Path(df_path)
        p.write_text(image.render())


if __name__ == "__main__":
    cli()
