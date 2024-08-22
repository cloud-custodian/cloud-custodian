# Custodian Aliyun Support

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
pip install -e tools/c7n_aliyun
```

```
ALIYUN_ACCESSKEYID='xxxx' 
ALIYUN_ACCESSSECRET='xxxxxxxxxx' 
ALIYUN_DEFAULT_REGION='cn-shenzhen' 
custodian run -s . policy.yml
```

# Serverless

Custodian supports both periodic and api call events for serverless policy execution.
