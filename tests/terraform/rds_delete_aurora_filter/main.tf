provider "aws" {}

resource "aws_vpc" "main" {
  cidr_block = "10.0.0.0/16"
  tags = {
    Name = "aurora-test-vpc"
  }
}

resource "aws_subnet" "a" {
  vpc_id            = aws_vpc.main.id
  cidr_block        = "10.0.1.0/24"
  availability_zone = "us-east-1a"
}

resource "aws_subnet" "b" {
  vpc_id            = aws_vpc.main.id
  cidr_block        = "10.0.2.0/24"
  availability_zone = "us-east-1b"
}

resource "aws_db_subnet_group" "main" {
  name       = "aurora-test-subnet-group"
  subnet_ids = [aws_subnet.a.id, aws_subnet.b.id]
}

resource "random_password" "master" {
  length  = 16
  special = false
}

resource "aws_rds_cluster" "main" {
  cluster_identifier   = "aurora-test-cluster"
  engine               = "aurora-mysql"
  engine_mode          = "provisioned"
  database_name        = "testdb"
  master_username      = "admin"
  master_password      = random_password.master.result
  db_subnet_group_name = aws_db_subnet_group.main.name
  skip_final_snapshot  = true
  apply_immediately    = true
}

resource "aws_rds_cluster_instance" "main" {
  identifier         = "aurora-test-instance"
  cluster_identifier = aws_rds_cluster.main.id
  instance_class     = "db.t3.medium"
  engine             = aws_rds_cluster.main.engine
  apply_immediately  = true
}
