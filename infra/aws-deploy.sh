#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────
# Deploy meeple to a single EC2 instance on AWS
#
# Prerequisites:
#   - aws cli installed and configured (aws configure)
#   - Domain managed by Route 53
#
# Usage:
#   DOMAIN=meeple.example.com HOSTED_ZONE_ID=Z0123456789 ./infra/aws-deploy.sh
# ─────────────────────────────────────────────────────────────
set -euo pipefail
cd "$(dirname "$0")/.."
PROJECT_DIR="$(pwd)"

# ── Configuration ───────────────────────────────────────────
DOMAIN="${DOMAIN:-play.meeple.cat}"
HOSTED_ZONE_ID="${HOSTED_ZONE_ID:-Z037706987H9NU6DCOBE}"
REGION="${AWS_REGION:-eu-central-1}"
INSTANCE_TYPE="${INSTANCE_TYPE:-t3.medium}"
KEY_NAME="${KEY_NAME:-meeple-deploy}"
PROJECT="meeple"

# ── Helpers ─────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; NC='\033[0m'
info()  { echo -e "${GREEN}>>>${NC} $1"; }
warn()  { echo -e "${YELLOW}>>>${NC} $1"; }
step()  { echo -e "${CYAN}--- $1${NC}"; }

command -v aws >/dev/null || { echo -e "${RED}aws cli not found${NC}"; exit 1; }

echo ""
echo "  ┌──────────────────────────────────────┐"
echo "  │  Deploying meeple to AWS EC2         │"
echo "  │  Domain:   $DOMAIN"
echo "  │  Region:   $REGION"
echo "  │  Instance: $INSTANCE_TYPE"
echo "  └──────────────────────────────────────┘"
echo ""

# ── 1. SSH Key Pair ─────────────────────────────────────────
KEY_FILE="$HOME/.ssh/${KEY_NAME}.pem"

step "1/7  SSH key pair"
if ! aws ec2 describe-key-pairs --key-names "$KEY_NAME" --region "$REGION" &>/dev/null; then
    aws ec2 create-key-pair \
        --key-name "$KEY_NAME" \
        --region "$REGION" \
        --query 'KeyMaterial' \
        --output text > "$KEY_FILE"
    chmod 600 "$KEY_FILE"
    info "Created key pair → $KEY_FILE"
else
    info "Key pair '$KEY_NAME' already exists"
    [[ -f "$KEY_FILE" ]] || warn "Key exists in AWS but $KEY_FILE not found locally"
fi

# ── 2. VPC & Security Group ─────────────────────────────────
VPC_ID="${VPC_ID:-vpc-00618201cc1d5f086}"
SG_NAME="${PROJECT}-sg"

step "2/7  VPC & security group"
info "VPC: $VPC_ID"

# Find a subnet in the VPC
SUBNET_ID=$(aws ec2 describe-subnets \
    --filters "Name=vpc-id,Values=$VPC_ID" \
    --region "$REGION" \
    --query 'Subnets[0].SubnetId' \
    --output text)
info "Subnet: $SUBNET_ID"

SG_ID=$(aws ec2 describe-security-groups \
    --filters "Name=group-name,Values=$SG_NAME" "Name=vpc-id,Values=$VPC_ID" \
    --region "$REGION" \
    --query 'SecurityGroups[0].GroupId' \
    --output text 2>/dev/null || echo "None")

if [[ "$SG_ID" == "None" || -z "$SG_ID" ]]; then
    SG_ID=$(aws ec2 create-security-group \
        --group-name "$SG_NAME" \
        --description "Meeple - SSH, HTTP, HTTPS" \
        --vpc-id "$VPC_ID" \
        --region "$REGION" \
        --query 'GroupId' \
        --output text)

    for PORT in 22 80 443; do
        aws ec2 authorize-security-group-ingress \
            --group-id "$SG_ID" \
            --protocol tcp \
            --port "$PORT" \
            --cidr 0.0.0.0/0 \
            --region "$REGION" >/dev/null
    done
    info "Created security group: $SG_ID"
else
    info "Using existing security group: $SG_ID"
fi

# ── 3. Find Ubuntu 24.04 AMI ───────────────────────────────
step "3/7  Ubuntu AMI"
AMI_ID=$(aws ec2 describe-images \
    --owners 099720109477 \
    --filters \
        "Name=name,Values=ubuntu/images/hvm-ssd-gp3/ubuntu-noble-24.04-amd64-server-*" \
        "Name=state,Values=available" \
    --region "$REGION" \
    --query 'sort_by(Images, &CreationDate)[-1].ImageId' \
    --output text)
info "AMI: $AMI_ID"

# ── 4. Launch Instance ─────────────────────────────────────
step "4/7  Launching EC2 instance"
INSTANCE_ID=$(aws ec2 run-instances \
    --image-id "$AMI_ID" \
    --instance-type "$INSTANCE_TYPE" \
    --key-name "$KEY_NAME" \
    --security-group-ids "$SG_ID" \
    --subnet-id "$SUBNET_ID" \
    --block-device-mappings '[{"DeviceName":"/dev/sda1","Ebs":{"VolumeSize":30,"VolumeType":"gp3"}}]' \
    --tag-specifications "ResourceType=instance,Tags=[{Key=Name,Value=$PROJECT}]" \
    --user-data file://infra/server-setup.sh \
    --region "$REGION" \
    --query 'Instances[0].InstanceId' \
    --output text)
info "Instance: $INSTANCE_ID"

info "Waiting for instance to be running..."
aws ec2 wait instance-running --instance-ids "$INSTANCE_ID" --region "$REGION"
info "Instance is running"

# ── 5. Elastic IP ──────────────────────────────────────────
step "5/7  Elastic IP"
ALLOC_ID=$(aws ec2 allocate-address \
    --domain vpc \
    --region "$REGION" \
    --tag-specifications "ResourceType=elastic-ip,Tags=[{Key=Name,Value=$PROJECT}]" \
    --query 'AllocationId' \
    --output text)

PUBLIC_IP=$(aws ec2 describe-addresses \
    --allocation-ids "$ALLOC_ID" \
    --region "$REGION" \
    --query 'Addresses[0].PublicIp' \
    --output text)

aws ec2 associate-address \
    --instance-id "$INSTANCE_ID" \
    --allocation-id "$ALLOC_ID" \
    --region "$REGION" >/dev/null

info "Elastic IP: $PUBLIC_IP"

# ── 6. Route 53 DNS ────────────────────────────────────────
step "6/7  Route 53 DNS"
aws route53 change-resource-record-sets \
    --hosted-zone-id "$HOSTED_ZONE_ID" \
    --change-batch '{
        "Changes": [{
            "Action": "UPSERT",
            "ResourceRecordSet": {
                "Name": "'"$DOMAIN"'",
                "Type": "A",
                "TTL": 300,
                "ResourceRecords": [{"Value": "'"$PUBLIC_IP"'"}]
            }
        }]
    }' >/dev/null
info "DNS: $DOMAIN → $PUBLIC_IP"

# ── 7. Upload code & start ─────────────────────────────────
step "7/7  Uploading code to server"

SSH_CMD="ssh -i $KEY_FILE -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null ubuntu@$PUBLIC_IP"

info "Waiting for SSH to become available..."
for i in $(seq 1 30); do
    if $SSH_CMD -o ConnectTimeout=5 "echo ok" &>/dev/null; then
        break
    fi
    sleep 5
done

info "Waiting for cloud-init to finish (Docker install)..."
$SSH_CMD "cloud-init status --wait" 2>/dev/null || true

info "Uploading project files..."
rsync -azP \
    --exclude node_modules \
    --exclude .next \
    --exclude .git \
    --exclude __pycache__ \
    --exclude '*.pyc' \
    --exclude .venv \
    --exclude pgdata \
    --exclude old-carcassone \
    --exclude carcassonne-react \
    -e "ssh -i $KEY_FILE -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null" \
    "$PROJECT_DIR/" "ubuntu@$PUBLIC_IP:/opt/meeple/"

info "Creating .env from template..."
$SSH_CMD "cd /opt/meeple && cp infra/.env.prod.example .env.prod"

info "Generating secure secrets in .env.prod..."
$SSH_CMD 'cd /opt/meeple && sed -i "s|CHANGE_ME_DB_PASSWORD|'"$(openssl rand -hex 16)"'|" .env.prod && sed -i "s|CHANGE_ME_JWT_SECRET|'"$(openssl rand -hex 32)"'|" .env.prod && sed -i "s|meeple.example.com|'"$DOMAIN"'|g" .env.prod'

info "Starting services..."
$SSH_CMD "cd /opt/meeple && sudo docker compose -f docker-compose.prod.yml --env-file .env.prod up -d --build"

info "Running database migrations..."
$SSH_CMD "cd /opt/meeple && sudo docker compose -f docker-compose.prod.yml --env-file .env.prod exec -T backend uv run alembic upgrade head" || warn "Migrations failed - you may need to run them manually"

# ── Summary ─────────────────────────────────────────────────
echo ""
echo "  ┌──────────────────────────────────────────────────────┐"
echo "  │  Deployment complete!                                │"
echo "  ├──────────────────────────────────────────────────────┤"
echo "  │  URL:  http://$DOMAIN"
echo "  │  IP:   $PUBLIC_IP"
echo "  │  SSH:  ssh -i $KEY_FILE ubuntu@$PUBLIC_IP"
echo "  ├──────────────────────────────────────────────────────┤"
echo "  │  To add HTTPS (optional):                            │"
echo "  │  ssh -i $KEY_FILE ubuntu@$PUBLIC_IP"
echo "  │  cd /opt/meeple && sudo ./infra/setup-tls.sh $DOMAIN│"
echo "  └──────────────────────────────────────────────────────┘"
echo ""
