App Engine - Check if a blacklisted domain is still in use
===========================================================
Custodian can check and notify if there are user-defined blacklisted domains in use. Note that the ``notify`` action requires a Pub/Sub topic to be configured.

In the example below, the policy checks if there are any domains contained in the ``&blacklisted-domains`` variable.

.. code-block:: yaml

    vars:
      blacklisted-domains-in-use: &blacklisted-domains
        - appengine-de.mo
        - gcp-li.ga
        - whatever.com
    policies:
      - name: gcp-app-engine-domain-notify-if-blacklisted-in-use
        resource: gcp.app-engine-domain
        filters:
          - type: value
            key: id
            op: in
            value: *blacklisted-domains
        actions:
          - type: notify
            subject: Blacklisted domains still in use
            to:
              - email@address
            format: txt
            transport:
              type: pubsub
              topic: projects/my-gcp-project/topics/my-topic
