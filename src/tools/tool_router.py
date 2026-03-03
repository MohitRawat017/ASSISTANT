import os
import json
import logging
import torch
from transformers import AutoTokenizer, AutoModelForCausalLM
from peft import PeftModel

from src.utils.config import Config

logger = logging.getLogger(__name__)

ADAPTER_PATH = os.path.join(Config.BASE_DIR, "models", "tool_call", "function_gemma", "fg_finetuned_ckpt")
BASE_MODEL_NAME = "google/functiongemma-270m-it"

_model = None
_tokenizer = None


def _load_model():
    global _model, _tokenizer

    device = "cuda" if torch.cuda.is_available() else "cpu"

    _tokenizer = AutoTokenizer.from_pretrained(ADAPTER_PATH)
    if _tokenizer.pad_token is None:
        _tokenizer.pad_token = _tokenizer.eos_token

    # Match training dtype: bf16 if supported, else fp32
    bf16_ok = device == "cuda" and torch.cuda.is_bf16_supported()
    load_dtype = torch.bfloat16 if bf16_ok else torch.float32

    base = AutoModelForCausalLM.from_pretrained(BASE_MODEL_NAME, torch_dtype=load_dtype)
    _model = PeftModel.from_pretrained(base, ADAPTER_PATH).to(device)
    _model.eval()

    logger.info(f"FunctionGemma loaded on {device} (dtype={load_dtype}).")


def _build_prompt(query: str, tool_schemas: list) -> str:
    tool_lines = []
    for schema in tool_schemas:
        name = schema["name"]
        args = schema.get("args", "")
        tool_lines.append(f"{name}({args})" if args else f"{name}()")

    developer_content = (
        "You are a function-calling model. "
        "Select exactly one tool from the available tools and return only valid JSON.\n\n"
        f"Available tools:\n{chr(10).join(tool_lines)}"
    )

    messages = [
        {"role": "developer", "content": developer_content},
        {"role": "user",      "content": query},
    ]
    return _tokenizer.apply_chat_template(
        messages, tokenize=False, add_generation_prompt=True
    )


def _parse_output(raw: str) -> dict:
    text = raw.strip()
    start, end = text.find("{"), text.rfind("}")

    if start == -1 or end == -1 or end <= start:
        return None

    try:
        parsed = json.loads(text[start:end + 1])
    except json.JSONDecodeError:
        return None

    if "tool" not in parsed:
        return None

    parsed.setdefault("args", {})
    return parsed


def predict_tool(query: str, tool_schemas: list) -> dict:
    if _model is None:
        _load_model()

    device = next(_model.parameters()).device
    prompt = _build_prompt(query, tool_schemas)
    inputs = _tokenizer(prompt, return_tensors="pt", add_special_tokens=False).to(device)

    with torch.no_grad():
        output_ids = _model.generate(
            **inputs,
            max_new_tokens=100,
            do_sample=False,
            pad_token_id=_tokenizer.pad_token_id,
        )

    generated = _tokenizer.decode(
        output_ids[0][inputs["input_ids"].shape[1]:],
        skip_special_tokens=True,
    )

    result = _parse_output(generated)
    logger.debug(f"FunctionGemma raw: {generated!r}")

    if result is None:
        logger.warning(f"FunctionGemma: no valid JSON. Raw: {generated!r}")
        return None

    valid_names = {s["name"] for s in tool_schemas}
    if result["tool"] not in valid_names:
        logger.warning(f"FunctionGemma: unknown tool '{result['tool']}'. Valid: {valid_names}")
        return None

    return result
