custodian-container
===================

custodian-container is a Go wrapper over the `cloudcustodian/c7n:latest`
Docker image.  It allows you to use the docker image with the same CLI you
would use for a local Custodian installation. 

This can be useful in situations where you would like to ensure a working
CLI without requiring Python or package dependencies.


Build
-----

```
cd cloud-custodian\tools\custodian-container
go build -o custodianc
```

Run
---
```
custodianc run -s . policy.yml
```