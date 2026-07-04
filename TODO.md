# TODO — path to production-worthy

Known gaps, in rough priority order. Current state is a working demo:
spot EC2 (weekdays 8am–8pm ET), GPT-4o-mini screening, LangSmith evals.

## ML core (the headline portfolio gap)

- [ ] **Run the fine-tuning loop end to end** — it has never been executed:
  1. `python models/finetune_pipeline.py --stage data` (~240 examples, ~$5)
  2. QLoRA train on Colab T4: `python models/oss_finetune.py --train --epochs 3`
  3. Eval adapter vs base, push adapter to HuggingFace Hub
  4. Deploy `serving/modal_endpoint.py`, set `MODAL_ENDPOINT_URL` in prod
- [ ] Fix `/health` — it reports `BioMistral-7B-QLoRA` but the active screener
      is GPT-4o-mini fallback; report the real backend
- [ ] Expand `eval/golden_set.jsonl` beyond 10 examples; add borderline and
      multi-condition cases
- [ ] Schedule weekly evals (cron → `POST /experiments/run`) and weekly trial
      re-ingestion (`etl/pipeline.py` via EventBridge/Batch — currently manual)

## Security

- [ ] Rate-limit `/search` and `/experiments/run` (nginx `limit_req`) — every
      search costs ~21 OpenAI calls, run costs a 10-example eval; both are
      unauthenticated. Set an OpenAI monthly spend cap as backstop.
- [ ] Put auth (or at least a shared token) on `POST /experiments/run`
- [ ] Tighten `allowed_ssh_cidr` in `infra/terraform.tfvars` to own IP
- [ ] Rotate `db_password` off the dev default (`ctpass`)
- [ ] Restrict EC2 port 80 ingress to CloudFront's origin-facing managed
      prefix list (currently anyone can bypass CloudFront)
- [ ] Set `CORS_ORIGINS` to the CloudFront domain instead of `*`
- [ ] Verify pgvector retrieval SQL is fully parameterized (`status_filter`
      path) — audit was interrupted

## Infra / operations

- [ ] Move Terraform state to S3 backend with locking (currently local file,
      contains secrets incl. the SSH private key)
- [ ] CloudFront invalidation (`/index.html`) in the deploy workflow — static
      assets cache 24h, so UI deploys can take a day to appear
- [ ] Automate DB seeding: nightly `pg_dump` to S3 + restore step in
      `user_data.sh` (currently a manual scp/restore after instance replace)
- [ ] Put `LANGCHAIN_API_KEY` in SSM + `user_data.sh` — it was appended to
      `/app/.env` by hand and will be lost on instance recreation
- [ ] CloudWatch alarms: health-check failure, disk >80%, spot interruption
- [ ] Update `EC2_HOST` GitHub secret automatically if the EIP ever changes
      (e.g. Terraform output → repo secret step)
