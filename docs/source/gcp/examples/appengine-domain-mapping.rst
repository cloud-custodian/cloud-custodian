App Engine - Domain Mapping
===========================

Description

.. code-block:: yaml

    vars:
      no-longer-in-use: &outdated-mappings
        - appengine-de.mo
        - alex.gcp-li.ga
        - whatever.com
    policies:
      - name: gcp-app-engine-domain-mapping-notify-if-outdated
        resource: gcp.app-engine-domain-mapping
        filters:
          - type: value
            key: id
            op: in
            value: *outdated-mappings
        actions:
          - type: notify
            to:
              - alex.karpitski@gmail.com
            subject: Mappings no longer in use
            format: txt
            transport:
              type: pubsub
              topic: projects/cloud-custodian-190204/topics/appengine-demo
