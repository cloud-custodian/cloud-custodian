custodian-cask
===================

custodian-cask is a Go wrapper over the `cloudcustodian/c7n:latest`
Docker image.  It allows you to use the docker image with the same CLI you
would use for a local Custodian installation. 

This can be useful in situations where you would like to ensure a working
CLI without requiring Python or package dependencies.


Build
-----

```
cd cloud-custodian\tools\custodian-cask
go build -o custodian-cask
```

Run
---
```
custodian-cask run -s . policy.yml
```

You may override the default docker image with the environment variable `CUSTODIAN_IMAGE`

Cask will only attempt to pull any specific image once per hour.  
You can delete $(tmp)\custodian-cask* if you'd like to force an update.