# 이 앱 때문에 새로 생기는 리소스만 관리한다 — 기존 EC2/VPC/Caddy/공용 DB(전부 콘솔로
# 만들어짐, deploy-test/rag가 이미 물려 있음)는 건드리지 않는다.
#
# IAM 신뢰 정책(github-actions-deploy 역할의 sub 목록에 이 저장소 repo_id 추가)은 여기서
# 관리하지 않는다 — AWS IAM에는 신뢰 정책에 "한 줄만 추가"하는 API가 없고, Terraform
# 리소스로 선언하려면 그 역할의 assume_role_policy 전체(다른 앱들이 쓰는 항목 포함)를
# import해서 통째로 소유해야 한다. 공유 역할의 소유권을 지금 옮기는 리스크가 이득보다
# 크다고 판단해 기존 방식(새앱배포절차.md 2번의 aws iam CLI 명령)을 그대로 쓴다.

resource "aws_ecr_repository" "app" {
  name                 = "virtual-financial-services"
  image_tag_mutability = "MUTABLE" # 새앱배포절차.md — Immutable이면 두 번째 push부터 latest 태그 재사용 실패

  image_scanning_configuration {
    scan_on_push = true
  }
}

resource "aws_ecr_lifecycle_policy" "app" {
  repository = aws_ecr_repository.app.name

  policy = jsonencode({
    rules = [{
      rulePriority = 1
      description  = "이미지 10개 초과분 만료"
      selection = {
        tagStatus   = "any"
        countType   = "imageCountMoreThan"
        countNumber = 10
      }
      action = { type = "expire" }
    }]
  })
}

output "repository_url" {
  value = aws_ecr_repository.app.repository_url
}
