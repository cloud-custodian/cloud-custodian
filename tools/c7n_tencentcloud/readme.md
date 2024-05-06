# Tencent Cloud

a provider for cloud custodian for usage with Tencent Cloud.

# Installation


```shell

pip install c7n-tencentcloud
```


# Usage

To execute policies against tencent cloud you'll need to provide api
credentials for custodian to interact with the cloud apis.

as a best practice create a sub account / cam user with api keys in the console.


```shell

export TENCENTCLOUD_SECRET_ID="xyz"
export TENCENTCLOUD_SECRET_KEY="abc123"
export TENCENTCLOUD_REGION="na-ashburn"
custodian run -v policy.yml
```

region can also be passed on the cli via the `--region` flag, complete list of regions is here
https://www.tencentcloud.com/document/product/213/6091

