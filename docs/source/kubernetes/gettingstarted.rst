.. _kubernetes_gettingstarted:

Getting Started (Alpha)
=======================

The Kubernetes Provider (Alpha) is an optional package which an be installed to enable writing
policies which interact with Kubernetes related resources.


.. kubernetes_install-cc:

Install Kubernetes Plugin
-------------------------

First, ensure you have :ref:`installed the base Cloud Custodian application
<install-cc>`. Cloud Custodian is a Python application and must run on an
`actively supported <https://devguide.python.org/#status-of-python-branches>`_
version. 

Once the base install is complete, you are now ready to install the Kubernetes provider package
using one of the following options:

Option 1: Install released packages to local Python Environment
"""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""""

.. code-block:: bash

    pip install c7n
    pip install c7n-kube


Option 2: Install latest from the repository
"""""""""""""""""""""""""""""""""""""""""""""

.. code-block:: bash

    git clone https://github.com/cloud-custodian/cloud-custodian.git
    pip install -e ./cloud-custodian
    pip install -e ./cloud-custodian/tools/c7n_kube

.. _kubernetes_authenticate:

Connecting to your Cluster
--------------------------

The Custodian Kubernetes provider automatically uses your kubectl configuration or the config
file set by the environment variable ``KUBECONFIG``. See the `Kubernetes Docs <https://kubernetes.io/docs/concepts/configuration/organize-cluster-access-kubeconfig/>`_
for more information.

.. _kube_write-policy:

Write Your First Policy
-----------------------
A policy is the primary way that Custodian is configured to manage cloud resources.
It is a YAML file that follows a predetermined schema to describe what you want
Custodian to do.

There are three main components to a policy:

* Resource: the type of resource to run the policy against
* Filters: criteria to produce a specific subset of resources
* Actions: directives to take on the filtered set of resources

In the example below, we will write a policy that filters for pods with a label "custodian"
and deletes it:

First, lets create a pod resource that we want to target with the policy:

.. code-block:: bash

   ❯ kubectl run nginx --image=nginx --labels=name=custodian
   ❯ kubectl get pod -o wide --show-labels
    NAME    READY   STATUS    RESTARTS   AGE   IP           NODE     NOMINATED NODE   READINESS GATES   LABELS
    nginx   1/1     Running   0          24s   10.0.1.224   worker   <none>           <none>            name=custodian

Now in the example below, we will write a policy that filters for pods with a
label "custodian" and deletes it:

Filename: ``custodian.yml``

.. code-block:: yaml

    policies:
      - name: my-first-policy
        description: |
          Deletes pods with label name:custodian
        resource: k8s.pod
        filters:
          - type: value
            key: metadata.labels.name
            value: custodian
        actions:
          - type: delete

.. _kube_run-policy:

Run Your Policy
---------------
First, ensure you have :ref:`configured connectivity to your cluster <kubernetes_authenticate>`.

Next, run the following command to execute the policy with Custodian:

.. code-block:: bash

   custodian run --output-dir=output custodian.yml --cache-period 0 -v

If successful, you should see output similar to the following on the command line::

  2022-09-14 12:28:38,735: custodian.cache:DEBUG Disabling cache
  2022-09-14 12:28:38,735: custodian.commands:DEBUG Loaded file pod.yaml. Contains 1 policies
  2022-09-14 12:28:38,736: custodian.output:DEBUG Storing output with <LogFile file://output/my-first-policy/custodian-run.log>
  2022-09-14 12:28:38,737: custodian.policy:DEBUG Running policy:pod resource:k8s.pod region:default c7n:0.9.18
  2022-09-14 12:28:38,754: custodian.k8s.client:DEBUG connecting to https://127.0.0.1:61427
  2022-09-14 12:28:38,819: custodian.resources.pod:DEBUG Filtered from 17 to 1 pod
  2022-09-14 12:28:38,820: custodian.policy:INFO policy:pod resource:k8s.pod region: count:1 time:0.08
  2022-09-14 12:28:38,837: custodian.k8s.client:DEBUG connecting to https://127.0.0.1:61427
  2022-09-14 12:28:38,863: custodian.policy:INFO policy:pod action:deleteresource resources:1 execution_time:0.04
  2022-09-14 12:28:38,864: custodian.output:DEBUG metric:ResourceCount Count:1 policy:pod restype:k8s.pod scope:policy

You should also find a new ``output/my-first-policy`` directory with a log and other
files (subsequent runs will append to the log by default, rather than
overwriting it).

See :ref:`filters` for more information on the features of the Value filter used in this sample.

You can also use `custodian schema` to get more information on the filters
available to you.

.. code-block:: bash

    ❯ custodian schema k8s
    resources:
    - k8s.config-map
    - k8s.custom-cluster-resource
    - k8s.custom-namespaced-resource
    - k8s.daemon-set
    - k8s.deployment
    - k8s.namespace
    - k8s.node
    - k8s.pod
    - k8s.replica-set
    - k8s.replication-controller
    - k8s.secret
    - k8s.service
    - k8s.service-account
    - k8s.stateful-set
    - k8s.volume
    - k8s.volume-claim

To understand which values are available for a resource you can use `kubectl`,
so for example to understand what attributes a persistent volume has on it you
can run:

.. code-block:: bash

   ❯ kubectl explain persistentvolume --recursive
    KIND:     PersistentVolume
    VERSION:  v1

    DESCRIPTION:
         PersistentVolume (PV) is a storage resource provisioned by an
         administrator. It is analogous to a node. More info:
         https://kubernetes.io/docs/concepts/storage/persistent-volumes

    FIELDS:
       apiVersion   <string>
       kind <string>
       metadata     <Object>
          annotations       <map[string]string>
          creationTimestamp <string>
          deletionGracePeriodSeconds        <integer>
          deletionTimestamp <string>
          finalizers        <[]string>
          generateName      <string>
          generation        <integer>
          labels    <map[string]string>

     ....

Or if you have a resource already deployed in your cluster and you want to
figure out how to taret it you can output it to `json` and review the available
attributes that way:


.. code-block:: bash

   ❯ kubectl get pv node-pv-volume -o json

    {
        "apiVersion": "v1",
        "kind": "PersistentVolume",
        "metadata": {
            "annotations": {
                "kubectl.kubernetes.io/last-applied-configuration": "{\"apiVersion\":\"v1\",\"kind\":\"PersistentVolume\",\"metadata\":{\"annotations\":{},\"labels\":{\"type\":\"local\"},\"name\":\"node-pv-volume\"},\"spec\":{\"accessModes\":[\"ReadWriteOnce\"],\"capacity\":{\"storage\":\"1Gi\"},\"hostPath\":{\"path\":\"/tmp/k8s\"},\"storageClassName\":\"manual\"}}\n"
            },
            "creationTimestamp": "2022-10-14T19:34:45Z",
            "finalizers": [
                "kubernetes.io/pv-protection"
            ],
            "labels": {
                "type": "local"
            },
            "name": "node-pv-volume",
            "resourceVersion": "394700",
            "uid": "ad414486-9fd9-48ac-8cc5-7d6b9c24b524"
        },
        "spec": {
            "accessModes": [
                "ReadWriteOnce"
            ],
            "capacity": {
                "storage": "1Gi"
            },
            "hostPath": {
                "path": "/tmp/k8s",
                "type": ""
            },
            "persistentVolumeReclaimPolicy": "Retain",
            "storageClassName": "manual",
            "volumeMode": "Filesystem"
        },
        "status": {
            "phase": "Available"
        }
    }
