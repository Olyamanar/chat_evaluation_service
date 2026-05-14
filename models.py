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
        "name": "Лишние вопросы и сообщения",
        "descriptions": {
            1: "2+ лишних уточнения",
            3: "1 лишнее уточнение",
            5: "Заданы вопросы или отправлен шаблон, которые нацелены на решение вопроса"
        }
    },
    {
        "name": "Решение вопроса",
        "descriptions": {
            1: "Вопрос не понят, дан ответ неверно",
            3: "Вопрос пользователя решён не полностью, не предусмотрен сценарий ошибки и не рассказано как её избежать",
            5: "Верно понята проблема/вопрос. Дана исчерпывающая информация, нет «недосказанности». Предвидены вопросы, предложено сразу решение"
        }
    },
    {
        "name": "Тон и вежливость",
        "descriptions": {
            1: "Грубость",
            3: "Были попытки урегулирования ситуации, но не извинились, если пользователь столкнулся с проблемой по вине системы",
            5: "Использование этикетных формул, отсутствие грубости, сарказма. Ключевые слова: «пожалуйста», «благодарю», «понимаю»; отсутствие капса, восклицаний агрессии. Проявление понимания к ситуации клиента. Фразы: «понимаю ваше беспокойство», «сожалею», «это действительно неприятно»"
        }
    }
]
