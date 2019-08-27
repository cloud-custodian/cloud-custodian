# c7n-salactus: Distributed Scale out S3 processing


Salactus, inspired by the planet eaters.

Distributed, scale out s3 scanning

**Note** this was built a few years before AWS S3 Batch Operations
which maybe a simpler solution for the problem domain.

## Use Cases

Sometimes you really want to scan all objects, or in the words of gary
oldman from the professional, "bring me EVERYONE" :-) There are a
couple of different reasons for that from an org perspective, given
current feature sets, most of it involves catching up on s3 security
from both an acl and encryption perspective after the fact.

Salactus provides for scale out scanning of every s3 object with
configurable object visitors. It also supports s3 inventory as a
source for objects or it can attempt to use heurestics to scan large
buckets, the intent is always to optimize for throughput across a
population measured in billions.


## Usage

```
$ apt-get install redis-server | or elasticache
```
```
$ export SALACTUS_REDIS=localhost | or point to elasticache endpoint
```
```
$ c7n-salactus --help
Usage: c7n-salactus [OPTIONS] COMMAND [ARGS]...

  Salactus, eater of s3 buckets

Options:
  --help  Show this message and exit.

Commands:
  accounts            Report on stats by account
  buckets             Report on stats by bucket
  failures            Show any unexpected failures
  inspect-bucket      Show all information known on a buckets
  inspect-partitions  Discover the partitions on a bucket via...
  inspect-queue       Show contents of a queue.
  queues              Report on progress by queues.
  reset               Delete all persistent cluster state.
  run                 Run across a set of accounts and buckets.
  save                Save the current state to a json file
  validate            Validate a configuration file.
  watch               watch scan rates across the cluster
  workers             Show information on salactus workers.
  ```


we also provide a sample user data for asg runtime initialization and a supervisord.conf for running the various components in parallel.


The components of salactus are


 - bucket-iterator - an account scanner that lists buckets and checks cloud watch metrics for reporting total progress of a scan

 - bucket-partition - heureustic algorithm for scanning large buckets, can use either a common prefix match, n-gram, or s3 inventory, auto configured

 - page-iterator - a head to tail object iterator over a given prefix

 - keyset-scan - handles pages of 1k objects and dispatches to object visitor
 
## Sample Configuration

The below sample configuration can be used to scan all objects in all
buckets in the specified account and generate JSON reports on any
objects that are currently not encrypted. Flip report-only to false
and it will actually remediate them to be encrypted using AES256.

To get this running you will need to create a role, e.g. salactus-role,
that can be assumed which has read permissions to CloudWatch, S3, and
write access to the bucket created or chosen for the reports, e.g.
salactus-bucket.

``` 
accounts:
  - account-id: "123456789012"
    role: "arn:aws:iam::123456789012:role/salactus-role"
    name: "AWS Account Alias"

visitors:
  - type: "encrypt-keys"
    crypto: AES256
    report-only: true

object-reporting:
  bucket: "salactus-bucket"
  prefix: "object-reports"
```
