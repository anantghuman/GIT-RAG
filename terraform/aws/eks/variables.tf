variable "aws_region" {
  type    = string
  default = "us-east-1"
}

variable "project_name" {
  type    = string
  default = "git-rag"
}

variable "vpc_cidr" {
  type    = string
  default = "10.42.0.0/16"
}

variable "db_username" {
  type    = string
  default = "gitrag"
}

variable "db_password" {
  type      = string
  sensitive = true
}

variable "openai_api_key" {
  type      = string
  sensitive = true
  default   = ""
}

variable "pinecone_api_key" {
  type      = string
  sensitive = true
  default   = ""
}

variable "github_webhook_secret" {
  type      = string
  sensitive = true
  default   = ""
}
