Comparisons
------------

Janitor Monkey
^^^^^^^^^^^^^^

Netflix's Janitor Monkey provides for a statically defined set of
rules in code, many of which are overly specific to Netflix's use
cases. It also utilizes legacy technology for state management in the
form of SimpleDB. On the other hand, Custodian allows users to define policies
and rules to enforce within a yaml configuration file, and, due to it's stateless nature it can be deployed on a laptop, server, or lambda.

Security Monkey
^^^^^^^^^^^^^^^

Netflix's Security Monkey is a more interesting tool that provides for some
basic audit capabilities. It's worth investigating, but it's not clear that
there is much overlap between Cloud Custodian and Security Monkey as they are targeted
to different use cases.
