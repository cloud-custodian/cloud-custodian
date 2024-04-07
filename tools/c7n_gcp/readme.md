# Custodian GCP Support

Status - Alpha

# Features

 - Serverless ✅
 - Api Subscriber ✅
 - Metrics ✅
 - Resource Query ✅
 - Multi Account (c7n-org) ✅

# Getting Started


## via pip

```
pip install c7n-gcp
```

By default custodian will use credentials associated to the gcloud cli, which will generate
warnings per google.auth (https://github.com/googleapis/google-auth-library-python/issues/292)

The recommended authentication form for production usage is to create a service account and
credentials, which will be picked up via by the custodian cli via setting the
*GOOGLE_APPLICATION_CREDENTIALS* environment variable.


# Serverless

Custodian supports both periodic and api call events for serverless
policy execution.

GCP Cloud Functions require cloudbuild api be enabled on the project
the functions are deployed to.

Periodic execution mode also requires cloudscheduler api be enabled on
a project. Cloudscheduler usage also requires an app engine instance
in the same region as the function deployment.
