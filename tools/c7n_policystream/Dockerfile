FROM ubuntu:disco

LABEL name="policystream" \
      description="Custodian policy changes streamed from Git" \
      repository="http://github.com/cloud-custodian/cloud-custodian" \
      homepage="http://github.com/cloud-custodian/cloud-custodian" \
      maintainer="Kapil Thangavelu <http://twitter.com/kapilvt>"

# Note this must be run from the root directory of the checkout
# as we install custodian w/ aws, azure, and gcp support from the same
# repo.

# Transfer Custodian source into container by directory
# to minimize size
ADD setup.py README.rst requirements.txt /src/
ADD c7n /src/c7n/
ADD tools /src/tools/

WORKDIR /src
RUN adduser --home /home/custodian --disabled-login custodian

RUN apt-get --yes update && apt-get --yes upgrade \
	&& apt-get --yes install build-essential libgit2-dev libffi-dev python3-pip \
	&& pip3 install -r requirements.txt  . \
	&& pip3 install -r tools/c7n_azure/requirements.txt tools/c7n_azure \
	&& pip3 install -r tools/c7n_gcp/requirements.txt tools/c7n_gcp \
	&& pip3 install -r tools/c7n_policystream/requirements.txt tools/c7n_policystream \
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
ENTRYPOINT ["/usr/local/bin/c7n-policystream"]
CMD ["--help"]
