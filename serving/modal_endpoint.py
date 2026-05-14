"""
Modal serverless GPU deployment for BioMistral-7B (base model, no adapter).

Deploy: modal deploy serving/modal_endpoint.py
Endpoint: https://<username>--biomistral-screener.modal.run/screen_http

Cold start: ~60s (4-bit model load)
Warm inference: ~2-4s per screening call
Scale-to-zero: 5 min idle window
"""

from __future__ import annotations

import json
import re

import modal

app = modal.App("biomistral-screener")

image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install(
        "transformers>=4.41.0",
        "bitsandbytes>=0.43.1",
        "accelerate>=0.30.0",
        "torch>=2.3.0",
        "sentencepiece>=0.2.0",
        "huggingface-hub>=0.23.0",
        "fastapi[standard]>=0.111.0",
    )
)

PROMPT_TEMPLATE = """<s>[INST] You are a clinical trial eligibility screener. Analyze the patient profile against the trial eligibility criteria and output ONLY a JSON object — no other text.

### Example
Patient: 45yo female, breast cancer stage II, ECOG 1, no prior chemo.
Criteria: Inclusion: age 18-70, breast cancer, ECOG 0-2. Exclusion: prior anthracycline.
Output: {{"eligible": true, "confidence": 0.88, "reason": "Patient meets age, diagnosis, and performance criteria with no exclusion factors.", "key_criteria_met": ["age 45", "breast cancer", "ECOG 1"], "key_criteria_failed": []}}

### Task
Patient: {patient}
Criteria: {criteria}
Output: [/INST]"""


BASE_MODEL = "BioMistral/BioMistral-7B"


@app.cls(
    gpu="A10G",
    image=image,
    scaledown_window=300,
)
class BioMistralScreener:
    @modal.enter()
    def load_model(self) -> None:
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig

        bnb_config = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_compute_dtype=torch.float16,
            bnb_4bit_use_double_quant=True,
        )

        self.tokenizer = AutoTokenizer.from_pretrained(BASE_MODEL)
        self.tokenizer.pad_token = self.tokenizer.eos_token

        self.model = AutoModelForCausalLM.from_pretrained(
            BASE_MODEL,
            quantization_config=bnb_config,
            device_map="auto",
            torch_dtype=torch.float16,
        )
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

    @modal.fastapi_endpoint(method="POST")
    def screen_http(self, body: dict) -> dict:
        """HTTP entry point. Accepts {patient, criteria}, returns eligibility dict."""
        patient = body.get("patient", "")
        criteria = body.get("criteria", "")
        if not patient or not criteria:
            return {"error": "patient and criteria are required", "eligible": False, "confidence": 0.0}
        return self.screen.local(patient, criteria)


def _extract_json(text: str) -> dict:
    # Strip markdown code fences
    text = re.sub(r"```(?:json)?", "", text).strip()
    # Find the outermost {...}
    match = re.search(r"\{[^{}]*\}", text, re.DOTALL)
    if match:
        try:
            data = json.loads(match.group())
            return {
                "eligible": bool(data.get("eligible", False)),
                "confidence": float(data.get("confidence", 0.0)),
                "reason": str(data.get("reason", "")),
                "key_criteria_met": list(data.get("key_criteria_met", [])),
                "key_criteria_failed": list(data.get("key_criteria_failed", [])),
            }
        except (json.JSONDecodeError, ValueError):
            pass
    # Heuristic fallback: look for eligible keyword in generated text
    lower = text.lower()
    eligible = "eligible" in lower and "not eligible" not in lower and "ineligible" not in lower
    return {
        "eligible": eligible,
        "confidence": 0.5 if eligible else 0.4,
        "reason": text[:300].strip() or "Unable to parse model output.",
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
