resource "aws_launch_template" "bare_list_reference" {
  image_id = data.aws_ami_ids.al2.ids[0]
}

resource "aws_launch_template" "parenthesized_list_reference" {
  image_id = (data.aws_ami_ids.al2.ids)[0]
}

data "aws_ami_ids" "al2" {
  name_regex = "^amzn2-*"
  owners     = ["amazon"]
}
