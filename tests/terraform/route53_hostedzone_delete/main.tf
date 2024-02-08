resource "aws_route53_zone" "test_hosted_zone" {
  name = "custodian.net"

  tags = {
    "TestTag" = "yes"
  }
}

resource "aws_route53_record" "test_r53_record" {
  zone_id = aws_route53_zone.test_hosted_zone.zone_id
  name    = "test.custodian.net"
  type    = "A"
  ttl     = "300"
  records = ["1.1.1.1"]
}
