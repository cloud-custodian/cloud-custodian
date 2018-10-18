FROM ubuntu:cosmic

ADD . /src
WORKDIR /src
RUN apt-get update && apt-get install -y libgit2-dev python3-pip
RUN pip3 install -r requirements.txt
ENV LC_ALL="C.UTF-8" LANG="C.UTF-8"
VOLUME ["/repos/"]
ENTRYPOINT ["/src/policystream.py"]

