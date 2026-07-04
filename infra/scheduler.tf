# Scheduled stop/start — demo app runs weekday business hours only (ET).
# Weekends: no start schedule fires, so the instance stays stopped from
# Friday 8pm until Monday 8am.

resource "aws_iam_role" "scheduler" {
  name = "${var.app_name}-scheduler-role"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "scheduler.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
  tags = { App = var.app_name }
}

resource "aws_iam_role_policy" "scheduler_ec2" {
  name = "${var.app_name}-scheduler-ec2"
  role = aws_iam_role.scheduler.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["ec2:StartInstances", "ec2:StopInstances"]
      Resource = "arn:aws:ec2:${var.aws_region}:*:instance/${aws_instance.app.id}"
    }]
  })
}

resource "aws_scheduler_schedule" "start" {
  name = "${var.app_name}-start"

  flexible_time_window {
    mode = "OFF"
  }

  schedule_expression          = var.ec2_start_cron
  schedule_expression_timezone = "America/New_York"

  target {
    arn      = "arn:aws:scheduler:::aws-sdk:ec2:startInstances"
    role_arn = aws_iam_role.scheduler.arn
    input    = jsonencode({ InstanceIds = [aws_instance.app.id] })
  }
}

resource "aws_scheduler_schedule" "stop" {
  name = "${var.app_name}-stop"

  flexible_time_window {
    mode = "OFF"
  }

  schedule_expression          = var.ec2_stop_cron
  schedule_expression_timezone = "America/New_York"

  target {
    arn      = "arn:aws:scheduler:::aws-sdk:ec2:stopInstances"
    role_arn = aws_iam_role.scheduler.arn
    input    = jsonencode({ InstanceIds = [aws_instance.app.id] })
  }
}
