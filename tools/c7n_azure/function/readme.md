Dev Build Container
--------

1. Clean the development environment

```make clean```

2. Update the `functionapp/config.json` with the policy you want to run (currently the config is baked into the image)

3. Build the container from the root of the Cloud Custodian installation

```docker build --tag cc/funcapppython:v1.0.0 -f tools/c7n_azure/function/Dockerfile .```
