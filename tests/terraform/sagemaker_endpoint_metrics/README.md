# sagemaker_endpoint_metrics

Two endpoints sharing one model: `busy` has two production variants, `idle`
has one. The test invokes only `busy`'s *second* variant, so the recorded
CloudWatch data covers a variant with invocations, a variant without, and an
endpoint with none -- and a filter that queried only the first variant would
report the busy endpoint as idle.

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
