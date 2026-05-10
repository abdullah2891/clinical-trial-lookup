"""
Modal serverless GPU deployment for BioMistral-7B + QLoRA adapter.

Deploy: modal deploy serving/modal_endpoint.py
Endpoint: https://<username>--biomistral-screener.modal.run/screen

Cold start: ~90s (model load + adapter merge)
Warm inference: ~2-4s per screening call
Scale-to-zero: 5 min idle window
"""

from __future__ import annotations

import json
import os
import re

import modal

app = modal.App("biomistral-screener")

image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install(
        "transformers>=4.41.0",
        "peft>=0.11.0",
        "bitsandbytes>=0.43.1",
        "accelerate>=0.30.0",
        "torch>=2.3.0",
        "sentencepiece>=0.2.0",
        "huggingface-hub>=0.23.0",
    )
)

PROMPT_TEMPLATE = """You are a clinical trial eligibility screener. Given a patient profile and trial eligibility criteria, determine if the patient is eligible.

Patient Profile:
{patient}

Trial Eligibility Criteria:
{criteria}

Respond with a JSON object with these exact keys:
- "eligible": boolean (true/false)
- "confidence": float between 0.0 and 1.0
- "reason": string (one sentence explanation)
- "key_criteria_met": list of strings
- "key_criteria_failed": list of strings

JSON response:"""


@app.cls(
    gpu="A10G",
    image=image,
    scaledown_window=300,
    secrets=[modal.Secret.from_name("huggingface-secret")],
)
class BioMistralScreener:
    @modal.enter()
    def load_model(self) -> None:
        import torch
        from peft import PeftModel
        from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig

        base_model_id = os.environ.get("BASE_MODEL", "BioMistral/BioMistral-7B")
        adapter_repo = os.environ.get(
            "LORA_ADAPTER_PATH", "yourusername/clinical-trial-eligibility-screener"
        )

        bnb_config = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_compute_dtype=torch.float16,
            bnb_4bit_use_double_quant=True,
        )

        self.tokenizer = AutoTokenizer.from_pretrained(base_model_id)
        self.tokenizer.pad_token = self.tokenizer.eos_token

        model = AutoModelForCausalLM.from_pretrained(
            base_model_id,
            quantization_config=bnb_config,
            device_map="auto",
            torch_dtype=torch.float16,
        )
        self.model = PeftModel.from_pretrained(model, adapter_repo)
        self.model.eval()

    @modal.method()
    def screen(self, patient: str, criteria: str) -> dict:
        """Screen a patient against trial criteria. Returns eligibility dict."""
        import torch

        prompt = PROMPT_TEMPLATE.format(patient=patient, criteria=criteria)
        inputs = self.tokenizer(prompt, return_tensors="pt").to(self.model.device)

        with torch.no_grad():
            output_ids = self.model.generate(
                **inputs,
                max_new_tokens=256,
                temperature=0.1,
                do_sample=True,
                pad_token_id=self.tokenizer.eos_token_id,
            )

        generated = self.tokenizer.decode(
            output_ids[0][inputs["input_ids"].shape[1]:],
            skip_special_tokens=True,
        )
        return _extract_json(generated)

    @modal.web_endpoint(method="POST")
    def screen_http(self, body: dict) -> dict:
        """HTTP entry point. Accepts {patient, criteria}, returns eligibility dict."""
        patient = body.get("patient", "")
        criteria = body.get("criteria", "")
        if not patient or not criteria:
            return {"error": "patient and criteria are required", "eligible": False, "confidence": 0.0}
        return self.screen.local(patient, criteria)


def _extract_json(text: str) -> dict:
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass
    return {
        "eligible": False,
        "confidence": 0.0,
        "reason": text[:200],
        "key_criteria_met": [],
        "key_criteria_failed": [],
    }


# Local test entry point
@app.local_entrypoint()
def test() -> None:
    screener = BioMistralScreener()
    result = screener.screen.remote(
        patient="58-year-old male with type 2 diabetes diagnosed 8 years ago. HbA1c 8.2%, on metformin 1000mg BID. No cardiovascular disease. BMI 29.",
        criteria="Inclusion: Age 40-75, T2DM ≥1 year, HbA1c 7.5-10%. Exclusion: Insulin therapy, eGFR <45.",
    )
    print(result)
