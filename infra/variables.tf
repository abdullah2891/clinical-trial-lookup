variable "aws_region" {
  description = "AWS region to deploy into"
  type        = string
  default     = "us-east-1"
}

variable "app_name" {
  description = "Resource name prefix"
  type        = string
  default     = "clinical-trials"
}

variable "instance_type" {
  description = "EC2 instance type. t3.large (2 vCPU/8 GB) is the minimum for pgvector + parallel GPT calls."
  type        = string
  default     = "t3.large"
}

variable "root_volume_size_gb" {
  description = "Root EBS volume size in GB. 50 GB covers OS + Docker images + pgvector data."
  type        = number
  default     = 50
}

variable "allowed_ssh_cidr" {
  description = "CIDR allowed for SSH. Restrict to your IP in production (e.g. 1.2.3.4/32)."
  type        = string
  default     = "0.0.0.0/0"
}

variable "github_repo" {
  description = "HTTPS URL of the GitHub repo to clone on the EC2 instance"
  type        = string
  # Replace with your actual repo URL
  default     = "https://github.com/YOUR_USERNAME/clinical-trials-lookup.git"
}

variable "github_branch" {
  description = "Git branch to deploy"
  type        = string
  default     = "main"
}

variable "ec2_start_cron" {
  description = "EventBridge cron (America/New_York) to start the instance"
  type        = string
  default     = "cron(0 8 ? * MON-FRI *)" # 8:00 AM ET weekdays
}

variable "ec2_stop_cron" {
  description = "EventBridge cron (America/New_York) to stop the instance"
  type        = string
  default     = "cron(0 20 ? * MON-FRI *)" # 8:00 PM ET weekdays
}

variable "openai_api_key" {
  description = "OpenAI API key — stored in SSM SecureString, never in plaintext"
  type        = string
  sensitive   = true
}

variable "db_password" {
  description = "Password for the clinical_trials Postgres database"
  type        = string
  sensitive   = true
}
