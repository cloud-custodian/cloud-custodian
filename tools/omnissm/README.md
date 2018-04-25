# OmniSSM

Automation for AWS Systems Manager using hybrid mode. Using hybrid mode for ec2 instances brings a few benefits.

 - No instance credentials needed
 - Centralized management of servers across numerous accounts.
 - Facilitate cross cloud/datacenter usage of SSM

Switching from ec2 to hybrid mode, does mean we have to reproduce a bit of functionality

 - Secure instance registration
 - Instance deactivation/garbage collection
 - Instance metadata enrichment.

We provide a few bits of automation tooling to enable seamless hybrid mode.

 - a register api via api gw lambda for registering cloud 
   instances. we handle secure introductions via cloud instance identity document signatures.

 - a host registration/initialization cli for interacting
   with the register api and initializing ssm-agent.

 - a custom inventory plugin for collecting process 
   information.


# Links

- Hybrid SSM Manual Install https://amzn.to/2Hlu9o2
- EC2 Instance Identity Documents https://amzn.to/2qLuGt9
- Google Instance Identity https://bit.ly/2HQexKc


