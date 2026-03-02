import os
import torch
import torch.nn as nn
import torch.nn.functional as F
import logging
from transformers import AutoTokenizer, AutoModel

from src.utils.config import Config

logger = logging.getLogger(__name__)

MODEL_PATH = os.path.join(Config.BASE_DIR, "models", "tool_call", "miniLM", "tsuzi_intent_model.pt")
BASE_MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"


class IntentClassifier(nn.Module):
    def __init__(self, base_model_name: str, num_labels: int):
        super().__init__()
        self.encoder = AutoModel.from_pretrained(base_model_name)
        hidden_size = self.encoder.config.hidden_size
        self.classifier = nn.Linear(hidden_size, num_labels)

    def forward(self, input_ids, attention_mask=None):
        outputs = self.encoder(input_ids=input_ids, attention_mask=attention_mask)
        return self.classifier(outputs.pooler_output)


_model = None
_tokenizer = None
_id_to_label = None


def _load_model():
    global _model, _tokenizer, _id_to_label

    checkpoint = torch.load(MODEL_PATH, map_location="cpu", weights_only=False)
    label_map = checkpoint["label_map"]
    _id_to_label = {v: k for k, v in label_map.items()}

    _tokenizer = AutoTokenizer.from_pretrained(BASE_MODEL_NAME)
    _model = IntentClassifier(BASE_MODEL_NAME, len(label_map))
    _model.load_state_dict(checkpoint["model_state_dict"])
    _model.eval()

    logger.info(f"MiniLM loaded. Labels: {list(label_map.keys())}")


def predict_intent(query: str) -> dict:
    if _model is None:
        _load_model()

    inputs = _tokenizer(query, return_tensors="pt", truncation=True, max_length=128, padding=True)

    with torch.no_grad():
        logits = _model(input_ids=inputs["input_ids"], attention_mask=inputs["attention_mask"])

    probs = F.softmax(logits, dim=-1)
    confidence, label_id = torch.max(probs, dim=-1)

    label_id = label_id.item()
    label = _id_to_label[label_id]

    return {
        "label": label,
        "label_id": label_id,
        "confidence": round(confidence.item(), 4),
    }
