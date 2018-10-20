FROM ubuntu:cosmic
MAINTAINER Kapil Thangavelu http://twitter.com/kapilvt

ADD . /src
WORKDIR /src
RUN apt-get update && apt-get install -y libgit2-dev python3-pip
RUN pip3 install -r requirements.txt
RUN python3 setup.py develop
ENV LC_ALL="C.UTF-8" LANG="C.UTF-8"
VOLUME ["/repos/"]
ENTRYPOINT ["c7n-policystream"]

