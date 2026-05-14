import json
import os
from datetime import datetime
from typing import List, Optional
from models import GoodExample, Message, MessageRole, Chat

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
EXAMPLES_FILE = os.path.join(DATA_DIR, "good_examples.json")


def _ensure_data_dir():
    os.makedirs(DATA_DIR, exist_ok=True)


def _load_examples() -> List[dict]:
    _ensure_data_dir()
    if not os.path.exists(EXAMPLES_FILE):
        return []
    try:
        with open(EXAMPLES_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return []


def _save_examples(examples: List[dict]):
    _ensure_data_dir()
    with open(EXAMPLES_FILE, "w", encoding="utf-8") as f:
        json.dump(examples, f, ensure_ascii=False, indent=2)


def add_good_example(chat: Chat) -> GoodExample:
    examples = _load_examples()
    example_id = f"ex_{datetime.now().strftime('%Y%m%d%H%M%S')}_{len(examples)}"
    example = GoodExample(
        id=example_id,
        chat_id=chat.id,
        employee_name=chat.employee_name or "Неизвестный",
        messages=chat.messages,
        added_at=datetime.now().isoformat()
    )
    examples.append(example.model_dump())
    _save_examples(examples)
    return example


def get_good_examples() -> List[GoodExample]:
    raw = _load_examples()
    return [GoodExample(**e) for e in raw]


def delete_good_example(example_id: str) -> bool:
    examples = _load_examples()
    new_examples = [e for e in examples if e.get("id") != example_id]
    if len(new_examples) == len(examples):
        return False
    _save_examples(new_examples)
    return True


def format_examples_for_prompt(examples: Optional[List[GoodExample]] = None) -> str:
    if examples is None:
        examples = get_good_examples()

    if not examples:
        return ""

    parts = ["Вот примеры ХОРОШИХ диалогов, которые были отмечены как эталонные:\n"]
    for i, ex in enumerate(examples[:5], 1):
        parts.append(f"\n--- Пример {i} (Сотрудник: {ex.employee_name}) ---")
        for msg in ex.messages:
            if msg.role == MessageRole.BOT:
                continue
            role_label = "Сотрудник" if msg.role.value == "employee" else "Клиент"
            parts.append(f"{role_label}: {msg.text}")
        parts.append("")

    return "\n".join(parts)
