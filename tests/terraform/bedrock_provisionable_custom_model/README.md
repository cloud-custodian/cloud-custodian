# NOTE!

The fixture set up here is **long-lived**. It takes too long to create to be
created and destroyed when running the tests that need it -- fine-tuning a
custom model takes hours, most of it queued waiting for training capacity.

So, unlike most fixtures in `tests/terraform`, this one is **applied manually,
out of band**, and is *not* managed by pytest-terraform. No test declares
`@terraform("bedrock_provisionable_custom_model")`, and none should. The tests
reference the resulting model only through `CUSTOM_MODELS` in
`tests/test_bedrock.py`, by **model name**.

# Bedrock "provisionable" custom model fixture

Builds the long-lived custom model that backs the `provisioned-throughputs`
filter tests on `aws.bedrock-custom-model`.

## Why the model is not a Terraform resource

`aws_bedrock_custom_model` *owns* the model -- its destroy deletes the model the
customization job produced. This model must survive `tofu destroy` of its
prerequisites, so Terraform here creates **only** the transient pieces (S3
buckets, training data object, IAM role) and
`setup.py` submits the customization job. The model is
unmanaged by design: the only way to delete it is a deliberate
`DeleteCustomModel`.

Related: a customization **job** can never be deleted (there is no
`DeleteModelCustomizationJob` API, only `Stop`), so jobs accumulate in the
account permanently. `setup.py` timestamps each job name to keep them unique.

`setup.py` also does not wait for the job. Customization takes hours, nearly all
of it queued waiting for training capacity, so blocking is impractical -- and
credentials tend to expire out from under a long wait. It submits and prints the
command to check on it.

## Why this base model

`meta.llama3-1-8b-instruct-v1:0:128k` in **us-west-2**, because the
`provisioned-throughputs` filter needs a custom model whose **only** serving
path is provisioned throughput. Llama 3.1 8B is
[PT-supported](https://docs.aws.amazon.com/bedrock/latest/userguide/prov-thru-supported.html)
but is *not* on the on-demand custom-model-deployment eligible list, which makes
it exactly right here. (Llama 3.3 70B is the opposite -- deployment-eligible but
not PT-supported -- so it backs `../bedrock_deployable_custom_model`.)

Llama 3.1 fine-tuning uses the non-conversational `{"prompt", "completion"}`
format with a minimum of 100 records. `train.jsonl` holds 120 trivial Q&A
records; the content is irrelevant, only a valid completed model is needed.

## Quota required to use it

Creating a provisioned throughput on this model needs two service quota
increases in **us-west-2**, both adjustable and both `0` by default:

| Quota code | Name |
|---|---|
| `L-3632DE15` | Model units per provisioned model for Meta Llama 3.1 8B Instruct |
| `L-BE77399C` | Model units no-commitment Provisioned Throughputs across custom models |

1 model unit each is enough. Without them,
`CreateProvisionedModelThroughput` fails with:

> `ServiceQuotaExceededException: Your account does not currently have any no
> commitment model units reserved for meta.llama3-1-8b-instruct-v1:0:128k.`

Unlike an on-demand deployment (no idle cost), a provisioned throughput is
**billed per model-unit-hour while it exists** -- create it, record, and delete
it promptly.

## Naming and tags

The model name is fixed at **`KEEP-c7n-provisionable-test-fixture`** -- no
random suffix -- for two reasons:

1. The tests select it by `modelName`, so a rebuild needs no test-code edit
   (only re-recording). The model name never appears in the model ARN, whose
   trailing id is AWS-generated and changes on every rebuild.
2. Cleanup in this shared account is a **manual** process, and an earlier build
   of this model was deleted by a colleague (confirmed via CloudTrail). Model
   names are what a human sees in the console's **Custom models -> Models** tab
   and the **Jobs** list. Those columns truncate near 17 characters, so the
   warning and the role come first: `KEEP-c7n-provisio...`.

Tags carry the readable explanation for whoever clicks in (`KEEP`, `owner`,
`purpose`); `setup.py` applies them to both the job and the model. If automated
cleanup is ever introduced, a name prefix will not stop it -- only whatever tag
key the reaper honors, so revisit the `KEEP` key then.

## Building (or rebuilding) the model

Requires credentials for the recording account and `tofu` on PATH.

```bash
cd tests/terraform/bedrock_provisionable_custom_model
tofu init
tofu apply     # prerequisites only; no model yet
../../../.venv/bin/python setup.py    # submits the customization job and exits
```

`setup.py` needs `boto3`, so run it with the repo's virtualenv as above
(a bare `./setup.py` will use the system interpreter and fail on the import).

`setup.py` prints the job ARN and the command to check on it. Expect **hours**
(~3.5h observed end-to-end for this model; data validation alone takes ~3
minutes, then the job sits queued waiting for training capacity):

```bash
aws bedrock get-model-customization-job --region us-west-2 \
  --job-identifier <job arn> \
  --query '{status:status,training:statusDetails.trainingDetails.status,model:outputModelArn}'
```

Once `status` is `Completed`, tear down the prerequisites -- the model is not
managed by Terraform and must survive this:

```bash
tofu destroy
aws bedrock list-custom-models --region us-west-2   # model still listed
```

Training cost is trivial (~$0.002 at $0.00149/1K tokens); the model then costs
**$1.95/month** to store for as long as it is kept.

## The model survives teardown

Destroying the prerequisites does not affect a completed model: Bedrock holds
its own copy and does not read these buckets at inference time. Verified
2026-07-28 for both fixture models -- after `tofu destroy` each remained
`Active` (and the sibling deployable model could still be deployed on demand).

To re-check after a future rebuild:

```bash
aws bedrock get-custom-model --region us-west-2 \
  --model-identifier KEEP-c7n-provisionable-test-fixture    # Active
```

## After rebuilding

The model ARN changes (new AWS-generated id), but the **name does not**, so
`CUSTOM_MODELS` in `tests/test_bedrock.py` needs no edit. The recorded flight
data does contain the old ARN, so re-record the affected tests.
