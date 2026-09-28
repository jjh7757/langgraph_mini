terraform {
  required_version = ">= 1.5"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
  # 원격 backend(S3 등) 없이 로컬 state 사용 — 개인 포트폴리오 규모에는 과함.
  # terraform.tfstate*는 .gitignore로 커밋 제외.
}

provider "aws" {
  region = "ap-northeast-2"
}
