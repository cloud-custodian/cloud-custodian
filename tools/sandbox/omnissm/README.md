# OmniSSM - EC2 Systems Manager Automation

[![GoDoc](https://godoc.org/github.com/capitalone/cloud-custodian/tools/omnissm?status.svg)](https://godoc.org/github.com/capitalone/cloud-custodian/tools/omnissm)


Automation for AWS Systems Manager using hybrid mode. Using hybrid mode for ec2 instances brings a few benefits.

 - No instance credentials needed
 - Centralized management of servers across numerous accounts.
 - Facilitate cross cloud/datacenter usage of SSM

Switching from ec2 to hybrid mode, does mean we have to reproduce a bit of functionality

 - Secure instance registration.
 - Instance deactivation/garbage collection on delete.
 - Instance metadata enrichment.

We provide a few bits of automation tooling to enable seamless hybrid mode.

 - A register api via api gw lambda for registering cloud instances.
   We handle secure introductions via cloud instance identity document signature verification.

 - a host registration/initialization cli for interacting with the register api and initializing ssm-agent on instance boot.

 - a custom inventory plugin for collecting process information.

 - a config subscriber for enriching a ssm instance with tags and cloud inventory,
   and deleting/gc instances from ssmo.

 - an sns topic subscriber for enriching instances that are registering after a config event
   has already fired (ie slow boot).

![(OmniSSM)](assets/omnissm.svg)

## Client Configuration

The OmniSSM agent is configured by environment variables as well as a YAML configuration file and command-line flags. OmniSSM checks for the file `omnissm.yaml` in either `/etc/omnissm/` or the current directory at runtime.

Parameters:

|Flag|Environment Variable|YAML key|Description|
|----|--------------------|--------|-----------|
|`-v,--verbose`|`OMNISSM_VERBOSE`|`verbose`|Enable debug logging|
|`--register-endpoint <endpoint>`|`OMNISSM_REGISTER_ENDPOINT`|`register_endpoint`|Specify a single API endpoint to register with, overriding `register_endpoints`|
|N/A|N/A|`register_endpoints`|A map of regions to endpoints|

Either the register endpoints map, or the single register endpoint override must be set.

## Links

- Hybrid SSM Manual Install https://amzn.to/2Hlu9o2
- EC2 Instance Identity Documents https://amzn.to/2qLuGt9
- Google Instance Identity https://bit.ly/2HQexKc

## Todo

- scale testing
- test with large cfg messages
- sns subscriber for slow boot instances
- systemd timer example for initialize & inventory
- custom inventory output directly to agent pickup location
- osquery inventory example
