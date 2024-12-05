resource "random_id" "user" {
  prefix      = "testuser-"
  byte_length = 4
}

resource "aws_iam_user" "user" {
  name = random_id.user.hex
  path = "/"
}

resource "aws_iam_user_ssh_key" "key1" {
  username   = aws_iam_user.user.name
  encoding   = "SSH"
  public_key = "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABAQCuxTuI+dUrkxojQJdVa4s7G59corPjSHyFkZy4h4JCpkPLMPP4RJE+6KQWk9eEsUxE90YnI17WxJc6uHY56xVZsPGyTbSobEFk4poufQ2MpCj08slWYkfpMw2yOYIuBZoYtw6IbqYq4tuQLdSx9TOAC3C7hdp0OtNgaDelAha1jiNChwFGheXQCM5T+py/QPMJsEL7Iqf3O0DppXwfCWjV3nIjiqvPtgypxE5Zzj8xPu64cjqfd0GavPzmj/ukxOSinepkx7GRx31DWIJvk8FLF6xSjERy2Ooo7lAu1nFl9pFefOt4hJ5UUpdcbYO8MNZzYfrqu/E5wBd7sGSClY79"
  status     = "Inactive"
}

resource "aws_iam_user_ssh_key" "key2" {
  username   = aws_iam_user.user.name
  encoding   = "SSH"
  public_key = "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABAQC7ubAyrW3Ex0sbaK1T/pkOS5eUH2Cn0cHSWSmYj3+XNgLV+YpyVZ6JbAMIWDcqTSdiMmM7Eh1bQg/3n6G9MgAFRmcs66ZRqOWaVPALGNGY1uIsVYKcnDLM7ecPGm8Habh0tyCG8pYlL/qiwYyXjvVy2ECMfsZCZ5BSpmsfVet3u5Dw0ztCPkqztLLBzNtFKd47YTAhvAD7YH2jVDe6uhXWT2L8il64F+189RhRsdDzqHYKAZZEFvRJH8GJoPf6r9mdoGUhxzz0USQvqrSYQi3PBMELt7cUWUKx6gYq86C7tNkp9a6cMwKDqXqqJa4pZtlsq1JtaRgoErpcd/ORfOZn"
}
