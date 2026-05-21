import json
import os
import logging

logger = logging.getLogger(__name__)

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")

EVALUATION_PROMPT = """Ты — эксперт по оценке качества работы операторов технической поддержки. 

Оцени диалог поддержки по 3 критериям. Каждый критерий оценивается строго: 1, 3 или 5.

Критерии:
1. "Лишние вопросы и сообщения" — есть ли избыточные уточнения вместо конкретного решения.
   1 = 2+ лишних уточнения
   3 = 1 лишнее уточнение  
   5 = Нет лишних вопросов, сообщения нацелены на решение

2. "Решение вопроса" — насколько полно и правильно решена проблема клиента.
   1 = Вопрос не понят или дан неверный ответ
   3 = Решено не полностью, есть недосказанность
   5 = Проблема понята верно, дана исчерпывающая информация, предвидены вопросы

3. "Тон и вежливость" — вежливость, эмпатия, отсутствие грубости.
   1 = Грубость, обесценивание проблемы клиента
   3 = Корректный тон, но не хватает эмпатии/извинений если клиент столкнулся с проблемой по вине системы Qugo
   5 = Этикетные формулы, эмпатия, понимание ситуации клиента

Контекст: Qugo — платформа для работы самозанятых с заказчиками (Магнит, Самокат и др.).
Оператор отвечает на вопросы исполнителей о выплатах, налогах, регистрации, документах.
Извинения требуются ТОЛЬКО если проблема возникла по вине системы Qugo.
НЕ требуются извинения если: проблема у стороннего сервиса (Мой Налог, банк, Телеграм), 
ошибка в данных самого клиента (неправильная карта), отсутствие задания/выплаты (это нормальный процесс — нужно обратиться к заказчику).

Формат ответа — ТОЛЬКО JSON, без пояснений:
{
  "criteria": [
    {"name": "Лишние вопросы и сообщения", "score": 5, "justification": "краткое объяснение"},
    {"name": "Решение вопроса", "score": 5, "justification": "краткое объяснение"},
    {"name": "Тон и вежливость", "score": 5, "justification": "краткое объяснение"}
  ],
  "strengths": ["сильная сторона 1", "сильная сторона 2"],
  "weaknesses": ["слабая сторона 1"],
  "recommendations": ["рекомендация 1"]
}

Диалог:
Оператор: {employee_name}
{chat_text}"""


def _format_chat(chat, employee_name: str) -> str:
    lines = []
    for m in chat.messages:
        role_label = "Оператор" if m.role.value == "employee" else "Клиент"
        lines.append(f"{role_label} ({m.sender}): {m.text}")
    return "\n".join(lines)


def _parse_json_from_response(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        lines = [l for l in lines if not l.strip().startswith("```")]
        text = "\n".join(lines).strip()
    start = text.find("{")
    end = text.rfind("}") + 1
    if start >= 0 and end > start:
        text = text[start:end]
    return json.loads(text)


def evaluate_with_ai(chat, employee_name: str) -> dict:
    if not GEMINI_API_KEY:
        return None

    try:
        from google import genai
    except ImportError:
        return None

    try:
        client = genai.Client(api_key=GEMINI_API_KEY)

        chat_text = _format_chat(chat, employee_name)
        prompt = EVALUATION_PROMPT.format(
            employee_name=employee_name,
            chat_text=chat_text
        )

        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=prompt,
        )
        text = response.text.strip()

        result = _parse_json_from_response(text)
        return result

    except json.JSONDecodeError as e:
        logger.error(f"AI JSON parse error: {e}")
        return None
    except Exception as e:
        logger.error(f"AI evaluation error: {e}")
        return None


def is_ai_available() -> bool:
    if not GEMINI_API_KEY:
        return False
    try:
        from google import genai
        return True
    except Exception:
        return False
