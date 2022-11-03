# Example Tag Compliance Policy

In this sample policy we are filtering for EC2 instances that are:

- Running
- Not part of an Auto Scaling Group (ASG)
- Not already marked for an operation
- Have less than 10 tags
- Missing one or more of the required tags. 
  
Once Custodian has filtered the list, it will mark all
EC2 instances that match the above criteria with a tag. That tag
specifies an action that will take place at a certain time. This policy
is one of three that are needed to manage tag compliance. The other two
policies in this set are:

1. Checking to see if the tags have been corrected before the four day period is up
1. Performing the operation of stopping all instances with the status to be stopped on that particular day.

``` {.yaml}
- name: ec2-tag-compliance-mark
  resource: ec2
  comment: |
    Mark non-compliant, Non-ASG EC2 instances with stoppage in 4 days
  filters:
▣───────── - "State.Name": running
│ ▣─────── - "tag:aws:autoscaling:groupName": absent
│ │ ▣───── - "tag:c7n_status": absent
│ │ │ ▣─── - type: tag-count
│ │ │ │    - or:                           ─┐
│ │ │ │      - "tag:Owner": absent          ├─If any of these tags are
│ │ │ │      - "tag:CostCenter": absent     │ missing, then select instance
│ │ │ │      - "tag:Project": absent       ─┘
│ │ │ │
│ │ │ │  actions: ─────────────────▶ For selected instances, run this action
│ │ │ │    - type: mark-for-op ────▶ Mark instance for operation
│ │ │ │      op: stop ─────────────▶ Stop instance
│ │ │ │      days: 4 ──────────────▶ After 4 days
│ │ │ │
│ │ │ ▣────▶ If instance has 10 tags, skip
│ │ ▣──────▶ If instance already has a c7n_status, skip
│ ▣────────▶ If instance is part of an ASG, skip
▣──────────▶ If instance is not running, skip
```