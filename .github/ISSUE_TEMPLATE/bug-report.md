---
name: Bug report
about: Report an issue about using Custodian
title: ''
labels: kind/bug
assignees: ''

---

**Describe the bug**
A clear and concise description of what the bug is.

**To Reproduce**
Steps to reproduce the behavior:

**Expected behavior**
A clear and concise description of what you expected to happen.


**Background (please complete the following information):**
 - OS: [e.g. OSX 10.15]
 - Python Version: [e.g. python 3.8.1]
 - Custodian Version: [e.g. 0.8.46.1]
 - Tool Version: [if applicable]
 - Cloud Provider: [e.g. gcp, aws, azure]
 - Policy: [please exclude any account/sensitive information]
```yaml
policies: 
   - name: check-buckets
      resource: aws.s3
```
 - Traceback: [if applicable, please exclude sensitive/account information]
 - `custodian version --debug` output

**Additional context**
Add any other context about the problem here.
