import re
import math
import asyncio
from typing import List, Optional
from models import Chat, ChatEvaluation, CriterionResult, MessageRole, CRITERIA
from scoring import calculate_total_score
from learning import get_good_examples


POLITE_PHRASES = [
    "пожалуйста", "благодарю", "спасибо", "рад помочь", "рад был помочь",
    "буду рад", "с удовольствием", "конечно", "обращайтесь", "всегда готовы",
    "всегда на связи", "хорошего дня", "добрый день", "добрый вечер",
    "доброе утро", "уважаем", "ценим", "сматри", "смело пишите",
]

EMPATHY_PHRASES = [
    "понимаю ваше", "понимаю как", "понимаю ситуацию", "сожалею",
    "это неприятно", "это действительно", "беспокойство", "как неприятно",
    "нам очень жаль", "приносим извинения", "извиняемся за",
    "приношу извинения", "извините за", "сочувствую", "понимаю вас",
    "понимаю", "нам важно", "стараюсь помочь",
]

RUDE_PHRASES = [
    "не знаю", "ничем не могу помочь", "ничем помочь не могу",
    "ваши проблемы", "как я уже говорил",
    "я же говорил", "читайте внимательнее", "это не наша проблема",
    "обратитесь куда-нибудь", "обратитесь в другое место",
    "что ещё", "ну и что", "вам же сказали", "я вам уже ответил",
    "это ваши проблемы", "не моя проблема", "я тут ни при чём",
    "разбирайтесь сами", "как хотите", "ваше дело",
    "я не обязан", "идите в", "пишите куда хотите",
]

DISMISSIVE_PHRASES = [
    "обратитесь в банк", "обратитесь в поддержку", "попробуйте сами",
    "это не ко мне", "не мой вопрос", "я не специалист",
    "обратитесь к", "напишите в",
]

SOLUTION_INDICATORS = [
    "для этого нужно", "вам необходимо", "вам нужно", "перейдите в",
    "нажмите на", "выберите", "откройте", "закройте", "сохраните",
    "подтвердите", "введите", "укажите", "проверьте", "убедитесь",
    "настройте", "зайдите в", "раздел", "вкладк", "кнопк",
    "рекомендую", "советую", "предлагаю", "лучше всего",
    "чтобы избежать", "в будущем", "для предотвращения",
    "сделайте следующее", "шаг", "инструкци", "алгоритм",
    "ссылк", "отправ", "сейчас", "попробуйте", "необходимо",
    "двухфакторн", "в настройках", "в профиле", "в личном кабинете",
    "в приложении", "на сайте", "через", "заполните", "прикрепите",
    "скриншот", "данные", "номер", "код", "пароль", "email",
    "составляет", "равен", "равна", "равно",
    "находится", "находитесь", "доступен", "доступна", "доступно",
    "активирован", "активирована", "подключен", "подключена",
    "оплачен", "оплачена", "доставлен", "доставлена",
    "оформлен", "оформлена", "получен", "получена",
    "помогу", "помочь", "подскажу", "подсказать",
    "объясню", "объяснить", "расскажу", "рассказать",
    "проверил", "проверила", "посмотрел", "уточнил", "обновил",
    "исправил", "поправил", "настроил",
    "отправил", "выслал", "продублировал",
    "причина в", "причина", "ошибка в",
    "так как", "потому что", "в связи с",
    "всё верно", "всё правильно", "подтверждаю",
    "действительно", "именно так",
    "можете", "можно", "будет",
]

GENERIC_QUESTION_PHRASES = [
    r"а что именно", r"что конкретно", r"уточните",
    r"поподробнее", r"расскажите подробнее", r"что-то ещё",
    r"какой именно", r"какая именно", r"что случилось",
    r"в чём проблема", r"а ещё раз", r"повторите",
    r"не совсем понял", r"не понял", r"можно подробнее",
]

GREETING_PHRASES = [
    "здравствуйте", "добрый день", "добрый вечер", "доброе утро",
    "приветствую", "рад вас слышать", "чем могу помочь",
    "чем могу помочь", "подскажите", "как могу помочь",
]

CLOSING_PHRASES = [
    "хорошего дня", "обращайтесь", "всегда рады", "всегда на связи",
    "при возникновении", "если возникнут", "если появятся",
    "если будут вопросы", "будем рады", "рад был помочь",
    "удачного", "всего доброго", "всего хорошего",
]


IMPERATIVE_VERBS = [
    "прекрати", "останови", "перестань",
    "убери", "забери",
    "перестаньте", "перестань", "отстань", "отстаньте",
]

SWEAR_WORDS = [
    "блин", "ёб", "еба", "хуй", "хуя", "пизд", "пиздец",
    "нахуй", "похуй", "оху", "аху", "охрен", "офиг", "офиге",
    "фигня", "дерьмо", "гавно", "гандон", "мудак", "дурак", "идиот",
    "козёл", "тварь", "сволочь", "дебил", "долба",
    "хер", "херня", "сука", "падла",
    "урод", "мразь",
]


def _client_expressed_negative(client_text: str) -> tuple:
    if not client_text.strip():
        return False, []
    tl = client_text.lower()
    reasons = []

    swear_hits = sum(1 for w in SWEAR_WORDS if w in tl)
    if swear_hits > 0:
        reasons.append("нецензурная лексика")

    aggressive_punct = _count_aggressive_punct(client_text)
    if aggressive_punct > 0:
        reasons.append("агрессивная пунктуация")

    imperative_hits = sum(
        1 for v in IMPERATIVE_VERBS if re.search(r'\b' + re.escape(v) + r'\b', tl)
    )
    if imperative_hits > 0:
        reasons.append("повелительное наклонение")

    frustration_phrases = [
        "отписк", "бесполезно", "бред", "ужас", "ужасно",
        "уже месяц", "несколько раз писал", "10т", "десятки раз", "каждый раз",
        "ни разу не помогли", "только отпис", "в суд", "жалоба",
        "не помогаете", "ни кто не помогает", "никто не помогает",
        "устал ждать", "надоело", "задолбал",
        "ненормально", "неприемлемо", "возмутительно",
        "уйду в другую", "уйду из", "увольняюсь", "менять работу",
        "ни кто не помогает",
    ]
    frustration_hits = sum(1 for p in frustration_phrases if p in tl)
    if frustration_hits > 0:
        reasons.append("фрустрация и недовольство")

    return (swear_hits > 0 or aggressive_punct > 0 or imperative_hits > 0 or frustration_hits > 0), reasons


def _get_employee_messages(chat: Chat) -> List[str]:
    return [m.text for m in chat.messages if m.role == MessageRole.EMPLOYEE]


def _get_client_messages(chat: Chat) -> List[str]:
    return [m.text for m in chat.messages if m.role == MessageRole.CLIENT]


def _get_all_text(messages: List[str]) -> str:
    return " ".join(messages).lower()


def _count_phrase_hits(text: str, phrases: List[str]) -> int:
    t = text.lower()
    return sum(1 for p in phrases if p in t)


def _count_regex_hits(text: str, patterns: List[str]) -> int:
    t = text.lower()
    return sum(1 for p in patterns if re.search(p, t))


def _count_questions(messages: List[str]) -> int:
    total = 0
    for m in messages:
        total += m.count("?")
    return total


def _count_caps_words(text: str) -> int:
    words = text.split()
    count = 0
    for w in words:
        clean = re.sub(r'[^а-яёa-z]', '', w.lower())
        if len(clean) > 2 and w == w.upper() and any(c.isalpha() for c in w):
            count += 1
    return count


def _count_aggressive_punct(text: str) -> int:
    return len(re.findall(r'!{2,}|\?{3,}|!\?|\?!', text))


def _avg_message_length(messages: List[str]) -> float:
    if not messages:
        return 0.0
    return sum(len(m) for m in messages) / len(messages)


def _has_dismissive_no_solution(text: str) -> bool:
    tl = text.lower()
    dismissive = any(p in tl for p in DISMISSIVE_PHRASES)
    solution = _count_phrase_hits(text, SOLUTION_INDICATORS) > 0
    return dismissive and not solution


def _client_expressed_problem(client_text: str) -> bool:
    problem_words = [
        "не работает", "не могу", "проблема", "ошибка", "сломал",
        "не получается", "баг", "глюч", "не открывается", "не загружается",
        "не приходит", "не приходит", "исчез", "пропал", "сбросил",
        "отклоняет", "отказ", "отмен", "не удалось", "трудност",
        "не заходит", "не заходит", "забыл", "потерял", "сбой",
    ]
    tl = client_text.lower()
    return any(p in tl for p in problem_words)


def _client_needs_apology(client_text: str) -> bool:
    tl = client_text.lower()

    third_party_services = ["мой налог", "фнс", "сбербанк", "тинькофф", "альфа", "втб",
        "телеграм", "telegram", "банк", "приложение заказчика"]
    if any(p in tl for p in third_party_services):
        return False

    payment_absence = ["нет задания", "нет акта", "не пришла выплата", "не поступила выплата",
        "не пришли деньги", "деньги не поступили", "нет выплаты", "нет задания на выплату"]
    if any(p in tl for p in payment_absence):
        return False

    client_data_error = ["ошибка в карте", "некорректные данные", "неправильный номер карты",
        "ошибся в реквизит", "ошибся в данных", "забыл карту", "не тот номер карты"]
    if any(p in tl for p in client_data_error):
        return False

    interface_noise = ["возникла ошибка / сложность", "ошибка ввода",
        "не уточнил суть обращ", "регистрация в qugo",
        "нажата кнопка", "тематика обращения"]
    tl_clean = tl
    for noise in interface_noise:
        tl_clean = tl_clean.replace(noise, "")
    tl = tl_clean

    clearly_system = [
        "из-за вас", "из-за системы", "ваша система", "по вине",
        "баг", "глюч", "сбой",
        "два чека", "две чека", "два одинаковых", "две одинаковых", "дубликат чека", "два акта", "две акт",
    ]
    if any(p in tl for p in clearly_system):
        return True

    qugo_service_faults = [
        "сломалось", "не открывается",
        "не загружается", "сбросил парол", "сбросил данные",
        "ошибка системы", "ошибка на стороне",
    ]
    if any(p in tl for p in qugo_service_faults):
        return True

    doc_error_context = ["чек", "расчёт", "расчет", "квитанци",
        "тариф", "комисси", "процент", "лимит", "баланс"]
    has_doc_error_context = any(p in tl for p in doc_error_context)
    if has_doc_error_context:
        error_words = ["недополучен", "отклоняется"]
        if any(p in tl for p in error_words):
            return True

    if "ошибка" in tl and not has_doc_error_context:
        client_own_mistake = ["это ошибка", "моя ошибка", "я ошиб", "я ошибся", "ошибся в ввод", "ошибся при ввод"]
        if any(p in tl for p in client_own_mistake):
            return False
        return True

    return False


def _compute_similarity(text1: str, text2: str) -> float:
    words1 = set(re.findall(r'\b\w{3,}\b', text1.lower()))
    words2 = set(re.findall(r'\b\w{3,}\b', text2.lower()))
    if not words1 or not words2:
        return 0.0
    intersection = words1 & words2
    union = words1 | words2
    return len(intersection) / len(union)


def _compare_with_good_examples(chat: Chat) -> float:
    examples = get_good_examples()
    if not examples:
        return 0.0

    emp_text = _get_all_text(_get_employee_messages(chat))
    if not emp_text.strip():
        return 0.0

    max_sim = 0.0
    for ex in examples[:10]:
        ex_emp_text = " ".join(m.text.lower() for m in ex.messages if m.role == MessageRole.EMPLOYEE)
        if not ex_emp_text.strip():
            continue
        sim = _compute_similarity(emp_text, ex_emp_text)
        max_sim = max(max_sim, sim)

    return max_sim


def _evaluate_extra_questions(chat: Chat) -> tuple:
    emp_msgs = _get_employee_messages(chat)
    client_msgs = _get_client_messages(chat)
    emp_text = _get_all_text(emp_msgs)
    client_text = _get_all_text(client_msgs)

    if not emp_msgs:
        return 1, "Сотрудник не отправил сообщений", ["Нет сообщений сотрудника"], []

    generic_q_count = _count_regex_hits(emp_text, GENERIC_QUESTION_PHRASES)
    total_questions = _count_questions(emp_msgs)

    emp_count = len(emp_msgs)
    client_count = len(client_msgs)
    msg_ratio = emp_count / max(client_count, 1)

    avg_len = _avg_message_length(emp_msgs)

    solution_hits = _count_phrase_hits(emp_text, SOLUTION_INDICATORS)
    has_greeting = _count_phrase_hits(emp_text, GREETING_PHRASES) > 0
    has_closing = _count_phrase_hits(emp_text, CLOSING_PHRASES) > 0

    penalty = 0.0
    justifications = []
    strengths = []
    weaknesses = []

    if generic_q_count >= 2 and solution_hits < 2:
        penalty += 2.0
        weaknesses.append("Задано 2+ уточняющих вопроса общего характера без конкретных решений")
        justifications.append(f"Обнаружено {generic_q_count} общих уточняющих вопросов")

    if total_questions > len(client_msgs) + 3 and solution_hits < 2:
        penalty += 1.5
        weaknesses.append("Слишком много вопросов, мало конкретных решений")
        justifications.append(f"{total_questions} вопросов при {len(client_msgs)} сообщениях клиента")

    if msg_ratio > 2.0 and avg_len < 50:
        penalty += 1.0
        weaknesses.append("Много коротких сообщений вместо одного полного ответа")

    if solution_hits >= 3:
        penalty -= 1.0
        strengths.append("Сообщение содержит конкретные инструкции для решения")

    if has_greeting and has_closing:
        penalty -= 0.5
        strengths.append("Диалог начат с приветствия и завершён корректно")

    if avg_len >= 80 and solution_hits >= 1:
        strengths.append("Подробные развёрнутые ответы")

    score = 5
    if penalty >= 2.0:
        score = 1
    elif penalty >= 1.0:
        score = 3

    if score == 5:
        justifications.append(
            "Вопросы и сообщения нацелены на решение вопроса. Лишних уточнений не обнаружено."
        )
    elif score == 3:
        justifications.append("Есть 1 лишнее уточнение или избыточное количество сообщений.")
    else:
        justifications.append("2+ лишних уточнения. Сообщения не нацелены на решение вопроса.")

    return score, " ".join(justifications), strengths, weaknesses


def _detect_ignored_messages(chat: Chat) -> bool:
    follow_up_phrases = [
        "ну что", "что там", "есть ответ", "почему молчите",
        "ау", "алло", "вы тут", "вы тут?", "кто-нибудь",
        "ответьте", "игнорируете", "проигнорировали",
        "жду ответа", "жду вашего", "когда ответ", "сколько ждать",
        "ужас", "отписк", "бред", "бесполезно", "надоело",
    ]
    msgs = chat.messages
    for i in range(len(msgs) - 1):
        msg = msgs[i]
        next_msg = msgs[i + 1]
        if msg.role == MessageRole.CLIENT and next_msg.role == MessageRole.CLIENT:
            next_text = next_msg.text.lower()
            skip_phrases = ["нажата кнопка", "отправил файл", "отправлена фотография",
                "отправлен файл"]
            if any(p in next_text for p in skip_phrases):
                continue
            if any(p in next_text for p in follow_up_phrases):
                has_response_after = any(
                    m.role == MessageRole.EMPLOYEE for m in msgs[i + 2:]
                )
                if not has_response_after:
                    return True

    consecutive_client = 0
    max_consecutive = 0
    last_client_texts = []
    last_consecutive_idx = 0
    for j, m in enumerate(msgs):
        if m.role == MessageRole.CLIENT:
            text = m.text.lower()
            skip = ["нажата кнопка", "отправил файл"]
            if not any(p in text for p in skip) and len(m.text.strip()) > 40:
                consecutive_client += 1
                max_consecutive = max(max_consecutive, consecutive_client)
                last_client_texts.append(m.text.lower())
                last_consecutive_idx = j
            else:
                pass
        elif m.role == MessageRole.EMPLOYEE:
            consecutive_client = 0
            last_client_texts = []

    if max_consecutive >= 3:
        combined = " ".join(last_client_texts)
        if any(p in combined for p in
               ["ужас", "отписк", "бред", "бесполезно", "надоело", "уйду",
                "задолбал", "ненормально", "в суд", "жалоба"]):
            has_response_after = any(
                m.role == MessageRole.EMPLOYEE for m in msgs[last_consecutive_idx + 1:]
            )
            if not has_response_after:
                return True

    return False


def _evaluate_problem_resolution(chat: Chat) -> tuple:
    emp_msgs = _get_employee_messages(chat)
    client_msgs = _get_client_messages(chat)
    emp_text = _get_all_text(emp_msgs)
    client_text = _get_all_text(client_msgs)

    if not emp_msgs or not client_msgs:
        return 1, "Недостаточно данных для оценки", ["Не хватает данных"], []

    solution_hits = _count_phrase_hits(emp_text, SOLUTION_INDICATORS)
    has_specific_info = bool(re.search(r'\+?\d[\d\s\-\(\)]{7,}', emp_text)) or \
                        bool(re.search(r'\S+@\S+\.\S+', emp_text)) or \
                        bool(re.search(r'https?://\S+', emp_text)) or \
                        solution_hits >= 3

    client_problem = _client_expressed_problem(client_text)

    has_dismissive = _has_dismissive_no_solution(emp_text)
    answer_off_topic = solution_hits == 0 and client_problem

    mentions_prevention = any(
        p in emp_text for p in [
            "чтобы избежать", "в будущем", "для предотвращения",
            "рекомендую", "советую", "предупрежд", "осторож",
        ]
    )

    gives_steps = bool(re.search(r'\d[\).]', emp_text)) and solution_hits >= 2

    strengths = []
    weaknesses = []
    justifications = []
    bonus = 0.0
    penalty = 0.0

    if has_dismissive:
        penalty += 3.0
        weaknesses.append("Отправлен к другому источнику без попытки решить проблему")

    if answer_off_topic:
        penalty += 2.5
        weaknesses.append("Ответ не соответствует вопросу клиента")

    if solution_hits >= 4:
        bonus += 1.5
        strengths.append("Дана исчерпывающая информация с конкретными действиями")

    if gives_steps:
        bonus += 1.0
        strengths.append("Предложено пошаговое решение")

    if has_specific_info:
        bonus += 0.5
        strengths.append("Указана конкретная информация (контакты, ссылки, данные)")

    if mentions_prevention:
        bonus += 1.0
        strengths.append("Предусмотрен сценарий ошибки и рассказано, как её избежать")

    if solution_hits == 0 and not has_dismissive:
        if len(emp_msgs) >= 1 and _avg_message_length(emp_msgs) >= 25:
            penalty += 0.5
            weaknesses.append("Ответ дан, но без пошаговой инструкции")
        else:
            penalty += 1.5
            weaknesses.append("Нет конкретных предложений для решения проблемы")

    score = 5
    if penalty >= 2.0:
        score = 1
    elif penalty >= 1.0:
        score = 3
    elif solution_hits <= 1 and not gives_steps and _avg_message_length(emp_msgs) < 25:
        score = 3

    if bonus >= 2.0 and penalty < 1.0:
        score = 5

    if score == 5:
        justifications.append(
            "Проблема верно понята. Дана исчерпывающая информация. "
            "Предвидены вопросы, предложено решение."
        )
    elif score == 3:
        justifications.append(
            "Вопрос решён не полностью или не предусмотрен сценарий ошибки."
        )
    else:
        justifications.append(
            "Вопрос не понят или дан неверный ответ."
        )

    return score, " ".join(justifications), strengths, weaknesses


_CLIENT_NEGATIVE_MARKERS = [
    "жду", "долго", "мне никто не отвечает", "никто не отвечает",
    "ignor", "игнориру", "ужасн", "бесполез", "отвратительн",
    "не работает", "не работает!", "всё сломал", "всё сломалось",
    "!", "!!!", "????",
    "когда выплатят", "когда деньги", "где мои деньги",
    "позор", "обман", "мошенн",
    "уже третий раз", "уже второй раз", "сколько можно",
    "неужели так сложно", "я теряю терпение", "потеряю терпение",
    "вас игнор", "обращался уже", "писал уже", "звонил уже",
    "противно", "отвратительно", "бред", "чушь",
    "никакой помощи", "никакой реакции", "терпение лопнуло",
]


def _client_seems_negative(chat: Chat) -> bool:
    client_msgs = _get_client_messages(chat)
    if len(client_msgs) <= 1:
        return False
    client_text = _get_all_text(client_msgs).lower()
    hits = sum(1 for marker in _CLIENT_NEGATIVE_MARKERS if marker in client_text)
    return hits >= 2


def _evaluate_tone_politeness(chat: Chat) -> tuple:
    emp_msgs = _get_employee_messages(chat)
    client_msgs = _get_client_messages(chat)
    emp_text = _get_all_text(emp_msgs)
    client_text = _get_all_text(client_msgs)

    if not emp_msgs:
        return 1, "Нет сообщений сотрудника", [], ["Нет сообщений"]

    bot_msgs = [m for m in chat.messages if m.role == MessageRole.BOT]
    real_emp_msgs = [m for m in chat.messages if m.role == MessageRole.EMPLOYEE]
    is_bot_heavy = len(bot_msgs) > len(real_emp_msgs)

    if is_bot_heavy:
        return 5, "Диалог с ботом, оператор дал верный ответ", [], []

    rude_count = _count_phrase_hits(emp_text, RUDE_PHRASES)

    client_negative, neg_reasons = _client_expressed_negative(client_text)
    has_apology = any(
        p in emp_text for p in [
            "извин", "сожалею", "жаль", "приношу", "извиняемся", "прошу прощения",
        ]
    )
    has_empathy = _count_phrase_hits(emp_text, EMPATHY_PHRASES) > 0

    strengths = []
    weaknesses = []
    justifications = []
    penalty = 0.0

    ignored_client = _detect_ignored_messages(chat)
    if ignored_client:
        penalty += 3.0
        weaknesses.append("Оператор проигнорировал сообщение клиента и закрыл/не ответил на диалог")

    if client_negative and not has_empathy and not has_apology:
        penalty += 2.0
        reasons_str = ", ".join(neg_reasons)
        weaknesses.append(f"Клиент выразил негатив ({reasons_str}) — оператор не проявил эмпатию")

    if rude_count > 0:
        penalty += 3.0
        weaknesses.append("Обнаружены грубые или обесценивающие фразы")

    score = 5
    if penalty >= 3.0:
        score = 1

    if score == 5:
        justifications.append(
            "Вежливое общение, отсутствие грубости. Вопрос клиента решён."
        )
    elif score == 1:
        justifications.append(
            "Грубость, обесценивание или игнорирование клиента."
        )

    return score, " ".join(justifications), strengths, weaknesses


def _evaluate_chat(chat: Chat, use_ai: bool = False) -> ChatEvaluation:
    tp_score, tp_just, tp_str, tp_weak = _evaluate_tone_politeness(chat)

    ai_result = None
    if use_ai:
        if not _client_seems_negative(chat):
            tp_score, tp_just = 5, "Исполнитель не выражал негатив, вежливое общение"
        else:
            try:
                from ai_evaluator import evaluate_with_ai, is_ai_available
                if is_ai_available():
                    ai_result = evaluate_with_ai(chat, chat.employee_name or "Неизвестный")
            except Exception:
                pass

    if ai_result and "criteria" in ai_result:
        ai_criteria = {c["name"]: c for c in ai_result["criteria"]}
        ai_soft = ai_criteria.get("Софт-скиллы")
        if ai_soft and ai_soft.get("score") in (1, 3, 5):
            tp_score = ai_soft["score"]
            tp_just = ai_soft.get("justification", tp_just)

        all_str = list(dict.fromkeys(ai_result.get("strengths", [])))
        all_weak = list(dict.fromkeys(ai_result.get("weaknesses", [])))
        recommendations = ai_result.get("recommendations", []) or _generate_recommendations(all_weak, tp_score)
    else:
        all_str = tp_str
        all_weak = tp_weak
        recommendations = _generate_recommendations(all_weak, tp_score)

    boost_msg = ""
    if not use_ai:
        example_sim = _compare_with_good_examples(chat)
        if example_sim > 0.4:
            boost_msg = " (сходство с эталонным диалогом учтено)"

    criteria_scores = [
        CriterionResult(name="Софт-скиллы", score=tp_score, justification=tp_just),
    ]

    total_score = calculate_total_score(criteria_scores)

    score_label = {100: "Отлично", 30: "Удовлетворительно", 0: "Критично"}.get(total_score, str(total_score))

    if tp_score == 5:
        summary = f"Оценка {total_score}/100{boost_msg}. Хороший уровень коммуникации."
    elif tp_score == 3:
        summary = f"Оценка {total_score}/100{boost_msg}. Недостаточно проявлена эмпатия."
    else:
        summary = f"Оценка {total_score}/100{boost_msg}. Игнорирование переживаний исполнителя."

    return ChatEvaluation(
        chat_id=chat.id,
        employee_name=chat.employee_name or "Неизвестный",
        date=chat.date,
        criteria_scores=criteria_scores,
        total_score=total_score,
        strengths=all_str,
        weaknesses=all_weak,
        recommendations=recommendations,
        summary=summary,
    )


def _generate_recommendations(weaknesses: List[str], soft_score: int) -> List[str]:
    recs = []

    for w in weaknesses:
        w_lower = w.lower()
        if "игнорир" in w_lower:
            recs.append(
                "В диалоге вы не отреагировали на сообщение клиента — после этого диалог был закрыт. "
                "Даже если ответа нет, напишите: «Я передал ваш вопрос коллегам, вернусь с ответом в течение часа»."
            )
        elif "груб" in w_lower or "обесценив" in w_lower:
            recs.append(
                "В ответе обнаружены формулировки, которые могут быть восприняты как грубые или обесценивающие. "
                "Замените формальные ответы на личные: «Понимаю ваше беспокойство» вместо «Выплаты обрабатываются»."
            )
        elif "негатив" in w_lower and ("не проявил" in w_lower or "не отреагировал" in w_lower):
            recs.append(
                "Клиент выражал недовольство, но вы не показали, что понимаете его эмоции. "
                "Начинайте ответ с сочувствия: «Понимаю, это неприятно. Давайте разберёмся вместе»."
            )

    return recs


def evaluate_chats_batch(
    chats: List[Chat],
    api_key: str = "",
    api_base: str = "",
    model: str = "",
    use_ai: bool = False,
    progress_callback=None,
) -> list:
    evaluations = []
    total = len(chats)

    for i, chat in enumerate(chats):
        if progress_callback:
            if asyncio.iscoroutinefunction(progress_callback):
                import asyncio as _aio
                try:
                    loop = _aio.get_event_loop()
                    if loop.is_running():
                        _aio.ensure_future(progress_callback(i, total, chat.id))
                    else:
                        loop.run_until_complete(progress_callback(i, total, chat.id))
                except RuntimeError:
                    pass
            else:
                progress_callback(i, total, chat.id)

        evaluation = _evaluate_chat(chat, use_ai=use_ai)
        evaluations.append(evaluation)

    if progress_callback:
        try:
            if asyncio.iscoroutinefunction(progress_callback):
                import asyncio as _aio
                try:
                    loop = _aio.get_event_loop()
                    if loop.is_running():
                        _aio.ensure_future(progress_callback(total, total, None))
                    else:
                        loop.run_until_complete(progress_callback(total, total, None))
                except RuntimeError:
                    pass
            else:
                progress_callback(total, total, None)
        except Exception:
            pass

    return evaluations


async def evaluate_chat_single(chat: Chat, use_ai: bool = False, **kwargs) -> ChatEvaluation:
    return _evaluate_chat(chat, use_ai=use_ai)
