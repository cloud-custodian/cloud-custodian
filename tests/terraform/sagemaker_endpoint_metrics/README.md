# sagemaker_endpoint_metrics

Three endpoints sharing one model and one execution role, covering the two
ways SageMaker reports endpoint metrics.

`busy` and `idle` are classic endpoints: the model is attached to each
production variant, and metrics are dimensioned by `EndpointName,
VariantName`. `busy` has two variants and the test invokes only the
*second*, so the recorded data covers a variant with invocations, a variant
without, and (in `idle`) an endpoint with none -- a filter that queried only
the first variant would report `busy` as idle.

`ic` is inference-component based: its configuration carries an execution
role and its variant names no model, so the variant is a compute pool and
the model arrives as an inference component. Such an endpoint publishes its
invocations under `InferenceComponentName` alone, with no `EndpointName`
dimension, while its utilization metrics stay dimensioned by `EndpointName,
VariantName`.

Neither the AWS provider nor OpenTofu has an inference component resource,
so `aws_cloudformation_stack` stands in for one. Destroying the stack
destroys the component.

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
