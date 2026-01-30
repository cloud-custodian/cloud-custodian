
resource "aws_opensearchserverless_security_policy" "encryption-policy" {
  name        = "test-collection"
  type        = "encryption"
  description = "encryption policy for test-collection"
  policy = jsonencode({
    Rules = [
      {
        ResourceType = "collection"
        Resource = [
          "collection/test-collection"
        ]
      }
    ],
    AWSOwnedKey = true
  })
}

resource "aws_opensearchserverless_collection" "test-collection" {
  name       = "test-collection"
  type       = "SEARCH"
  depends_on = [aws_opensearchserverless_security_policy.encryption-policy]
}

resource "aws_opensearchserverless_access_policy" "test-data-policy" {
  name        = "test-collection"
  type        = "data"
  description = "read and write permissions"
  policy = jsonencode([
    {
      Rules = [
        {
          ResourceType = "collection",
          Resource = [
            "collection/test-collection"
          ],
          Permission = [
            "aoss:CreateCollectionItems",
            "aoss:DeleteCollectionItems",
            "aoss:UpdateCollectionItems",
            "aoss:DescribeCollectionItems"
          ]
        },
        {
          ResourceType = "index",
          Resource = [
            "index/test-collection/*"
          ],
          Permission = [
            "aoss:CreateIndex",
            "aoss:DeleteIndex",
            "aoss:UpdateIndex",
            "aoss:DescribeIndex",
            "aoss:ReadDocument",
            "aoss:WriteDocument"
          ]
        }
      ],
      Principal = [
        "arn:aws:iam::444444444444:root"
      ]
    }
  ])
}
