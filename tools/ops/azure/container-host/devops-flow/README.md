# Azure DevOps Workflow for Container Host

This directory contains the yaml definitions for CI/CD pipelines to help manage policies in an Azure DevOps repository structure. The two pipelines will:
* Validate policies as part of a Pull Request by running `custodian validate`
* Copy the policy files into a blob storage container that will be picked up by a running container host. This pipeline takes a variable for controlling the folder that should be copied.

In order to use these pipelines directly, you must use a repository in Azure DevOps, however the steps in both of the pipelines can easily be ported to the format of other build providers. If you do not have an existing project, [Create a Project in Azure DevOps](https://docs.microsoft.com/en-us/azure/devops/organizations/projects/create-project?view=azure-devops) before continuing on.

The other needed Azure resource is a storage account with a container to store the policy files. If you follow the directions for hosting Cloud Custodian in a container in Azure, this account will already be created. Otherwise, [Create a Storage Account](https://docs.microsoft.com/en-us/azure/storage/common/storage-quickstart-create-account?tabs=azure-portal) and then [Create a Container](https://docs.microsoft.com/en-us/azure/storage/blobs/storage-quickstart-blobs-portal#create-a-container) to hold policy files.

Remember: For a policy to be executed in a container instance of c7n the mode must be set to either "container-periodic" or "container-event"

- [Azure DevOps Workflow for Container Host](#Azure-DevOps-Workflow-for-Container-Host)
- [Initialize Azure DevOps](#Initialize-Azure-DevOps)
- [Validation Pipeline](#Validation-Pipeline)
  - [Steps to setup Pipeline](#Steps-to-setup-Pipeline)
  - [Pipeline Steps](#Pipeline-Steps)
- [CI Pipeline](#CI-Pipeline)
  - [Steps to setup Pipeline](#Steps-to-setup-Pipeline-1)
  - [Pipeline Steps](#Pipeline-Steps-1)
  - [Support for Multiple Storage Accounts](#Support-for-Multiple-Storage-Accounts)

# Initialize Azure DevOps
For the remainder of this tutorial, you must have a properly configured Azure DevOps instance. The assumed folder structure of the repository is:
```
- policies
  |- policy folder 1
    |- policy1.yaml
    |- policy2.yaml
  |- policy folder 2
    |- policy3.yaml
  ...
- .azure-pipelines
  |- azure-pipelines.yaml
  |- validation-pipeline.yaml
```
Where:
* `policies` is a directory that contains any directory folder of policy yaml files. Only the yaml files within this structure will get copied to blob storage to be run on the containers
* `.azure-pipelines` is a directory that holds all azure pipeline definitions. If other pipelines are desired, then they should also be included in this directory.
* `azure-pipelines.yaml` copied from this directory, it defines the pipeline steps to copy policy files to blob storage
* `validation-pipeline.yaml` copied from this directory, it defines the pipeline that validates any changed policy files before allowing a pull request to be merged into master

This is a very simplistic solution to act as a building block. More complex folder and repository structures can be built up using the same principals for more advanced use cases. One example of keeping policies for different environments in the same directory structure is shown at the end.

# Validation Pipeline

## Steps to setup Pipeline
The validation pipeline is saved in `.azure-pipelines/validation-pipeline.yaml` in the root directory.

1. Create a new pipeline based off of the definition `.azure-pipelines/validation-pipeline.yaml`. The default trigger runs the pipeline when a pull request is opened to master.
2. Set the variable in the build pipeline
    * POLICY_FILE_PATH - Path to the folder of the policy files that should be deployed, for this example it should be `./policies`
3. Add a [build validation](https://docs.microsoft.com/en-us/azure/devops/repos/git/branch-policies?view=azure-devops#build-validation) to the master branch. This prevents PRs from being merged without the policy validation pipeline from completing.

## Pipeline Steps
This pipeline runs `custodian validate` on the policy files that have changed in the incoming PR. It filters to only look at the changed files in the policy file path.
1. Get a list of files that changed between the source and target branch
1. Run `custodian validate` for each of the changed files


# CI Pipeline

## Steps to setup Pipeline
The deployment pipeline is saved in `.azure-pipelines/azure-pipelines.yaml` in the root directory.

1. Create a [service connection](https://docs.microsoft.com/en-us/azure/devops/pipelines/library/service-endpoints?view=azure-devops&tabs=yaml) to the resource group containing the blob storage account
2. Create a new pipeline based off of the definition `.azure-pipelines/azure-pipelines.yaml`
3. Set the variables in the build pipeline
    * AZURE_SERVICE_CONNECTION - Name of the service connection to the resource group containing the storage account
    * STORAGE_ACCOUNT_NAME - Name of the storage account 
    * STORAGE_CONTAINER_NAME - Name of the container in the storage account. Currently the storage container must exist in the storage account or the AZ CLI step of the pipeline will fail.
    * POLICY_FILE_PATH - Path to the folder of policy files that should be deployed, for this example it should be `./policies`

## Pipeline Steps
This is a very simple pipeline, but can evolve in the future to support more complex scenarios:
1. Generate a SAS token to the storage account. It is valid for 10 minutes
1. Synchronize the files from POLICY_FILE_PATH with the container in blob storage. This will delete files from blob storage that no longer exist in the repository

## Support for Multiple Storage Accounts
Pipelines can be used to deploy different subfolders of policy files to different blob storage accounts. For example, let our policy folder structure look like the following:
```
- policies
  |- production
    |- production-policy1.yaml
    |- production-policy2.yaml
  |- staging
    |- staging-policy1.yaml
    |- staging-policy2.yaml
  |- development
    |- development-policy1.yaml
    |- development-policy2.yaml
```

In this scenario we will create three pipelines to deploy to three different blob storage containers. Each of these storage containers will be watched by a kubernetes pod to apply the policies. Note, for development below we will have it deploy all of the policy files and not just the ones in the development folder. This is done by the following steps:

1. Create a service connection for each of the resource groups that contain storage accounts that need to be accessed
1. Create three build pipelines that are each based on `.azure-pipelines/azure-pipelines.yaml` - This way if there is a change to the pipeline file all of the pipelines will be updated automatically rather than updating each one independently
1. Set the build pipeline variables for each instance. The important thing to remember here is that the storage account variables must be for the target account of each environment. Examples of what the values may look like are:
    * Production
        * AZURE_SERVICE_CONNECTION: CloudCustodianProduction
        * STORAGE_ACCOUNT_NAME: ContainerHostCCProduction
        * STORAGE_CONTAINER_NAME: policies
        * POLICY_FILE_PATH: ./policies/production
    * Staging
        * AZURE_SERVICE_CONNECTION: CloudCustodianStaging
        * STORAGE_ACCOUNT_NAME: ContainerHostCCStaging
        * STORAGE_CONTAINER_NAME: policies
        * POLICY_FILE_PATH: ./policies/staging
    * Development
        * AZURE_SERVICE_CONNECTION: CloudCustodianDevelopment
        * STORAGE_ACCOUNT_NAME: ContainerHostCCDevelopment
        * STORAGE_CONTAINER_NAME: policies
        * POLICY_FILE_PATH: ./policies
