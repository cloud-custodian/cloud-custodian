# sagemaker_endpoint_metrics

Four endpoints sharing one model and one execution role, covering the two
ways SageMaker reports endpoint metrics, each with one that serves traffic
and one that serves none.

`busy` and `idle` are classic endpoints: the model is attached to each
production variant, and metrics are dimensioned by `EndpointName,
VariantName`. `busy` has three variants -- `quiet`, `busy` and `gpu` -- and
everything but `quiet` is invoked, so the recorded data covers variants with
invocations, a variant without, and (in `idle`) an endpoint with none. A
filter that queried only the first variant would report `busy` as idle.
`gpu` is an `ml.g4dn.xlarge`, which is what makes the GPU metrics report;
nothing here uses the GPU, but the instance having one is enough.

`ic` and `ic-idle` are inference-component based: their configurations carry
an execution role and their variants name no model, so each variant is a
compute pool and the model arrives as an inference component. Such an
endpoint publishes its invocations under `InferenceComponentName` alone,
with no `EndpointName` dimension, while its utilization metrics stay
dimensioned by `EndpointName, VariantName`. `ic` is invoked and `ic-idle`
never is, which is how we know an uncalled component endpoint reports zeros
rather than nothing at all.

An endpoint hosting components takes only one variant and its instance type
can't be changed after creation, so `ic` is a GPU pool with one component
reserving the accelerator, and `ic-idle` a cheaper CPU pool.

Neither the AWS provider nor OpenTofu has an inference component resource,
so `aws_cloudformation_stack` stands in for one. Destroying the stack
destroys the component.

`probe_metrics.py` checks `c7n/data/sagemaker_metrics.yaml` against what
these endpoints publish, and documents how to update it. Run it with
credentials for this account once the endpoints are `InService`.

`model.tar.gz` is the smallest artifact the prebuilt XGBoost serving image
will load:

```bash
uv run --no-project --with xgboost python -c "
import xgboost, numpy
d = xgboost.DMatrix(numpy.array([[0.0], [1.0]]), label=numpy.array([0.0, 1.0]))
booster = xgboost.train({'objective': 'reg:squarederror'}, d, num_boost_round=1)
booster.save_model('xgboost-model.json')"
mv xgboost-model.json xgboost-model
tar czf model.tar.gz xgboost-model
```
