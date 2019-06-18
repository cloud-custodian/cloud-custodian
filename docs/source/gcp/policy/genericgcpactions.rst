.. _gcp_genericgcpactions:

Generic Actions
================

This action can be applied to any GCP resource type.

Notify
------
``Notify``
  Add notify message into Cloud Pub/Sub. To check below example please use created GCP project and configured Pub/Sub topic.

  .. code-block:: yaml

        policies:
            - name: gcp-notify-first-example
              description: |
                Example of notify action
              resource: gcp.loadbalancer-address
              actions:
                - type: notify
                  to:
                    - email@email
                  format: json
                  transport:
                    type: pubsub
                    topic: projects/<name of a project>/topics/<name of a topic>

To run the example please make sure

 - the project is configured,
 - Pub/Sub topic is created and configured,
 - Cloud function for messages decoding is created.

Pub/Sub system is able to provide information about message in encoded format. One of the ways how to make the message readable is using a decoding cloud function.

If the messaging system is not configured please follow next steps:

 - create a project in GCP or use created one (name of the project use instead of <name of a project> in the policy),
 - open `Pub/Sub page <https://console.cloud.google.com/cloudpubsub/topicList>`_,
 - create a topic (name of the topic use instead of <name of a topic> in the policy),
 - open `Cloud Function page <https://console.cloud.google.com/functions/list>`_
 - create a function with following params:

    - Name: name of the function,
    - Topic: <name of the topic>,
    - Memory allocated: 128 MB,
    - Runtime: Python 3.7,
    - Function to execute: print_decoded,
    - main.py:

    .. code-block:: python

        import base64
        import zlib

        def print_decoded(event, context):
            decoded_compressed = base64.b64decode(event['data'])
            decompressed = zlib.decompress(decoded_compressed)
            print(decompressed)

After the steps are executed please open `Log Viewer <https://console.cloud.google.com/logs/viewer>`_. Select created function in the resource combobox. It should be available in Cloud Function -> name of the function section.
If the above policy is run new decoded message will appear in logs.
