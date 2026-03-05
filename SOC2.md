# SOC 2 Alignment – Cross-Border Payments API

This document maps our infrastructure design to the five SOC 2 Trust Services Criteria (TSC).  
The primary focus for this platform is **Security (CC)** and **Availability (A)**, with  
**Confidentiality (C)** and **Processing Integrity (PI)** as supporting criteria.

---

## 1. Access Control (CC6 – Logical and Physical Access)

### Principle of Least Privilege

| Layer | Control |
|---|---|
| **AWS IAM** | Each ECS task uses a dedicated execution role with only `ssm:GetParameters` and `ecr:GetDownloadUrlForLayer`. No wildcard `*` permissions. |
| **ECS Tasks** | Containers run as non-root user (`UID 1000`). No `--privileged` flag. Read-only root filesystem where possible. |
| **Network** | ECS tasks in **private subnets** — not directly reachable from the internet. Only ALB can route traffic to them (SG rule: inbound 8000 from ALB SG only). |
| **ALB** | HTTPS only on port 443. Port 80 redirects to 443 (no plaintext HTTP accepted). |
| **GitHub Actions** | Secrets (`AWS_ACCESS_KEY_ID`, etc.) stored as **GitHub Encrypted Secrets**, never in code or logs. Deployment requires environment approval for production. |

### Authentication

- API-to-blockchain service: internal network only (not publicly exposed).
- Future external API consumers: should use **API Gateway + Cognito** or **mTLS client certificates**.
- All AWS console access: **MFA enforced** via AWS IAM Identity Center.

### RBAC in Terraform

```hcl
# Developers can only read state; only CI/CD role can apply
resource "aws_iam_policy" "tf_readonly" {
  name = "terraform-read-only"
  # ... readonly S3 and DynamoDB for state
}
```

---

## 2. Data Security (CC6.1, CC6.7 – Encryption)

### In Transit

| Path | Encryption |
|---|---|
| Client → ALB | TLS 1.2+ (AWS-managed certificate via ACM) |
| ALB → ECS tasks | HTTPS (internal, within VPC) |
| ECS → blockchain service | HTTP within private VPC network |
| ECS → AWS APIs (ECR, SSM, CloudWatch) | TLS enforced by AWS SDK |

### At Rest

| Data | Encryption |
|---|---|
| ECR images | AES-256 (configured in Terraform) |
| CloudWatch Logs | AWS-managed KMS key |
| SSM Parameter Store secrets | `SecureString` type — encrypted with KMS |
| ECS ephemeral storage | Encrypted at rest (Fargate default) |
| Terraform state (S3) | SSE-S3 + bucket versioning enabled |

### Secret Management

Secrets (vendor API keys, blockchain node URLs) are stored in **AWS SSM Parameter Store** as `SecureString` and injected as environment variables at task startup — never baked into Docker images or committed to git.

```bash
# Store a secret (example)
aws ssm put-parameter \
  --name "/payments-api/vendor-a-api-key" \
  --value "sk-..." \
  --type SecureString \
  --key-id alias/payments-api-key
```

---

## 3. Audit Logging (CC7 – System Monitoring)

### What We Log

Every `/transfer` request produces a structured JSON log entry including:

```json
{
  "timestamp": "2024-11-01T14:32:00Z",
  "level": "INFO",
  "message": "Transfer completed",
  "vendor": "vendorA",
  "txhash": "0x123abc...",
  "amount": 100,
  "client_ip": "203.0.113.42",
  "latency_ms": 38.4,
  "step": "vendor_forward"
}
```

### Log Destinations

| Layer | Destination | Retention |
|---|---|---|
| Application logs | CloudWatch Logs `/ecs/payments-api` | **90 days** |
| ALB access logs | S3 bucket (access logs enabled) | **1 year** |
| AWS API calls | CloudTrail (all regions, multi-account) | **1 year** |
| Blockchain validation failures | Same structured log + `txhash_confirmations_total{result="not found"}` metric alert |

### Key Audit Events

| Event | Log Level | Detail |
|---|---|---|
| `txhash validated` | INFO | txhash, block number, timestamp |
| `txhash not found` | WARNING | txhash, client IP, amount |
| `vendor forwarded` | INFO | vendor, reference_id |
| `unknown vendor attempted` | WARNING | vendor name, client IP |
| `blockchain service down` | ERROR | error message, fallback behavior |

### Immutability

CloudWatch Logs are **append-only** for the ECS task role. Deletion requires a separate IAM permission that is not granted to the task role. CloudTrail logs are delivered to a **separate AWS account** (log archive account) where even admins cannot delete them.

---

## 4. Incident Response Readiness (CC7.4, CC7.5)

### Detection

| Signal | Tool | Action |
|---|---|---|
| Error rate spike | Prometheus alert → PagerDuty | On-call engineer paged within 2 min |
| Blockchain service down | CloudWatch Alarm on `txhash_confirmations_total{result="error"}` | Auto-page + ECS task restart |
| Failed deployments | GitHub Actions smoke test failure | Deploy blocked; rollback triggered automatically by ECS circuit breaker |
| Unusual IAM activity | CloudTrail → GuardDuty | Auto-alert to security channel |

### Response Runbook (MTTR Targets)

| Severity | Target MTTR | Response |
|---|---|---|
| P1 – API down | < 15 min | Rollback via ECS circuit breaker or `terraform apply` previous SHA |
| P2 – High error rate | < 30 min | Check CloudWatch Logs, Grafana dashboard, rollback if needed |
| P3 – Latency degraded | < 2 hours | Investigate vendor timeouts, scale ECS tasks if needed |

### Rollback Procedure

```bash
# 1. Identify last known good SHA
git log --oneline -10

# 2. Redeploy previous image
TF_VAR_image_tag=<previous-sha> terraform apply -auto-approve

# 3. Verify
curl https://api.example.com/health
bash tests/post-deploy-smoke-test.sh
```

### Change Management

- All infrastructure changes go through **pull requests** with required review.
- Production deployments require **GitHub environment approval** (manual gate).
- All Terraform plans are reviewed in CI before `apply`.
- `enable_deletion_protection = true` on the ALB prevents accidental teardown.

---

## 5. Availability (A1)

| Control | Implementation |
|---|---|
| Multi-AZ deployment | ECS tasks distributed across 2 availability zones |
| Health checks | ALB checks `/health` every 30s; unhealthy tasks are replaced automatically |
| Auto-scaling | ECS Service Auto Scaling based on CPU/memory (configurable) |
| Circuit breaker | ECS deployment circuit breaker rolls back on failed deployments |
| Dependency isolation | Blockchain service failure returns HTTP 503 — does not crash the API |

---

## 6. Processing Integrity (PI1)

| Control | Implementation |
|---|---|
| Input validation | Pydantic models validate `amount > 0` and `txhash` format before processing |
| Txhash verification | Every transfer requires blockchain confirmation before vendor routing |
| Idempotency | `reference_id` in vendor response ties back to `txhash` — prevents double processing |
| Immutable images | ECR tags are immutable (git SHA); what was tested is what runs in production |

---

## SOC 2 Readiness Checklist

| Control Area | Notes |
|---|---|
| IAM least privilege | ECS task roles scoped to minimum permissions |
| MFA enforced | Required for all AWS console users |
| Encryption in transit | TLS 1.2+ on ALB; internal VPC traffic |
| Encryption at rest | ECR, SSM, CloudWatch all encrypted |
| Audit logging | Structured JSON logs, 90-day retention |
| CloudTrail enabled | Multi-region, delivered to archive account |
| Incident response plan | Runbook above; PagerDuty integration ready |
| Automated rollback | ECS circuit breaker + smoke tests block bad deploys |
| Vulnerability scanning | Trivy in CI + ECR scan-on-push |
| Secrets management | SSM Parameter Store, never in code |
| Change management | PRs + production environment approval |
| Multi-AZ availability | 2 AZs, ALB, ECS health checks |
