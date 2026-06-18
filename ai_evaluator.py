import json
import os
import logging

logger = logging.getLogger(__name__)

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
DASHSCOPE_API_KEY = os.environ.get("DASHSCOPE_API_KEY", "")

EVALUATION_PROMPT = """Оцени софт-скиллы оператора: 1, 3 или 5.
5 = Хорошая коммуникация. Эмпатия когда исполнитель негативно настроен. При нейтральном вопросе — вежливый ответ по делу = 5.
3 = Сухой/формальный ответ при возмущении исполнителя. Не хватает тепла.
1 = Игнорирование эмоций исполнителя. Формализм.

Эмпатия нужна ТОЛЬКО при негативе исполнителя. Обычный вопрос-ответ = 5. Диалог с кнопками бота + короткий ответ = 5. Qugo — платформа для самозанятых.

Примеры:

ПРИМЕР 1 (оценка 5):
Оп: Здравствуйте! Сейчас уточню, нужно несколько минут.
Кл: Здравствуйте,подскажите пожалуйста,мне ни одна выплата не поступила
Оп: Ожидайте, пожалуйста. Сроки зачисления зависят от банка.
Кл: Спасибо!
Оператор ответил вежливо по делу. Исполнитель не негативно настроен.

ПРИМЕР 2 (оценка 3):
Оп: Здравствуйте!
Кл: Когда мне выплатят?! Я уже три дня жду, это невыносимо!
Оп: Выплаты обрабатываются. Ожидайте.
Оператор ответил формально, не проявил эмпати к возмущению.

ПРИМЕР 3 (оценка 1):
Кл: Оператор!!! Вы меня игнорируете!
Кл: Ужасный сервис, бесполезно!
Оп: Напишите ваш вопрос.
Кл: Я уже писала! Никто не отвечает!
Оператор проигнорировал возмущения исполнителя.

ПРАВИЛА ДЛЯ РЕКОМЕНДАЦИЙ:
- Рекомендации ДОЛЖНЫ быть персональными — опирайся на конкретные фразы оператора из диалога
- НЕ выдумывай рекомендации если оценка 5 — оставь пустой массив []
- НЕ пиши общие советы типа "будьте эмпатичны" — пиши конкретно что operator сказал не так и как нужно было сказать
- КАЖДАЯ рекомендация — ТОЛЬКО что улучшить в общении оператора. НЕ предлагай варианты решения проблемы клиента (не пиши "Передайте запрос в отдел", "Уточните у заказчика" и т.д.)

Формат — ТОЛЬКО JSON:
{{
  "criteria": [{{"name": "Софт-скиллы", "score": 5, "justification": "кратко"}}],
  "strengths": ["сильная"],
  "weaknesses": ["слабая"],
  "recommendations": ["рекомендация"]
}}

Оператор: {employee_name}
{chat_text}"""


def _format_chat(chat, employee_name: str) -> str:
    lines = []
    for m in chat.messages:
        if m.role.value == "bot":
            continue
        text = m.text.strip()
        skip = any(p in text for p in [
            "перешел на страницу", "покинул сайт", "переведён в статус",
            "отправил файл", "Crm_url", "Местоположение:", "Браузер:",
            "IP:", "ID: workman", "User_id:", "Имя:", "Телефон:", "URL профиля:",
            "ИНН:", "Пришел с", "Диалог автоназначен", "Сотрудник уже в пути",
            "Здравствуйте! Наш эксперт уже на связи", "Оператор",
            "Диалогу присвоены категории", "Оцените, пожалуйста",
            "Кнопки отправлены", "Переключаю чат на сотрудника",
            "Ulicom", "[ОЦЕНИТЬ]",
        ])
        if skip:
            continue
        role_label = "Оп" if m.role.value == "employee" else "Кл"
        lines.append(f"{role_label}: {text}")
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
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        logger.error(f"Failed to parse AI response: {text[:300]}")
        return None


def _evaluate_with_gemini(chat, employee_name: str) -> dict:
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
        return _parse_json_from_response(text)
    except Exception as e:
        logger.error(f"Gemini error: {e}")
        return None


def _evaluate_with_qwen(chat, employee_name: str) -> dict:
    api_key = os.environ.get("DASHSCOPE_API_KEY", "")
    if not api_key:
        return None

    try:
        import httpx
    except ImportError:
        return None

    try:
        chat_text = _format_chat(chat, employee_name)
        prompt = EVALUATION_PROMPT.format(
            employee_name=employee_name,
            chat_text=chat_text
        )
        url = "https://dashscope-intl.aliyuncs.com/compatible-mode/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        data = {
            "model": "qwen-plus",
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.3,
        }
        response = httpx.post(url, json=data, headers=headers, timeout=60)
        if response.status_code != 200:
            logger.error(f"Qwen API error: {response.status_code} {response.text[:200]}")
            return None
        result = response.json()
        if not isinstance(result, dict):
            logger.error(f"Qwen response is not dict: {str(result)[:300]}")
            return None
        if "choices" not in result:
            logger.error(f"Qwen response missing 'choices' key, keys: {list(result.keys())}")
            return None
        text = result["choices"][0]["message"]["content"].strip()
        usage = result.get("usage", {})
        _usage_stats["total_tokens"] += usage.get("total_tokens", 0)
        _usage_stats["calls"] += 1
        return _parse_json_from_response(text)
    except KeyError as e:
        logger.error(f"Qwen response missing expected key: {e}")
        return None
    except Exception as e:
        logger.error(f"Qwen error: {e}")
        return None


def evaluate_with_ai(chat, employee_name: str) -> dict:
    result = _evaluate_with_qwen(chat, employee_name)
    if result:
        return result
    result = _evaluate_with_gemini(chat, employee_name)
    if result:
        return result
    return None


_usage_stats = {"total_tokens": 0, "calls": 0, "errors": 0}


def get_usage_stats() -> dict:
    return dict(_usage_stats)


def is_ai_available() -> bool:
    return bool(os.environ.get("DASHSCOPE_API_KEY", "")) or bool(os.environ.get("GEMINI_API_KEY", ""))
