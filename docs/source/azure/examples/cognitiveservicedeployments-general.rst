.. _azure_examples_cognitiveservice_deployments:

Cognitive Services Deployments - Find and delete failed model deployments
=========================================================================

The ``azure.cognitiveservice-deployment`` resource can be used to find and
remediate failed Azure OpenAI / Cognitive Services model deployments.

Find failed deployments
-----------------------

.. code-block:: yaml

  policies:
    - name: azure-cognitiveservice-deployments-find-failed
      resource: azure.cognitiveservice-deployment
      filters:
        - type: value
          key: properties.provisioningState
          op: in
          value: [Failed, Canceled]

Delete failed deployments
-------------------------

.. code-block:: yaml

  policies:
    - name: azure-cognitiveservice-deployments-delete-failed
      resource: azure.cognitiveservice-deployment
      filters:
        - type: value
          key: properties.provisioningState
          value: Failed
      actions:
        - type: delete

Tagging note
------------

Tagging is not supported for ``azure.cognitiveservice-deployment``.
Cloud Custodian intentionally rejects tag actions for this resource type because
deployment-level tagging is not exposed consistently for this ARM child resource.
