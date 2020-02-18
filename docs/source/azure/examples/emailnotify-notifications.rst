Email - Send Users an Email
===========================

Action to queue email after the mailer is configured.  See `c7n_mailer readme.md <https://github.com/cloud-custodian/cloud-custodian/blob/master/tools/c7n_mailer/README.md#using-on-azure>`_ for more information.


.. code-block:: yaml

    policies:
      - name: notify
        resource: azure.resourcegroup
        actions:
          - type: notify
            template: default
            subject: Hello World
            to:
              - someone@somewhere.com
            transport:
              type: asq
              queue: https://storagename.queue.core.windows.net/queuename
