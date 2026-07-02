#!/bin/bash
# EC2 bootstrap — runs once at first launch as root
# Installs Docker, clones the repo, writes secrets, starts all services.
set -euo pipefail
exec > >(tee /var/log/user_data.log | logger -t user_data) 2>&1

APP_NAME="${app_name}"
AWS_REGION="${aws_region}"
GITHUB_REPO="${github_repo}"
GITHUB_BRANCH="${github_branch}"
APP_DIR="/app"

echo "=== [1/6] System update ==="
apt-get update -y
apt-get install -y curl git jq unzip

echo "=== [2/6] Install Docker CE ==="
curl -fsSL https://get.docker.com | sh
systemctl enable docker
systemctl start docker
usermod -aG docker ubuntu

echo "=== [3/6] Install AWS CLI v2 ==="
curl -fsSL "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o /tmp/awscliv2.zip
unzip -q /tmp/awscliv2.zip -d /tmp
/tmp/aws/install
rm -rf /tmp/awscliv2.zip /tmp/aws

echo "=== [4/6] Clone application ==="
git clone --branch "$GITHUB_BRANCH" "$GITHUB_REPO" "$APP_DIR"
chown -R ubuntu:ubuntu "$APP_DIR"

echo "=== [5/6] Write .env from SSM ==="
OPENAI_KEY=$(aws ssm get-parameter \
  --name "/$APP_NAME/OPENAI_API_KEY" \
  --with-decryption \
  --region "$AWS_REGION" \
  --query Parameter.Value \
  --output text)

DB_PASS=$(aws ssm get-parameter \
  --name "/$APP_NAME/DB_PASSWORD" \
  --with-decryption \
  --region "$AWS_REGION" \
  --query Parameter.Value \
  --output text)

cat > "$APP_DIR/.env" <<EOF
OPENAI_API_KEY=$OPENAI_KEY
POSTGRES_USER=ctuser
POSTGRES_PASSWORD=$DB_PASS
POSTGRES_DB=clinical_trials
MODAL_ENDPOINT_URL=
EOF
chown ubuntu:ubuntu "$APP_DIR/.env"
chmod 600 "$APP_DIR/.env"

echo "=== [6/6] Start services ==="
cd "$APP_DIR"
docker compose -f docker-compose.prod.yml up -d --build

echo "=== Bootstrap complete ==="
echo "App will be available on port 80 once Docker images finish building (~3 min)."
echo "Check progress: docker compose logs -f"
