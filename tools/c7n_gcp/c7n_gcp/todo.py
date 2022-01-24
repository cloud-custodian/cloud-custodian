# YOU GOT THIS!!!

## Overall

- tools/c7n_mailer/email_delivery.py
    - Make GCP-friendly
- tools/c7n_mailer/gcp_mailer/gcp_queue_processor.py
    - Slack and Splunk support

## Deployment

- c7n/mu.py # TODO: We also have tools/c7n_gcp/c7n_gcp/mu.py that is possibly a better target
- tools/c7n_mailer/gcp_mailer/deploy.py
- tools/c7n_mailer/gcp_mailer/function.py
- tools/c7n_mailer/gcp_mailer/handle.py

## Tests

- tools/c7n_mailer/tests/google

## Wishlist

- Label support (support `tags` if `labels` isn't present?)
- VPC support
- Documentation
- Stretch goal: AWS support from GCP
- Stretch goal: GCP SendGrid support
  - import c7n_mailer.gcp_mailer.sendgrid_delivery as google_sendgrid # TODO: Generalize, since GCP recommends SendGrid
- Stretch goal: Enable Slack/Datadog support without an email provider (only used for lookups for templates)
