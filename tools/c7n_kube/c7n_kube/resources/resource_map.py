# Copyright The Cloud Custodian Authors.
# SPDX-License-Identifier: Apache-2.0
ResourceMap = {
    "k8s.config-map": "c7n_kube.resources.core.configmap.ConfigMap",
    "k8s.custom-cluster-resource": "c7n_kube.resources.crd.CustomResourceDefinition",
    "k8s.custom-namespaced-resource": "c7n_kube.resources.crd.CustomNamespacedResourceDefinition",
    "k8s.daemon-set": "c7n_kube.resources.apps.daemonset.DaemonSet",
    "k8s.deployment": "c7n_kube.resources.apps.deployment.Deployment",
    "k8s.namespace": "c7n_kube.resources.core.namespace.Namespace",
    "k8s.node": "c7n_kube.resources.core.node.Node",
    "k8s.pod": "c7n_kube.resources.core.pod.Pod",
    "k8s.replica-set": "c7n_kube.resources.apps.replicaset.ReplicaSet",
    "k8s.replication-controller": (
        "c7n_kube.resources.core.replicationcontroller.ReplicationController"),
    "k8s.secret": "c7n_kube.resources.core.secret.Secret",
    "k8s.service": "c7n_kube.resources.core.service.Service",
    "k8s.service-account": "c7n_kube.resources.core.serviceaccount.ServiceAccount",
    "k8s.stateful-set": "c7n_kube.resources.apps.statefulset.StatefulSet",
    "k8s.volume": "c7n_kube.resources.core.volume.PersistentVolume",
    "k8s.volume-claim": "c7n_kube.resources.core.volume.PersistentVolumeClaim"
}
