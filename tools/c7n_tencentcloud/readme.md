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

## Credential Configuration

### Method 1: Environment Variables

```shell
export TENCENTCLOUD_SECRET_ID="xyz"
export TENCENTCLOUD_SECRET_KEY="abc123"
export TENCENTCLOUD_REGION="na-ashburn"
custodian run -v policy.yml
```

### Method 2: Profile Configuration (Recommended)

Create a credentials file at `~/.tencentcloud/credentials`:

```ini
[default]
secret_id = your_default_secret_id
secret_key = your_default_secret_key
region = ap-singapore

[production]
secret_id = your_prod_secret_id
secret_key = your_prod_secret_key
region = na-ashburn

[development]
secret_id = your_dev_secret_id
secret_key = your_dev_secret_key
region = ap-singapore
```

Then use the `--profile` parameter:

```shell
# Use default profile
custodian run -v policy.yml --output-dir ./output

# Use specific profile
custodian run -v policy.yml --profile production --output-dir ./output
```

region can also be passed on the cli via the `--region` flag, complete list of regions is here
https://www.tencentcloud.com/document/product/213/6091

