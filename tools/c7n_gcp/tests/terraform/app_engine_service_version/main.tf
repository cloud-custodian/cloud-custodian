resource "random_id" "suffix" {
  byte_length = 2
}

# Needs an existing App Engine app in the project; see README.md.

data "archive_file" "app_source" {
  type        = "zip"
  source_dir  = "${path.module}/app"
  output_path = "${path.module}/.terraform/app.zip"
}

resource "google_storage_bucket" "source" {
  name                        = "c7n-app-engine-${terraform.workspace}-${random_id.suffix.hex}"
  location                    = "US"
  force_destroy               = true
  uniform_bucket_level_access = true
}

resource "google_storage_bucket_object" "source" {
  name   = "app-${data.archive_file.app_source.output_md5}.zip"
  bucket = google_storage_bucket.source.name
  source = data.archive_file.app_source.output_path
}

resource "google_app_engine_standard_app_version" "secure_always" {
  service    = "default"
  version_id = "c7n-always-${random_id.suffix.hex}"
  runtime    = "nodejs24"

  entrypoint {
    shell = "node app.js"
  }

  deployment {
    zip {
      source_url = "https://storage.googleapis.com/${google_storage_bucket.source.name}/${google_storage_bucket_object.source.name}"
    }
  }

  handlers {
    url_regex                   = "/.*"
    security_level              = "SECURE_ALWAYS"
    redirect_http_response_code = "REDIRECT_HTTP_RESPONSE_CODE_301"

    script {
      script_path = "auto"
    }
  }
}

resource "google_app_engine_standard_app_version" "secure_optional" {
  service    = "default"
  version_id = "c7n-optional-${random_id.suffix.hex}"
  runtime    = "nodejs24"

  entrypoint {
    shell = "node app.js"
  }

  deployment {
    zip {
      source_url = "https://storage.googleapis.com/${google_storage_bucket.source.name}/${google_storage_bucket_object.source.name}"
    }
  }

  handlers {
    url_regex      = "/.*"
    security_level = "SECURE_OPTIONAL"

    script {
      script_path = "auto"
    }
  }
}
