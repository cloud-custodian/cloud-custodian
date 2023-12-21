resource "aws_vpc" "main" {
  cidr_block = "10.0.0.0/16"
}

resource "random_pet" "name1" {
}

resource "random_pet" "name2" {
}

resource "aws_security_group" "n1" {
  name        = random_pet.name1.id
  description = random_pet.name1.id
  vpc_id      = aws_vpc.main.id

}

resource "aws_security_group" "n2" {
  name        = random_pet.name2.id
  description = random_pet.name2.id
  vpc_id      = aws_vpc.main.id
}

resource "aws_vpc_security_group_egress_rule" "n1_to_n2" {
  security_group_id            = aws_security_group.n1.id
  referenced_security_group_id = aws_security_group.n2.id
  ip_protocol                  = -1
}

