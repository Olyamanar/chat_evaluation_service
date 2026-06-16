from pydantic import BaseModel
from typing import List, Optional
from enum import Enum


class MessageRole(str, Enum):
    EMPLOYEE = "employee"
    CLIENT = "client"
    BOT = "bot"
    UNKNOWN = "unknown"


class Message(BaseModel):
    timestamp: Optional[str] = None
    sender: str
    role: MessageRole
    text: str


class Chat(BaseModel):
    id: str
    employee_name: Optional[str] = None
    date: Optional[str] = None
    messages: List[Message]
    bot_heavy: bool = False


class CriterionResult(BaseModel):
    name: str
    score: int
    justification: str


class ChatEvaluation(BaseModel):
    chat_id: str
    employee_name: str
    date: Optional[str] = None
    criteria_scores: List[CriterionResult]
    total_score: int
    strengths: List[str]
    weaknesses: List[str]
    recommendations: List[str]
    summary: str


class EvaluationRequest(BaseModel):
    employee_name: str
    max_chats: int = 1000
    file_id: str
    use_ai: bool = False


class GoodExample(BaseModel):
    id: str
    chat_id: str
    employee_name: str
    messages: List[Message]
    added_at: str


class EmployeeChats(BaseModel):
    employee_name: str
    total_chats: int
    chats: List[Chat]


CRITERIA = [
    {
        "name": "Софт-скиллы",
        "descriptions": {
            1: "Игнорирование переживаний и эмоций исполнителя при работе с нашим сервисом",
            3: "Недостаточно проявлена эмпатия, формальный подход к общению",
            5: "Хорошая коммуникация, эмпатия, понимание ситуации исполнителя"
        }
    }
]
