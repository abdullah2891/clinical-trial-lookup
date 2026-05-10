"""
QLoRA fine-tuning of BioMistral-7B on clinical trial eligibility data.

Training runs on a T4 (Google Colab free tier) or A10G (RunPod $0.25/hr).
Outputs a LoRA adapter (~40MB) saved to outputs/qlora-biomistral/adapter.

Usage:
    python models/oss_finetune.py --train
    python models/oss_finetune.py --eval --adapter ./outputs/qlora-biomistral/adapter
    python models/oss_finetune.py --push --hub-repo yourusername/clinical-trial-eligibility-screener
"""

from __future__ import annotations

import argparse
import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

OUTPUT_DIR = Path("outputs/qlora-biomistral/adapter")
DATA_DIR = Path("finetune_data")

PROMPT_TEMPLATE = (
    "### Patient:\n{patient}\n\n"
    "### Eligibility Criteria:\n{criteria}\n\n"
    "### Assessment:\n{response}"
)


@dataclass
class QLoRAConfig:
    base_model: str = "BioMistral/BioMistral-7B"
    lora_r: int = 16
    lora_alpha: int = 32
    lora_dropout: float = 0.05
    target_modules: tuple[str, ...] = ("q_proj", "v_proj", "k_proj", "o_proj")
    epochs: int = 3
    per_device_batch_size: int = 2
    gradient_accumulation_steps: int = 4
    learning_rate: float = 2e-4
    max_seq_length: int = 1024
    output_dir: str = str(OUTPUT_DIR)
    bits: int = 4


def _load_dataset(split: str = "train"):
    from datasets import Dataset

    path = DATA_DIR / f"{split}.jsonl"
    records = []
    with path.open() as f:
        for line in f:
            r = json.loads(line)
            label = r.get("label", {})
            response = json.dumps(label) if isinstance(label, dict) else str(label)
            text = PROMPT_TEMPLATE.format(
                patient=r["patient"],
                criteria=r["criteria"],
                response=response,
            )
            records.append({"text": text})
    return Dataset.from_list(records)


def train(cfg: QLoRAConfig | None = None) -> None:
    """QLoRA fine-tune BioMistral-7B."""
    import torch
    from peft import LoraConfig, TaskType, get_peft_model, prepare_model_for_kbit_training
    from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
    from trl import SFTConfig, SFTTrainer

    if cfg is None:
        cfg = QLoRAConfig()

    bnb_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype=torch.float16,
        bnb_4bit_use_double_quant=True,
    )

    logger.info("Loading base model: %s", cfg.base_model)
    tokenizer = AutoTokenizer.from_pretrained(cfg.base_model, use_fast=True)
    tokenizer.pad_token = tokenizer.eos_token

    model = AutoModelForCausalLM.from_pretrained(
        cfg.base_model,
        quantization_config=bnb_config,
        device_map="auto",
        trust_remote_code=True,
    )
    model = prepare_model_for_kbit_training(model)

    lora_config = LoraConfig(
        r=cfg.lora_r,
        lora_alpha=cfg.lora_alpha,
        lora_dropout=cfg.lora_dropout,
        target_modules=list(cfg.target_modules),
        task_type=TaskType.CAUSAL_LM,
        bias="none",
    )
    model = get_peft_model(model, lora_config)
    model.print_trainable_parameters()

    train_dataset = _load_dataset("train")
    eval_dataset = _load_dataset("val")

    sft_config = SFTConfig(
        output_dir=cfg.output_dir,
        num_train_epochs=cfg.epochs,
        per_device_train_batch_size=cfg.per_device_batch_size,
        gradient_accumulation_steps=cfg.gradient_accumulation_steps,
        learning_rate=cfg.learning_rate,
        max_seq_length=cfg.max_seq_length,
        logging_steps=10,
        eval_strategy="epoch",
        save_strategy="epoch",
        load_best_model_at_end=True,
        fp16=True,
        report_to="none",
    )

    trainer = SFTTrainer(
        model=model,
        train_dataset=train_dataset,
        eval_dataset=eval_dataset,
        args=sft_config,
    )
    trainer.train()
    trainer.save_model(cfg.output_dir)
    tokenizer.save_pretrained(cfg.output_dir)
    logger.info("Adapter saved to %s", cfg.output_dir)


def evaluate(adapter_path: str) -> dict[str, float]:
    """Compare adapter vs. base model on the val set. Returns accuracy dict."""
    import torch
    from peft import PeftModel
    from transformers import AutoModelForCausalLM, AutoTokenizer

    base_model_id = os.getenv("BASE_MODEL", "BioMistral/BioMistral-7B")
    tokenizer = AutoTokenizer.from_pretrained(adapter_path)
    model = AutoModelForCausalLM.from_pretrained(
        base_model_id, load_in_4bit=True, device_map="auto", torch_dtype=torch.float16
    )
    model = PeftModel.from_pretrained(model, adapter_path)
    model.eval()

    val_records = []
    with (DATA_DIR / "val.jsonl").open() as f:
        for line in f:
            val_records.append(json.loads(line))

    correct = 0
    for r in val_records:
        prompt = PROMPT_TEMPLATE.format(patient=r["patient"], criteria=r["criteria"], response="")
        inputs = tokenizer(prompt, return_tensors="pt").to(model.device)
        with torch.no_grad():
            out = model.generate(**inputs, max_new_tokens=128, temperature=0.1, do_sample=True)
        decoded = tokenizer.decode(out[0][inputs["input_ids"].shape[1]:], skip_special_tokens=True)
        try:
            pred = json.loads(decoded[decoded.index("{"):decoded.rindex("}") + 1])
            gt = r.get("label", {})
            if pred.get("eligible") == gt.get("eligible"):
                correct += 1
        except Exception:
            pass

    accuracy = correct / len(val_records) if val_records else 0.0
    logger.info("Eligibility accuracy on val: %.2f%%", accuracy * 100)
    return {"accuracy": accuracy, "n_val": len(val_records)}


def push_to_hub(adapter_path: str, hub_repo: str) -> None:
    """Push the LoRA adapter to HuggingFace Hub."""
    from huggingface_hub import HfApi

    api = HfApi(token=os.getenv("HF_TOKEN"))
    api.upload_folder(
        folder_path=adapter_path,
        repo_id=hub_repo,
        repo_type="model",
        commit_message="Upload QLoRA BioMistral clinical trial eligibility adapter",
    )
    logger.info("Adapter pushed to https://huggingface.co/%s", hub_repo)


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser()
    parser.add_argument("--train", action="store_true")
    parser.add_argument("--eval", action="store_true")
    parser.add_argument("--push", action="store_true")
    parser.add_argument("--model", default="BioMistral/BioMistral-7B")
    parser.add_argument("--epochs", type=int, default=3)
    parser.add_argument("--adapter", default=str(OUTPUT_DIR))
    parser.add_argument("--hub-repo", default="")
    args = parser.parse_args()

    if args.train:
        cfg = QLoRAConfig(base_model=args.model, epochs=args.epochs)
        train(cfg)

    if args.eval:
        evaluate(args.adapter)

    if args.push:
        if not args.hub_repo:
            raise ValueError("--hub-repo required for --push")
        push_to_hub(args.adapter, args.hub_repo)


if __name__ == "__main__":
    main()
