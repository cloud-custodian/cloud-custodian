# Example lifted from
# https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/iam_server_certificate

provider "aws" {
  region = "us-east-1"
}

resource "aws_iam_server_certificate" "test_cert_alt" {
  name = "alt_test_cert"

  certificate_body = <<EOF
-----BEGIN CERTIFICATE-----
MIIDbzCCAlegAwIBAgIUcw3NyQThmWFTEOb1sA/TJB6ii64wDQYJKoZIhvcNAQEL
BQAwRzELMAkGA1UEBhMCREUxDzANBgNVBAcMBkJlcmxpbjEVMBMGA1UECgwMVGVz
dCBDb21wYW55MRAwDgYDVQQDDAdmb28uY29tMB4XDTIwMTExMTE1MDg1NFoXDTIw
MTExMjE1MDg1NFowRzELMAkGA1UEBhMCREUxDzANBgNVBAcMBkJlcmxpbjEVMBMG
A1UECgwMVGVzdCBDb21wYW55MRAwDgYDVQQDDAdmb28uY29tMIIBIjANBgkqhkiG
9w0BAQEFAAOCAQ8AMIIBCgKCAQEAoeBN2aK8NVEUuToK45zgaenGpeP7IpRl0v2o
Ln6NpEZkpRBCsgG+vvb5FQ6gZT8nDDp+UXt4+J6CXcz015ycPcYFMId5xg3uyZZA
iBPJvhbZoJDAgioxcLVmOj5QA6kWRi+g6SIa+LAbDASGiCStegGZrOZbDx0v0vL2
zgrx41yMg+nYEMicERQslpJGjj1Z74NMhU/LaeCPhprWmuVvZ294RPK788nJK4/k
nSRVy7MSdnqLqUNboKi+BISwVyyoXyAy/R0d9dAJrzSQSsXtsCCUmCgW9R066Dv+
JwuAhPoRfGc6ADHXfdLpuTPilzu0gLrSrCut2jpmXdB0G3vD4wIDAQABo1MwUTAd
BgNVHQ4EFgQUJlWc3glW1lX5sPkzfo9PyHx0gMYwHwYDVR0jBBgwFoAUJlWc3glW
1lX5sPkzfo9PyHx0gMYwDwYDVR0TAQH/BAUwAwEB/zANBgkqhkiG9w0BAQsFAAOC
AQEANHj4uGDtuzHkZCsa7Ax32lgDakWDTRpnKR91L5pVSxwHEB7wEle0qyZjgkPd
Xnyay3Sc9U+ZmHkotRv0kZVEqdVNHTlT5p5SeFuXGTkhzep3Avo11FMutsPFimpu
cdX54TqxMQlKofd8MV7H2tLIAooEN29U/sV5YdsNqxxmHuTNKwe8hamjhy9mCaSF
Rt7rUsMa+aYfug6ASWYYWCID5DKI6dYvi24/C9ItMKuEwT1XcLPIslx1NZ22EfLz
9I15cn24mUdwfu7oWWinhJDkDtvcdUCT125uXOZq2Pl2hMGhMEiVimZG7L8CZp2N
U4KJDlF/hGTe2VWJj+W/yvUycQ==
-----END CERTIFICATE-----
EOF

  private_key = <<EOF
-----BEGIN PRIVATE KEY-----
MIIEvgIBADANBgkqhkiG9w0BAQEFAASCBKgwggSkAgEAAoIBAQCh4E3Zorw1URS5
OgrjnOBp6cal4/silGXS/agufo2kRmSlEEKyAb6+9vkVDqBlPycMOn5Re3j4noJd
zPTXnJw9xgUwh3nGDe7JlkCIE8m+FtmgkMCCKjFwtWY6PlADqRZGL6DpIhr4sBsM
BIaIJK16AZms5lsPHS/S8vbOCvHjXIyD6dgQyJwRFCyWkkaOPVnvg0yFT8tp4I+G
mtaa5W9nb3hE8rvzyckrj+SdJFXLsxJ2eoupQ1ugqL4EhLBXLKhfIDL9HR310Amv
NJBKxe2wIJSYKBb1HTroO/4nC4CE+hF8ZzoAMdd90um5M+KXO7SAutKsK63aOmZd
0HQbe8PjAgMBAAECggEBAJJvrT1SH9xDivG89hjN0508Y/2x7X9sq2hhGwFkbpHL
NES2Hv+U4I80MEPCRYsRxCslxxvDDL4r9lcQj/V0sUqYlh0+kQR/miI2kA4JiJkz
ZpAAIoYd0Tfaga3yrMOC9KltcK01sxyBgxYuCd2jAGO8it6ETJ+xkY/NR0NBV2yK
3dvh5G/RaOK02AgIc9W+XIlEZ2Y4oVX9OKs7Ey2reZOFpZ7LhcuoZL2BykZHOKJO
MqZ9oWCD9YldyuqyU7IUwrydVfceQ6rTTJ8liAxX6UYy0AlALTWnW74kAoSXcv/1
DcZK36B6KxSYagdtD+BTdWz5s88Em5DcHB/vWEsMd8ECgYEA1BYgr19DzoDLXwor
cd5mm7i5uQG9x5JOsuWDzeP7b6hsnS7j4MGP5oYqNTyWII7ucaxGVHy5vzjscjdo
zlJ/VI4ZtFP8bg4lKtbRgYtA/zhbE43voDkQjQ/3UStsk2UXHslImYNAVuXqRMDO
mBg572gXgX2jKWgxgj3t02aPzfMCgYEAw2S6QqM1m1yHhhS2O1FFzVZiAlsKf8sb
ABQZGt1IDKceUE1VMdq5a+0OqyvMurpIF2Lw3PXqxFL+mB/+LEl4ZKjbyWd3ZhrQ
nwxmyrjaNL98PjRxCXQ85aUTE2Mf6IG98Ylg6MrVUOSVD79tXmeszxqGPp6jAHQb
2gvIX35qflECgYBPL1fSwpnZfyLvgCeKY0QiPg0xsyG9YrX5e1IDzGwzW0n6QeiZ
IQvuQQd/SviufU8vp+e2Yb8kU0eMuX1rE0gxNMEKIBVurd9YqE4etPR2lf8DRQpD
4yp30I9BghoOyj6govx1PJkIGN2n/+jixqDS7yVflp4Vtq5Nd3vVY0Sr2wKBgHez
fJwYSl38SJYumBksx/tsgSx6Q6tYbRkWNu8LQvllZB/D0H5zRYbFumfItGpsdn/F
QFPNX96YDZp6dwcAl33rKIJxHWdy4/2b5lko95y69k1RaTJmgGwbPd1xq3mQCiIv
jCvxHs+oyVzVZBYio25ZDIbOPoOnnextrXo7AtiRAoGBAJOYYW9HPdB+Wx7jNGjq
vgjo7sZkwCTtGtRWPWk1Eqi7dGzByat2hzodLZ3U7bnIjb3ZXQLdYUO4N8wmATc0
q8hTLmcBKedh8RzkSvHjGYtlL8sYED3e2CxKrP6V7ZtXjuI1Vg+Xj8WR28f+1l4T
ekMDdPBzdHE2OSZzU6Bz3DyF
-----END PRIVATE KEY-----
EOF
}
