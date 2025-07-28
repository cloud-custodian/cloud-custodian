# Changelog - ManoMano Cloud Custodian Fork

This document outlines the modifications and enhancements made to the upstream Cloud Custodian project by ManoMano.

## Branch: 0.9.46.0 (Current)

### New Resources

This fork includes the following Kubernetes resources that may not be present in the upstream master branch:

- **cron-job** - Kubernetes CronJob resource management
- **daemon-set** - Kubernetes DaemonSet resource management
- **deployment** - Enhanced Kubernetes Deployment resource management
- **stateful-set** - Enhanced Kubernetes StatefulSet resource management
- **replica-set** - Kubernetes ReplicaSet resource management
- **pod** - Enhanced Kubernetes Pod resource management
- **config-map** - Kubernetes ConfigMap resource management
- **secret** - Kubernetes Secret resource management
- **service** - Kubernetes Service resource management
- **service-account** - Kubernetes ServiceAccount resource management
- **namespace** - Kubernetes Namespace resource management
- **node** - Kubernetes Node resource management
- **volume** - Kubernetes Volume resource management
- **volume-claim** - Kubernetes PersistentVolumeClaim resource management
- **role** - Kubernetes Role resource management
- **cluster-role** - Kubernetes ClusterRole resource management
- **replication-controller** - Kubernetes ReplicationController resource management
- **custom-namespaced-resource** - Custom namespaced resource management
- **custom-cluster-resource** - Custom cluster resource management

### New Actions

This fork includes the following enhanced or new actions:

- **PatchAndWaitAction** - New action class for StatefulSets that patches resources and waits for completion
- **EventAction** - Enhanced event-based action handling
- **MethodAction** - Base class for method-based actions
- **PatchAction** - Enhanced patch functionality for Kubernetes resources
- **PatchResource** - Resource-specific patching capabilities
- **DeleteAction** - Enhanced delete functionality
- **DeleteResource** - Resource-specific deletion capabilities
- **LabelAction** - Advanced labeling functionality for Kubernetes resources
- **EventLabelAction** - Event-based labeling actions
- **AutoLabelUser** - Automatic user labeling functionality

### Infrastructure Enhancements

- **Threaded Processing** - Non-priority resources are now processed in threads for improved performance
- **ECR Integration** - Custom build and push scripts for AWS ECR deployment
- **Docker Multi-architecture** - Support for ARM64 architecture builds
- **Time Zone Support** - Enhanced timezone handling capabilities
- **Custom Resource Support** - Added core_mm.py with extended PatchAction and PatchResource classes for NodePools and custom resource handling and add the offhour/offhour filter

### Build and Deployment

- **build-and-push.sh** - Automated script for building and pushing Docker images to AWS ECR
- **images.hcl** - Docker build configuration for multi-platform builds
- **Custom Docker Images** - Specialized Docker images with AWS CLI and kubectl pre-installed

### Removed Components

The following components have been removed from this fork:

- **TencentCloud Provider** - Removed tencentcloud support
- **OpenStack Provider** - Removed openstack support
- **Compression ZSTD** - Removed zstd compression support

## Installation

### Using Poetry (Recommended)

```bash
poetry install
poetry shell
```

### Building and Pushing to ECR

```bash
./build-and-push.sh
```

This script:
- Logs into AWS ECR using the manomano-support profile
- Builds Docker images for linux/arm64 platform
- Pushes images to the ManoMano ECR registry (304971447450.dkr.ecr.eu-west-3.amazonaws.com)
- Uses version tag `mm-0.9.46.0`

## Version Information

- **Base Version**: 0.9.46.0
- **ManoMano Version**: mm-0.9.46.0
- **Docker Registry**: 304971447450.dkr.ecr.eu-west-3.amazonaws.com
- **Platform Support**: linux/arm64