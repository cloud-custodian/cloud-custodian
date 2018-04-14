# Sphere 11

Sphere 11 provides an api for locking/unlock resources within
AWS. Modifications to a locked resource can either generate
notifications, or be automatically reverted.

Enforcement of the locks is delegated to custodian policies
within the account. The lock api serves as metadata tracking
on the lock.

Resources can be locked at the resource level, enclosure, or account
level. Supported enclosure is a vpc for network resources. Resources
locked at an enclosure level, can be unlocked on an individual
resource level.

Leases can also be created for a given user or role (for sts) to
perform changes on the given resource within the given time frame.

# Resources supported

- [x] security groups
- [ ] route tables
- [ ] network acls
- [ ] iam users
- [ ] iam policies
- [ ] iam roles


# Documentation

- api
- authentication
- data-model
- diff-patch
- operations

# Technical




