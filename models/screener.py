"""
EligibilityScreener — inference wrapper for the fine-tuned BioMistral model.

Calls either:
  - The Modal serverless endpoint (production)
  - A local HuggingFace model with LoRA adapter (development)

Depends on MODAL_ENDPOINT_URL env var for production mode.

Usage:
    screener = EligibilityScreener()
    result = screener.screen(patient_profile, eligibility_criteria)
"""

from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass, field

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

try:
    from langsmith import traceable
    from langsmith.wrappers import wrap_openai
except ImportError:  # keep the screener usable without langsmith installed
    def traceable(*d_args, **d_kwargs):
        def decorator(fn):
            return fn
        return decorator

    def wrap_openai(client):
        return client

logger = logging.getLogger(__name__)

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


@dataclass
class ScreeningResult:
    nct_id: str
    title: str
    eligible: bool
    confidence: float
    reason: str
    key_criteria_met: list[str] = field(default_factory=list)
    key_criteria_failed: list[str] = field(default_factory=list)
    latency_ms: float = 0.0


GPT_SCREENING_PROMPT = """You are a clinical trial eligibility screener.

Patient Profile:
{patient}

Trial Eligibility Criteria:
{criteria}

Respond with ONLY a JSON object:
{{"eligible": true/false, "confidence": 0.0-1.0, "reason": "one sentence", "key_criteria_met": [], "key_criteria_failed": []}}"""


class EligibilityScreener:
    """
    Routes screening to Modal (BioMistral-7B) with GPT-4o-mini fallback.
    Set MODAL_ENDPOINT_URL to use the serverless GPU endpoint.
    """

    def __init__(self) -> None:
        self._endpoint_url = os.getenv("MODAL_ENDPOINT_URL", "")
        self._openai_key = os.getenv("OPENAI_API_KEY", "")
        self._local_model: object | None = None
        self._client = httpx.Client(timeout=15.0)

    @traceable(name="screen_trial", run_type="chain")
    def screen(
        self,
        patient_profile: str,
        eligibility_criteria: str,
        nct_id: str = "",
        title: str = "",
    ) -> ScreeningResult:
        """Screen a patient against a trial's eligibility criteria."""
        start = time.monotonic()

        raw: dict = {}
        if self._endpoint_url:
            raw = self._call_modal(patient_profile, eligibility_criteria)

        # Fall back when Modal returned no usable result (no reason or low-confidence heuristic)
        modal_unusable = len(str(raw.get("reason", ""))) < 10 or float(raw.get("confidence", 0)) < 0.5
        if modal_unusable and self._openai_key:
            logger.debug("Modal result unusable — falling back to GPT-4o-mini")
            raw = self._call_gpt(patient_profile, eligibility_criteria)
        elif modal_unusable and not self._openai_key:
            raw = self._call_local(patient_profile, eligibility_criteria)

        latency_ms = (time.monotonic() - start) * 1000
        return self._parse_result(raw, nct_id, title, latency_ms)

    def screen_batch(
        self,
        patient_profile: str,
        trials: list[dict[str, str]],
        max_workers: int = 8,
    ) -> list[ScreeningResult]:
        """Screen a patient against multiple trials in parallel."""
        from concurrent.futures import ThreadPoolExecutor, as_completed

        def _screen_one(trial: dict) -> ScreeningResult:
            try:
                return self.screen(
                    patient_profile,
                    trial.get("criteria", ""),
                    nct_id=trial.get("nct_id", ""),
                    title=trial.get("title", ""),
                )
            except Exception as exc:
                logger.warning("Screening failed for %s: %s", trial.get("nct_id"), exc)
                return ScreeningResult(
                    nct_id=trial.get("nct_id", ""),
                    title=trial.get("title", ""),
                    eligible=False,
                    confidence=0.0,
                    reason="Screening failed due to an internal error.",
                )

        results: list[ScreeningResult] = [None] * len(trials)  # type: ignore[list-item]
        with ThreadPoolExecutor(max_workers=min(max_workers, len(trials))) as pool:
            futures = {pool.submit(_screen_one, t): i for i, t in enumerate(trials)}
            for fut in as_completed(futures):
                results[futures[fut]] = fut.result()
        return results

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=8))
    def _call_modal(self, patient: str, criteria: str) -> dict:
        resp = self._client.post(
            self._endpoint_url,
            json={"patient": patient, "criteria": criteria},
        )
        resp.raise_for_status()
        return resp.json()

    def _call_gpt(self, patient: str, criteria: str) -> dict:
        """GPT-4o-mini fallback screener with JSON response format."""
        from openai import OpenAI
        client = wrap_openai(OpenAI(api_key=self._openai_key))
        prompt = GPT_SCREENING_PROMPT.format(patient=patient, criteria=criteria)
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            max_tokens=300,
            temperature=0.1,
        )
        return json.loads(resp.choices[0].message.content or "{}")

    def _call_local(self, patient: str, criteria: str) -> dict:
        """Load and run the local LoRA-augmented model (lazy init)."""
        if self._local_model is None:
            self._local_model = self._load_local_model()

        prompt = PROMPT_TEMPLATE.format(patient=patient, criteria=criteria)
        output = self._run_local_inference(prompt)
        return self._extract_json(output)

    def _load_local_model(self) -> object:
        import torch
        from peft import PeftModel
        from transformers import AutoModelForCausalLM, AutoTokenizer

        base_model_id = os.getenv("BASE_MODEL", "BioMistral/BioMistral-7B")
        adapter_path = os.getenv("LORA_ADAPTER_PATH", "./outputs/qlora-biomistral/adapter")
        logger.info("Loading local model from %s + adapter %s", base_model_id, adapter_path)

        tokenizer = AutoTokenizer.from_pretrained(base_model_id)
        model = AutoModelForCausalLM.from_pretrained(
            base_model_id,
            load_in_4bit=True,
            device_map="auto",
            torch_dtype=torch.float16,
        )
        model = PeftModel.from_pretrained(model, adapter_path)
        model.eval()
        return {"model": model, "tokenizer": tokenizer}

    def _run_local_inference(self, prompt: str) -> str:
        import torch

        bundle = self._local_model  # type: ignore[union-attr]
        tokenizer = bundle["tokenizer"]
        model = bundle["model"]

        inputs = tokenizer(prompt, return_tensors="pt").to(model.device)
        with torch.no_grad():
            output_ids = model.generate(
                **inputs,
                max_new_tokens=256,
                temperature=0.1,
                do_sample=True,
                pad_token_id=tokenizer.eos_token_id,
            )
        return tokenizer.decode(output_ids[0][inputs["input_ids"].shape[1]:], skip_special_tokens=True)

    def _extract_json(self, text: str) -> dict:
        try:
            start = text.index("{")
            end = text.rindex("}") + 1
            return json.loads(text[start:end])
        except (ValueError, json.JSONDecodeError) as exc:
            logger.warning("JSON extraction failed: %s — raw: %.200s", exc, text)
            return {"eligible": False, "confidence": 0.0, "reason": text[:200],
                    "key_criteria_met": [], "key_criteria_failed": []}

    def _parse_result(
        self, raw: dict, nct_id: str, title: str, latency_ms: float
    ) -> ScreeningResult:
        return ScreeningResult(
            nct_id=nct_id,
            title=title,
            eligible=bool(raw.get("eligible", False)),
            confidence=float(raw.get("confidence", 0.0)),
            reason=str(raw.get("reason", "")),
            key_criteria_met=[str(c) for c in raw.get("key_criteria_met", [])],
            key_criteria_failed=[str(c) for c in raw.get("key_criteria_failed", [])],
            latency_ms=latency_ms,
        )
