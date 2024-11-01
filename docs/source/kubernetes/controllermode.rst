.. _kubernetes_controlermode:

Kubernetes Controller Mode
==========================

The Kubernetes Provider also supports executing as a Dynamic Admission Controller. This allows
you to execute and enforce policies on resources as they are created, updated, or deleted. The
k8s-admission mode must be run as a separate HTTPS web service with the provided ``c7n-kates`` cli.

To run policies in this mode, ensure that the cluster has MutatingAdmissionWebhooks enabled. For
more info, see the `Kubernetes Docs <https://kubernetes.io/docs/reference/access-authn-authz/admission-controllers/>`_.


.. kubernetes_k8s-admission-install:

Install the Server
------------------

Dynamic Admission Controllers can only operate against HTTPS webhooks. To get started, you can either
create a service inside of your Kubernetes Cluster or use a cloud provider to run a web server.

Option 1: Manual installation
=============================

To get started, create a new directory of policies:

.. code-block:: bash

   mkdir policies

Next, in your policy directory, create a new policy.yaml file and add the following contents:

.. code-block:: yaml

  policies:
    - name: 'example-warn-policy'
      resource: 'k8s.pod'
      description: 'This is a sample policy'
      mode:
        type: k8s-admission
        on-match: warn
        operations:
          - CREATE

Next, generate the MuttatingWebhookConfiguration manifest. replace $endpoint with the https endpoint
of your web server, e.g. ``https://example.org``:

.. code-block:: bash

   c7n-kates --policy-dir policies --generate --endpoint $endpoint > webhook.yaml

This will create a manifest containing a webhook that will inspect the operations and resource types
that are applicable to your policies. Next, apply the manifest to your Kubernetes Cluster:

.. code-block:: bash

   kubectl apply -f webhook.yaml

Next, on your server, start c7n-kates:

.. code-block:: bash

   c7n-kates --policy-dir policies

Option 2: Helm chart
====================

First configure the chart. The following  will configure a sample policy, use
cert-manager to sign your webhook, and operate against all pods when they are
created or updated. Adjust values.yaml as needed.

.. code-block:: bash

    cat << EOF > values.yaml
    certManager:
      enabled: true

    policies:
      source: configMap
      configMap:
        policies:
          # insert your policies here

          - name: 'example-warn-policy'
            resource: 'k8s.pod'
            description: 'This is a sample policy'
            mode:
              type: k8s-admission
              on-match: warn
              operations:
                - CREATE

    # These will need to be modified to match your policies.
    rules:
      - apiGroups: [""]
        apiVersions: [v1]
        operations: [CREATE, UPDATE]
        resources: [pods]
        scope: Namespaced
    EOF

    helm repo add c7n https://cloud-custodian.github.io/helm-charts/`
    helm install c7n-kube c7n/c7n-kube --values values.yaml

Testing
-------

We can apply a pod manifest to see the warning, create a new file ``pod.yaml`` and add the following:

.. code-block:: yaml

  apiVersion: v1
  kind: Pod
  metadata:
    name: nginx
  spec:
    containers:
    - name: nginx
      image: nginx:1.14.2
      ports:
      - containerPort: 80

Next, we can apply the new pod manifest:

.. code-block:: bash

   kubectl apply -f pod.yaml

Which should result in the following message:

.. code-block:: bash

   Warning: example-warn-policy:This is a sample policy
   pod/nginx created


On the server, you should see:

.. code-block:: bash

  c7n-kates --policy-dir policies
  2022-09-14 20:33:49,116: c7n_kube.server:INFO Loaded 1 policies
  2022-09-14 20:33:49,314: c7n_kube.server:INFO Serving at 0.0.0.0 8800
  2022-09-14 20:33:50,558: c7n_kube.server:INFO {"kind":"AdmissionReview","apiVersion":"admission.k8s.io/v1","request":{"uid":"2ec4911a-8a9d-4c8d-8aa5-2d3709877fd0","kind":{"group":"","version":"v1","kind":"Pod"},"resource":{"group":"","version":"v1","resource":"pods"},"requestKind":{"group":"","version":"v1","kind":"Pod"},"requestResource":{"group":"","version":"v1","resource":"pods"},"name":"nginx","namespace":"default","operation":"CREATE","userInfo":{"username":"kubernetes-admin","groups":["system:masters","system:authenticated"]},"object":{"kind":"Pod","apiVersion":"v1","metadata":{"name":"nginx","namespace":"default","uid":"eae00ed2-72d2-4ab4-9012-51ba11a284d0","creationTimestamp":"2022-09-14T20:33:50Z","annotations":{"kubectl.kubernetes.io/last-applied-configuration":"{\"apiVersion\":\"v1\",\"kind\":\"Pod\",\"metadata\":{\"annotations\":{},\"name\":\"nginx\",\"namespace\":\"default\"},\"spec\":{\"containers\":[{\"image\":\"nginx:1.14.2\",\"name\":\"nginx\",\"ports\":[{\"containerPort\":80}]}]}}\n"},"managedFields":[{"manager":"kubectl-client-side-apply","operation":"Update","apiVersion":"v1","time":"2022-09-14T20:33:50Z","fieldsType":"FieldsV1","fieldsV1":{"f:metadata":{"f:annotations":{".":{},"f:kubectl.kubernetes.io/last-applied-configuration":{}}},"f:spec":{"f:containers":{"k:{\"name\":\"nginx\"}":{".":{},"f:image":{},"f:imagePullPolicy":{},"f:name":{},"f:ports":{".":{},"k:{\"containerPort\":80,\"protocol\":\"TCP\"}":{".":{},"f:containerPort":{},"f:protocol":{}}},"f:resources":{},"f:terminationMessagePath":{},"f:terminationMessagePolicy":{}}},"f:dnsPolicy":{},"f:enableServiceLinks":{},"f:restartPolicy":{},"f:schedulerName":{},"f:securityContext":{},"f:terminationGracePeriodSeconds":{}}}}]},"spec":{"volumes":[{"name":"kube-api-access-mb9m2","projected":{"sources":[{"serviceAccountToken":{"expirationSeconds":3607,"path":"token"}},{"configMap":{"name":"kube-root-ca.crt","items":[{"key":"ca.crt","path":"ca.crt"}]}},{"downwardAPI":{"items":[{"path":"namespace","fieldRef":{"apiVersion":"v1","fieldPath":"metadata.namespace"}}]}}],"defaultMode":420}}],"containers":[{"name":"nginx","image":"nginx:1.14.2","ports":[{"containerPort":80,"protocol":"TCP"}],"resources":{},"volumeMounts":[{"name":"kube-api-access-mb9m2","readOnly":true,"mountPath":"/var/run/secrets/kubernetes.io/serviceaccount"}],"terminationMessagePath":"/dev/termination-log","terminationMessagePolicy":"File","imagePullPolicy":"IfNotPresent"}],"restartPolicy":"Always","terminationGracePeriodSeconds":30,"dnsPolicy":"ClusterFirst","serviceAccountName":"default","serviceAccount":"default","securityContext":{},"schedulerName":"default-scheduler","tolerations":[{"key":"node.kubernetes.io/not-ready","operator":"Exists","effect":"NoExecute","tolerationSeconds":300},{"key":"node.kubernetes.io/unreachable","operator":"Exists","effect":"NoExecute","tolerationSeconds":300}],"priority":0,"enableServiceLinks":true,"preemptionPolicy":"PreemptLowerPriority"},"status":{"phase":"Pending","qosClass":"BestEffort"}},"oldObject":null,"dryRun":false,"options":{"kind":"CreateOptions","apiVersion":"meta.k8s.io/v1","fieldManager":"kubectl-client-side-apply"}}}

  2022-09-14 20:33:50,559: custodian.k8s.policy:INFO Got event:{'kind': 'AdmissionReview', 'apiVersion': 'admission.k8s.io/v1', 'request': {'uid': '2ec4911a-8a9d-4c8d-8aa5-2d3709877fd0', 'kind': {'group': '', 'version': 'v1', 'kind': 'Pod'}, 'resource': {'group': '', 'version': 'v1', 'resource': 'pods'}, 'requestKind': {'group': '', 'version': 'v1', 'kind': 'Pod'}, 'requestResource': {'group': '', 'version': 'v1', 'resource': 'pods'}, 'name': 'nginx', 'namespace': 'default', 'operation': 'CREATE', 'userInfo': {'username': 'kubernetes-admin', 'groups': ['system:masters', 'system:authenticated']}, 'object': {'kind': 'Pod', 'apiVersion': 'v1', 'metadata': {'name': 'nginx', 'namespace': 'default', 'uid': 'eae00ed2-72d2-4ab4-9012-51ba11a284d0', 'creationTimestamp': '2022-09-14T20:33:50Z', 'annotations': {'kubectl.kubernetes.io/last-applied-configuration': '{"apiVersion":"v1","kind":"Pod","metadata":{"annotations":{},"name":"nginx","namespace":"default"},"spec":{"containers":[{"image":"nginx:1.14.2","name":"nginx","ports":[{"containerPort":80}]}]}}\n'}, 'managedFields': [{'manager': 'kubectl-client-side-apply', 'operation': 'Update', 'apiVersion': 'v1', 'time': '2022-09-14T20:33:50Z', 'fieldsType': 'FieldsV1', 'fieldsV1': {'f:metadata': {'f:annotations': {'.': {}, 'f:kubectl.kubernetes.io/last-applied-configuration': {}}}, 'f:spec': {'f:containers': {'k:{"name":"nginx"}': {'.': {}, 'f:image': {}, 'f:imagePullPolicy': {}, 'f:name': {}, 'f:ports': {'.': {}, 'k:{"containerPort":80,"protocol":"TCP"}': {'.': {}, 'f:containerPort': {}, 'f:protocol': {}}}, 'f:resources': {}, 'f:terminationMessagePath': {}, 'f:terminationMessagePolicy': {}}}, 'f:dnsPolicy': {}, 'f:enableServiceLinks': {}, 'f:restartPolicy': {}, 'f:schedulerName': {}, 'f:securityContext': {}, 'f:terminationGracePeriodSeconds': {}}}}]}, 'spec': {'volumes': [{'name': 'kube-api-access-mb9m2', 'projected': {'sources': [{'serviceAccountToken': {'expirationSeconds': 3607, 'path': 'token'}}, {'configMap': {'name': 'kube-root-ca.crt', 'items': [{'key': 'ca.crt', 'path': 'ca.crt'}]}}, {'downwardAPI': {'items': [{'path': 'namespace', 'fieldRef': {'apiVersion': 'v1', 'fieldPath': 'metadata.namespace'}}]}}], 'defaultMode': 420}}], 'containers': [{'name': 'nginx', 'image': 'nginx:1.14.2', 'ports': [{'containerPort': 80, 'protocol': 'TCP'}], 'resources': {}, 'volumeMounts': [{'name': 'kube-api-access-mb9m2', 'readOnly': True, 'mountPath': '/var/run/secrets/kubernetes.io/serviceaccount'}], 'terminationMessagePath': '/dev/termination-log', 'terminationMessagePolicy': 'File', 'imagePullPolicy': 'IfNotPresent'}], 'restartPolicy': 'Always', 'terminationGracePeriodSeconds': 30, 'dnsPolicy': 'ClusterFirst', 'serviceAccountName': 'default', 'serviceAccount': 'default', 'securityContext': {}, 'schedulerName': 'default-scheduler', 'tolerations': [{'key': 'node.kubernetes.io/not-ready', 'operator': 'Exists', 'effect': 'NoExecute', 'tolerationSeconds': 300}, {'key': 'node.kubernetes.io/unreachable', 'operator': 'Exists', 'effect': 'NoExecute', 'tolerationSeconds': 300}], 'priority': 0, 'enableServiceLinks': True, 'preemptionPolicy': 'PreemptLowerPriority'}, 'status': {'phase': 'Pending', 'qosClass': 'BestEffort'}}, 'oldObject': None, 'dryRun': False, 'options': {'kind': 'CreateOptions', 'apiVersion': 'meta.k8s.io/v1', 'fieldManager': 'kubectl-client-side-apply'}}}
  2022-09-14 20:33:50,559: custodian.k8s.policy:INFO Matching event against:{'operations': ['CREATE'], 'resources': 'pods', 'group': 'core', 'apiVersions': 'v1', 'scope': 'Namespaced'}
  2022-09-14 20:33:50,560: custodian.k8s.policy:INFO Event Matched
  2022-09-14 20:33:50,639: custodian.k8s.policy:INFO Filtered from 1 to 1 resource(s)
  2022-09-14 20:33:50,639: custodian.k8s.policy:INFO allowing admission because on-match:warn, matched:1
  10.0.201.111 - - [14/Sep/2022 20:33:50] "POST /?timeout=10s HTTP/1.1" 200 -
  2022-09-14 20:33:50,640: c7n_kube.server:INFO {"apiVersion": "admission.k8s.io/v1", "kind": "AdmissionReview", "response": {"allowed": true, "warnings": ["example-warn-policy:This is a sample policy"], "uid": "2ec4911a-8a9d-4c8d-8aa5-2d3709877fd0", "status": {"code": 200, "message": "OK"}}}

.. kubernetes_k8s-admission-authoring:

Authoring Policies
------------------

The ``k8s-admission`` mode supports both built-in resource types in Kubernetes as well as Custom objects
defined by Custom Resource Definitions. In addition, the mode allows you to specify different behaviors
``on-match``: ``allow``, ``deny``, and ``warn``. In addition, you can specify which operations to
respond to: ``CREATE``, ``UPDATE``, ``DELETE``, and ``CONNECT``.

For ``CREATE``, ``UPDATE``, and ``CONNECT`` operations, the resource that the policy will operate on will be
the incoming resource, i.e. the new object. In the case of the ``DELETE`` operation, the old object will be
used.

In addition to the value filter and any other built in filters, ``k8s-admission`` mode policies can also
filter resources based on the event itself. For instance:

.. code-block:: yaml

   policies:
     - name: event-filter-example
       resource: k8s.pod
       mode:
         type: k8s-admission
         on-match: deny
         operations:
         - CREATE
         - UPDATE
       filters:
         - type: event
           key: request.userInfo.username
           value: foo

A sample event looks like:

.. code-block:: json

  {
     "kind":"AdmissionReview",
     "apiVersion":"admission.k8s.io/v1",
     "request":{
        "uid":"662c3df2-ade6-4165-b395-770857bc17b7",
        "kind":{
           "group":"",
           "version":"v1",
           "kind":"Pod"
        },
        "resource":{
           "group":"",
           "version":"v1",
           "resource":"pods"
        },
        "requestKind":{
           "group":"",
           "version":"v1",
           "kind":"Pod"
        },
        "requestResource":{
           "group":"",
           "version":"v1",
           "resource":"pods"
        },
        "name":"static-web",
        "namespace":"default",
        "operation":"CREATE",
        "userInfo":{
           "username":"kubernetes-admin",
           "groups":[
              "system:masters",
              "system:authenticated"
           ]
        },
        "object":{
           "kind":"Pod",
           "apiVersion":"v1",
           "metadata":{
              "name":"static-web",
              "namespace":"default",
              "uid":"e96b4e07-633e-426d-9a7f-db39676cf0b4",
              "creationTimestamp":"2022-08-25T22:08:33Z",
              "labels":{
                 "role":"myrole"
              },
              "annotations":{
                 "kubectl.kubernetes.io/last-applied-configuration":"{\"apiVersion\":\"v1\",\"kind\":\"Pod\",\"metadata\":{\"annotations\":{},\"labels\":{\"role\":\"myrole\"},\"name\":\"static-web\",\"namespace\":\"default\"},\"spec\":{\"containers\":[{\"image\":\"nginx\",\"name\":\"web\",\"ports\":[{\"containerPort\":80,\"name\":\"web\",\"protocol\":\"TCP\"}]}]}}\n"
              },
              "managedFields":[
                 {
                    "manager":"kubectl-client-side-apply",
                    "operation":"Update",
                    "apiVersion":"v1",
                    "time":"2022-08-25T22:08:33Z",
                    "fieldsType":"FieldsV1",
                    "fieldsV1":{
                       "f:metadata":{
                          "f:annotations":{
                             ".":{

                             },
                             "f:kubectl.kubernetes.io/last-applied-configuration":{

                             }
                          },
                          "f:labels":{
                             ".":{

                             },
                             "f:role":{

                             }
                          }
                       },
                       "f:spec":{
                          "f:containers":{
                             "k:{\"name\":\"web\"}":{
                                ".":{

                                },
                                "f:image":{

                                },
                                "f:imagePullPolicy":{

                                },
                                "f:name":{

                                },
                                "f:ports":{
                                   ".":{

                                   },
                                   "k:{\"containerPort\":80,\"protocol\":\"TCP\"}":{
                                      ".":{

                                      },
                                      "f:containerPort":{

                                      },
                                      "f:name":{

                                      },
                                      "f:protocol":{

                                      }
                                   }
                                },
                                "f:resources":{

                                },
                                "f:terminationMessagePath":{

                                },
                                "f:terminationMessagePolicy":{

                                }
                             }
                          },
                          "f:dnsPolicy":{

                          },
                          "f:enableServiceLinks":{

                          },
                          "f:restartPolicy":{

                          },
                          "f:schedulerName":{

                          },
                          "f:securityContext":{

                          },
                          "f:terminationGracePeriodSeconds":{

                          }
                       }
                    }
                 }
              ]
           },
           "spec":{
              "volumes":[
                 {
                    "name":"kube-api-access-7pc2d",
                    "projected":{
                       "sources":[
                          {
                             "serviceAccountToken":{
                                "expirationSeconds":3607,
                                "path":"token"
                             }
                          },
                          {
                             "configMap":{
                                "name":"kube-root-ca.crt",
                                "items":[
                                   {
                                      "key":"ca.crt",
                                      "path":"ca.crt"
                                   }
                                ]
                             }
                          },
                          {
                             "downwardAPI":{
                                "items":[
                                   {
                                      "path":"namespace",
                                      "fieldRef":{
                                         "apiVersion":"v1",
                                         "fieldPath":"metadata.namespace"
                                      }
                                   }
                                ]
                             }
                          }
                       ],
                       "defaultMode":420
                    }
                 }
              ],
              "containers":[
                 {
                    "name":"web",
                    "image":"nginx",
                    "ports":[
                       {
                          "name":"web",
                          "containerPort":80,
                          "protocol":"TCP"
                       }
                    ],
                    "resources":{

                    },
                    "volumeMounts":[
                       {
                          "name":"kube-api-access-7pc2d",
                          "readOnly":true,
                          "mountPath":"/var/run/secrets/kubernetes.io/serviceaccount"
                       }
                    ],
                    "terminationMessagePath":"/dev/termination-log",
                    "terminationMessagePolicy":"File",
                    "imagePullPolicy":"Always"
                 }
              ],
              "restartPolicy":"Always",
              "terminationGracePeriodSeconds":30,
              "dnsPolicy":"ClusterFirst",
              "serviceAccountName":"default",
              "serviceAccount":"default",
              "securityContext":{

              },
              "schedulerName":"default-scheduler",
              "tolerations":[
                 {
                    "key":"node.kubernetes.io/not-ready",
                    "operator":"Exists",
                    "effect":"NoExecute",
                    "tolerationSeconds":300
                 },
                 {
                    "key":"node.kubernetes.io/unreachable",
                    "operator":"Exists",
                    "effect":"NoExecute",
                    "tolerationSeconds":300
                 }
              ],
              "priority":0,
              "enableServiceLinks":true,
              "preemptionPolicy":"PreemptLowerPriority"
           },
           "status":{
              "phase":"Pending",
              "qosClass":"BestEffort"
           }
        },
        "oldObject":"None",
        "dryRun":false,
        "options":{
           "kind":"CreateOptions",
           "apiVersion":"meta.k8s.io/v1",
           "fieldManager":"kubectl-client-side-apply"
        }
     }
  }
