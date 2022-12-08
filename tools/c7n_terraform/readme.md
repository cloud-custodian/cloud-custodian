
# Cloud Custodian Terraform Provider

Custodian's terraform provider enables writing and evaluating
custodian policies against Terraform IaaC modules.


tldr: we want to enable writing custodian policies against IaaC assets (terraform, cfn, etc) directly in devops/ci pipelines.

# Purpose

The primary purpose of this is to integrate with ci/cd pipelines to
evaluate compliance and governance early in the deployment
lifecycle. Custodian cloud providers provide for realtime detection
and remediation as a detective control against infrastructure already
deployed in the environment regardless of how it was provisioned. As
an initial target, the terraform provider is designed to complement
that with preventive enforcement earlier in the
lifecycle. ie. enabling a shift-left to policy enforcement.


# Pipeline CLI

In looking at expanding out to shift-left pipeline use cases, one
thing that becomes clearer is that custodian's default cli ux isn't
perhaps the best fit for the target audience. When we're operating
against cloud resources we have to deal with cardinalities in the
thousands to millions. When we're operating in the pipelines we're
typically dealing with resource cardinalities in the 10s. Additionally
there is a goal expectation of having rich output that correlates to
the ci tooling (github annotations, etc) or pinpointing the issue for
a developer, as well as color'd output and other niceties. we could
incorporate that as a new subcommand into the main custodian cli
(dependent on presence of iaac providers installed), or have a
dedicated subcommand associated.

The other main deficiency with the cli is that we're not able to pass
directly the iaac files as data sets we want to consider. Typically
policies have expressed this as query parameterization within the
policy as being able to specify the exact target set. But the use case
here is more typically command line driven with specification of both
policy files and target IaaC files, as well as other possible vcs
integrations (policystream style wrt delta files) or ci integrations.

# Resources

wrt to the iaac provider we can either operate loosely typed or strongly typed. with strong typing we can spec out exact attributes and potentially do additional possibly validation wrt to user specified attributes, but it requires keeping an up to date store of all iaac provider assets, which could be both fairly large and rapidly changing (terraform has over 150 providers all release independently). for now, I think it would be good to keep to loose typing on resources. .. and perhaps document provider addressable resource attributes  as part of documentation.

Loose typing would enable working out of the box with extant providers, but policy authors would have to consult reference docs for their respective providers on available attributes or even provider resource type existence. From a custodian perspective we would use a common resource implementation across provider resource types.

#  Examples

```yaml
- resource: terraform.aws_dynamodb_table
   name: ensure encryption
   filters:
      server_side_encryption.enabled: true
      kms_key_arn: key_alias
```



# 

  custodian run terraform.yml
  
  custodian report --format=
  
# dedicated cli


  custodian run-source terraform.yml
