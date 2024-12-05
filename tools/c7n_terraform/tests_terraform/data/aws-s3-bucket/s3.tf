resource "aws_s3_bucket" "b" {
  bucket = var.mybucket
  acl    = "public-read"
  policy = file("policy.json")

  tags = local.common_tags

  website {
    index_document = "index.html"
    error_document = "error.html"

    routing_rules = <<EOF
    [{
        "Condition": {
	        "KeyPrefixEquals": "docs/"
		    },
		        "Redirect": {
			        "ReplaceKeyPrefixWith": "documents/"
				    }
				    }]
				    
    EOF
  }
}
