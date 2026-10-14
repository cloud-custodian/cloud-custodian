provider "aws" {
  region = "us-east-1"
}

resource "aws_db_instance" "example" {
  allocated_storage   = 20
  storage_type        = "gp2"
  engine              = "mysql"
  engine_version      = "8.0"
  instance_class      = "db.t3.micro"
  db_name             = "testdb"
  username            = "admin"
  password            = "password123"
  skip_final_snapshot = true

  tags = {
    Name = "rds-test-instance"
  }
}
