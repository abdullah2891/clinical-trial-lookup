"""
GPT-4o teacher data generation + OpenAI fine-tune pipeline.

Generates synthetic (patient_profile, criteria, label) training examples
using GPT-4o as a teacher, saves to finetune_data/train.jsonl, then
optionally launches an OpenAI supervised fine-tune job.

Usage:
    python models/finetune_pipeline.py --stage data   # generate ~240 examples
    python models/finetune_pipeline.py --stage finetune
    python models/finetune_pipeline.py --stage all
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import random
import time
from pathlib import Path

from openai import OpenAI

logger = logging.getLogger(__name__)

DATA_DIR = Path("finetune_data")
TRAIN_FILE = DATA_DIR / "train.jsonl"
VAL_FILE = DATA_DIR / "val.jsonl"

CONDITION_SEEDS = [
    "type 2 diabetes with peripheral neuropathy",
    "stage III non-small cell lung cancer",
    "relapsing-remitting multiple sclerosis",
    "moderate-to-severe Crohn's disease",
    "treatment-resistant major depressive disorder",
    "early-stage Alzheimer's disease",
    "HER2-positive breast cancer",
    "chronic kidney disease stage 4",
    "rheumatoid arthritis on methotrexate",
    "moderate plaque psoriasis",
]

PATIENT_GEN_PROMPT = """Generate a realistic synthetic patient profile for a {condition} clinical trial.
Include: age, sex, diagnosis, disease duration, current medications, recent labs (relevant), comorbidities, and exclusion factors (randomly present or absent).
Be concise (150-200 words). Do not use real names."""

LABEL_PROMPT = """You are an expert clinical trial coordinator. Given:

Patient Profile:
{patient}

Trial Eligibility Criteria:
{criteria}

Determine eligibility. Respond with a JSON object:
{{
  "eligible": true/false,
  "confidence": 0.0-1.0,
  "reason": "one sentence",
  "key_criteria_met": ["...", "..."],
  "key_criteria_failed": ["...", "..."]
}}"""

SAMPLE_CRITERIA = """Inclusion:
- Age 18-75 years
- Confirmed diagnosis for ≥6 months
- ECOG performance status 0-2
- Adequate organ function

Exclusion:
- Active autoimmune disease requiring systemic treatment
- Prior treatment with investigational agent within 30 days
- Pregnancy or breastfeeding
- Uncontrolled infection"""


class DataGenerator:
    def __init__(self) -> None:
        self._client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])

    def generate(self, n_examples: int = 240) -> None:
        DATA_DIR.mkdir(exist_ok=True)
        examples: list[dict] = []

        for i in range(n_examples):
            condition = random.choice(CONDITION_SEEDS)
            try:
                patient = self._gen_patient(condition)
                label = self._gen_label(patient, SAMPLE_CRITERIA)
                examples.append({
                    "patient": patient,
                    "criteria": SAMPLE_CRITERIA,
                    "label": label,
                    "condition": condition,
                })
                if (i + 1) % 20 == 0:
                    logger.info("Generated %d / %d examples", i + 1, n_examples)
                time.sleep(0.3)  # rate-limit
            except Exception as exc:
                logger.warning("Example %d failed: %s", i, exc)

        split = int(len(examples) * 0.9)
        _write_jsonl(TRAIN_FILE, examples[:split])
        _write_jsonl(VAL_FILE, examples[split:])
        logger.info("Saved %d train / %d val examples", split, len(examples) - split)

    def _gen_patient(self, condition: str) -> str:
        resp = self._client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": PATIENT_GEN_PROMPT.format(condition=condition)}],
            max_tokens=300,
            temperature=0.9,
        )
        return resp.choices[0].message.content or ""

    def _gen_label(self, patient: str, criteria: str) -> dict:
        resp = self._client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": LABEL_PROMPT.format(patient=patient, criteria=criteria)}],
            max_tokens=300,
            temperature=0.2,
            response_format={"type": "json_object"},
        )
        return json.loads(resp.choices[0].message.content or "{}")


def _write_jsonl(path: Path, records: list[dict]) -> None:
    with path.open("w") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser()
    parser.add_argument("--stage", choices=["data", "finetune", "all"], default="data")
    parser.add_argument("--n-examples", type=int, default=240)
    args = parser.parse_args()

    if args.stage in ("data", "all"):
        DataGenerator().generate(args.n_examples)

    if args.stage in ("finetune", "all"):
        logger.info("OpenAI fine-tune: upload %s then create job", TRAIN_FILE)
        client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
        with TRAIN_FILE.open("rb") as f:
            file_obj = client.files.create(file=f, purpose="fine-tune")
        job = client.fine_tuning.jobs.create(
            training_file=file_obj.id,
            model="gpt-4o-mini-2024-07-18",
        )
        logger.info("Fine-tune job created: %s", job.id)


if __name__ == "__main__":
    main()
