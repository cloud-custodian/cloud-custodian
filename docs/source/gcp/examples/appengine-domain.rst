App Engine - Domain
====================

Custodian can check expiration of user-added custom domains.

.. code-block:: yaml

    vars:
      no-longer-in-use: &outdated-mappings
        - appengine-de.mo
        - gcp-li.ga
        - whatever.com
    policies:
      - name: gcp-app-engine-domain-notify-if-outdated
        resource: gcp.app-engine-domain
        filters:
          - type: value
            key: id
            op: in
            value: *outdated-mappings
        actions:
          - type: notify
            to:
              - email@address
            subject: Domains no longer in use
            format: txt
            transport:
              type: pubsub
              topic: projects/cloud-custodian-190204/topics/appengine-demo
