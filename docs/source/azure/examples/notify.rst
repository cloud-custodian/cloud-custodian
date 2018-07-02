Email Notify
==============

Action to queue email.  See c7n_mailer readme.md for more information.

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
