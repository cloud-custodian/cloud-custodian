# sagemaker_endpoint_async_metrics

Two asynchronous inference endpoints sharing one model and one endpoint
configuration: `busy` is invoked when recording and `idle` never is.

This is a fixture of its own rather than more endpoints in
`sagemaker_endpoint_metrics`, because recording against that fixture renames
every endpoint in it, and with them every recording made against it.

`model.tar.gz` is a copy of the one in `../sagemaker_endpoint_metrics`, whose
README says how it's built.
