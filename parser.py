import re
import os
import uuid
from typing import List, Optional, Tuple
import xml.etree.ElementTree as ET
from models import Message, MessageRole, Chat

BOT_KEYWORDS = [
    "поддержка клиентов", "бот", "bot", "автоответчик",
    "auto-reply", "робот", "robot", "система уведомлений",
    "автоинформатор", "auto", "service bot",
]

_BOT_SENDERS = set()

BOT_TEXT_MARKERS = [
    "Кнопки отправлены:",
    "Переключаю на сотрудника.",
    "Переключаю на оператора",
    "Какой у вас вопрос?",
    "Сейчас посмотрю ваши последние выплаты, секунду",
    "Выберите выплату, по которой у вас вопрос:",
    "Смотрю детали этой выплаты",
    "Опишите, пожалуйста, с чем именно нужна помощь",
]

SEPARATOR_PATTERNS = [
    r"^={3,}",
    r"^-{3,}",
    r"^\*{3,}",
    r"^#{3,}",
    r"^=+\s*диалог\s*(№|#|номер)?\s*\d+\s*=+",
    r"^=+\s*чат\s*(№|#|номер)?\s*\d+\s*=+",
    r"^=+\s*dialog\s*#?\d+\s*=+",
    r"^=+\s*conversation\s*#?\d+\s*=+",
    r"^диалог\s*(№|#|номер)?\s*\d+",
    r"^чат\s*(№|#|номер)?\s*\d+",
    r"^conversation\s*#?\d+",
    r"^dialog\s*#?\d+",
    r"^№\s*:?\s*\d+",
]

METADATA_PREFIXES = (
    "начат:", "имя посетителя:", "отделы:", "местоположение:",
    "браузер:", "ip:", "id:", "user_id:", "имя:", "телефон:",
    "url профиля:", "компания:", "инн:", "crm_url:", "site_url:",
    "пришел с", "отделы", "№:",
)

SYSTEM_MSG_PATTERNS = [
    re.compile(r"^диалог\s+автоназначен", re.I),
    re.compile(r"^диалогу присвоены категории", re.I),
    re.compile(r"^\[посетитель отправил файл", re.I),
    re.compile(r"^нажата кнопка", re.I),
    re.compile(r"^кнопки отправлен", re.I),
    re.compile(r"^\[оценить\]", re.I),
]

SYSTEM_NO_TS_PATTERNS = [
    re.compile(r"^(посетитель|диалог|сотрудник|оператор|мы работаем|наш эксперт|кнопки|вы будете|оцените)", re.I),
    re.compile(r"^\[посетитель", re.I),
    re.compile(r"^\[оценить\]", re.I),
    re.compile(r"^для подписания", re.I),
    re.compile(r"^\d+\)\s*(перейдите|откройте|зайдите)", re.I),
]

OPERATOR_DETECT_PATTERNS = [
    re.compile(r"оператор\s+(\S+(?:\s+\S+?)?)\s+(?:закрыл|изменил)", re.I),
    re.compile(r"диалог\s+автоназначен\s+на\s+оператора\s+(\S+(?:\s+\S+)?)", re.I),
    re.compile(r"\]\s*(\S+(?:\s+\S+)?)\s*\((?:сотрудник|оператор|менеджер)\)\s*:", re.I),
    re.compile(r"^(\S+(?:\s+\S+)?)\s*\((?:сотрудник|оператор|менеджер)\)\s*:", re.I),
    re.compile(r"^(\S+(?:\s+\S+)?)\s*:\s*перевожу\s+обращение\s+на\s+оператор", re.I),
    re.compile(r"^(\S+(?:\s+\S+)?)\s*:\s*перевожу\s+вас\s+на\s+оператор", re.I),
]

TXT_PATTERNS = [
    re.compile(
        r"\[(\d{2}\.\d{2}\.\d{4}\s+\d{2}:\d{2}:\d{2})\]\s*(.+?)\s*(?:\((.+?)\))?\s*:\s*(.*)"
    ),
    re.compile(
        r"\[(\d{2}\.\d{2}\.\d{4}\s+\d{2}:\d{2})\]\s*(.+?)\s*(?:\((.+?)\))?\s*:\s*(.*)"
    ),
    re.compile(
        r"(\d{2}\.\d{2}\.\d{4}\s+\d{2}:\d{2}:\d{2})\s*[-–]\s*(.+?)\s*(?:\((.+?)\))?\s*:\s*(.*)"
    ),
    re.compile(
        r"(\d{2}\.\d{2}\.\d{4}\s+\d{2}:\d{2})\s*[-–]\s*(.+?)\s*(?:\((.+?)\))?\s*:\s*(.*)"
    ),
    re.compile(
        r"(\d{2}:\d{2}:\d{2})\s+(\S+(?:\s+\S+){0,3}?)\s*:\s+(.*)"
    ),
    re.compile(
        r"(\d{2}:\d{2})\s*[-–]\s*(.+?)\s*(?:\((.+?)\))?\s*:\s*(.*)"
    ),
    re.compile(
        r"(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})\s*(.+?)\s*(?:\((.+?)\))?\s*:\s*(.*)"
    ),
    re.compile(
        r"(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2})\s*(.+?)\s*(?:\((.+?)\))?\s*:\s*(.*)"
    ),
]

ROLE_PREFIX_PATTERNS = [
    (re.compile(r"^сотрудник\s*:\s*(.*)", re.IGNORECASE), MessageRole.EMPLOYEE),
    (re.compile(r"^оператор\s*:\s*(.*)", re.IGNORECASE), MessageRole.EMPLOYEE),
    (re.compile(r"^менеджер\s*:\s*(.*)", re.IGNORECASE), MessageRole.EMPLOYEE),
    (re.compile(r"^клиент\s*:\s*(.*)", re.IGNORECASE), MessageRole.CLIENT),
    (re.compile(r"^пользователь\s*:\s*(.*)", re.IGNORECASE), MessageRole.CLIENT),
    (re.compile(r"^agent\s*:\s*(.*)", re.IGNORECASE), MessageRole.EMPLOYEE),
    (re.compile(r"^customer\s*:\s*(.*)", re.IGNORECASE), MessageRole.CLIENT),
    (re.compile(r"^employee\s*:\s*(.*)", re.IGNORECASE), MessageRole.EMPLOYEE),
]


def is_bot(sender: str) -> bool:
    sender_lower = sender.lower().strip()
    if any(kw in sender_lower for kw in BOT_KEYWORDS):
        return True
    return any(bs in sender_lower for bs in _BOT_SENDERS)


def _detect_bot_senders(content: str) -> set:
    bot_senders = set()
    for line in content.split("\n"):
        if "Кнопки отправлен" not in line:
            continue
        m = re.match(r"\d{2}:\d{2}(?::\d{2})?\s+(\S+(?:\s+\S+){0,2}?)\s*:\s*Кнопки отправлен", line)
        if m:
            sender = m.group(1).strip()
            if sender and len(sender) > 1:
                bot_senders.add(sender.lower())
    return bot_senders


def is_bot_message(sender: str, text: str) -> bool:
    if is_bot(sender):
        return True
    for marker in BOT_TEXT_MARKERS:
        if marker in text:
            return True
    return False


def detect_role(sender: str, known_employees: Optional[List[str]] = None) -> MessageRole:
    if is_bot(sender):
        return MessageRole.BOT

    if known_employees:
        sender_lower = sender.strip().lower()
        for emp in known_employees:
            if sender_lower == emp.strip().lower():
                return MessageRole.EMPLOYEE

        sender_words = set(sender_lower.split())
        if sender_words:
            matches = []
            for emp in known_employees:
                emp_words = set(emp.strip().lower().split())
                if sender_words == emp_words or \
                   (sender_words.issubset(emp_words) and len(sender_words) < len(emp_words)):
                    matches.append(emp)
            if len(matches) == 1:
                return MessageRole.EMPLOYEE
            if len(matches) > 1 and len(sender_words) == 1:
                name_only = sender_lower
                for emp in known_employees:
                    parts = emp.strip().lower().split()
                    if parts[-1] == name_only:
                        matches_name = [e for e in known_employees if e.strip().lower().split()[-1] == name_only]
                        if len(matches_name) == 1:
                            return MessageRole.EMPLOYEE

        return MessageRole.CLIENT

    return MessageRole.UNKNOWN


def _detect_operator_names(content: str) -> List[str]:
    bot_senders = _detect_bot_senders(content)

    operators = set()
    for pattern in OPERATOR_DETECT_PATTERNS:
        for m in pattern.finditer(content):
            name = m.group(1).strip()
            if len(name) > 1 and not name.startswith("ссылк"):
                if name.lower() in bot_senders:
                    continue
                operators.add(name)

    filtered = set()
    for name in operators:
        nw = set(name.lower().split())
        is_subset = False
        for other in operators:
            if other == name:
                continue
            ow = set(other.lower().split())
            if len(nw) < len(ow) and nw.issubset(ow):
                is_subset = True
                break
        if not is_subset:
            filtered.add(name)
    return sorted(filtered)


def _is_separator(line: str) -> bool:
    stripped = line.strip()
    if not stripped:
        return False
    for pattern in SEPARATOR_PATTERNS:
        if re.match(pattern, stripped, re.IGNORECASE):
            return True
    return False


def _is_metadata(line: str) -> bool:
    stripped = line.strip().lower()
    if not stripped:
        return True
    for prefix in METADATA_PREFIXES:
        if stripped.startswith(prefix):
            return True
    if stripped.startswith("---"):
        return True
    return False


def _is_system_message(text: str) -> bool:
    for pattern in SYSTEM_MSG_PATTERNS:
        if pattern.match(text):
            return True
    return False


def _extract_dialog_date(lines: List[str]) -> Optional[str]:
    for line in lines:
        stripped = line.strip()
        m = re.match(r"Начат:\s*(\d{2}\.\d{2}\.\d{4})", stripped, re.I)
        if m:
            return m.group(1)
    return None


def _is_new_message(line: str) -> bool:
    stripped = line.strip()
    if not stripped:
        return False
    if _is_separator(stripped):
        return True
    for pattern in TXT_PATTERNS:
        if re.match(pattern, stripped):
            return True
    for role_pattern, _ in ROLE_PREFIX_PATTERNS:
        if role_pattern.match(stripped):
            return True
    return False


def _parse_ts_format(lines: List[str], known_employees: List[str]) -> Tuple[List[Message], bool]:
    messages = []
    pattern_matched = False
    i = 0
    while i < len(lines):
        stripped = lines[i].strip()
        i += 1
        if not stripped or _is_metadata(stripped):
            continue

        if _is_separator(stripped):
            continue

        matched = False
        for pattern in TXT_PATTERNS:
            m = pattern.match(stripped)
            if m:
                groups = m.groups()
                timestamp = groups[0]

                if len(groups) == 4:
                    sender = groups[1].strip()
                    role_hint = groups[2]
                    text = groups[3].strip()
                elif len(groups) == 3:
                    sender = groups[1].strip()
                    role_hint = None
                    text = groups[2].strip()
                else:
                    continue

                if not sender or not text:
                    continue

                while i < len(lines):
                    if _is_new_message(lines[i]):
                        break
                    next_line = lines[i].strip()
                    if next_line:
                        text += "\n" + next_line
                    i += 1

                if _is_system_message(text):
                    continue
                if _is_system_message(sender + " " + text):
                    continue

                text_clean = re.sub(r"^\[посетитель отправил файл:.*?\]$", "", text, flags=re.I).strip()
                if not text_clean:
                    continue

                if role_hint:
                    role_hint_lower = role_hint.lower()
                    if any(kw in role_hint_lower for kw in ["сотрудник", "оператор", "менеджер", "agent", "employee"]):
                        role = MessageRole.EMPLOYEE
                    elif any(kw in role_hint_lower for kw in ["клиент", "пользователь", "customer", "client"]):
                        role = MessageRole.CLIENT
                    else:
                        role = detect_role(sender, known_employees)
                else:
                    role = detect_role(sender, known_employees)

                if is_bot_message(sender, text_clean):
                    role = MessageRole.BOT

                messages.append(Message(
                    timestamp=timestamp,
                    sender=sender,
                    role=role,
                    text=text_clean
                ))
                pattern_matched = True
                matched = True
                break

        if not matched:
            for role_pattern, role_val in ROLE_PREFIX_PATTERNS:
                m = role_pattern.match(stripped)
                if m:
                    text = m.group(1).strip()
                    while i < len(lines):
                        if _is_new_message(lines[i]):
                            break
                        next_line = lines[i].strip()
                        if next_line:
                            text += "\n" + next_line
                        i += 1

                    sender_name = role_val.value
                    if role_val == MessageRole.EMPLOYEE:
                        sender_name = "Сотрудник"
                    elif role_val == MessageRole.CLIENT:
                        sender_name = "Клиент"
                    messages.append(Message(
                        timestamp=None,
                        sender=sender_name,
                        role=role_val,
                        text=text
                    ))
                    pattern_matched = True
                    break

        if not matched and messages:
            messages[-1].text += "\n" + stripped

    return messages, pattern_matched


def _group_into_chats(messages: List[Message], known_employees: Optional[List[str]] = None, dialog_date: str = None, chat_id_prefix: str = "1", use_time_boundary: bool = True) -> List[Chat]:
    if not messages:
        return []

    if known_employees:
        for msg in messages:
            if msg.role == MessageRole.UNKNOWN:
                msg.role = detect_role(msg.sender, known_employees)

    chats = []
    current_messages = []
    chat_idx = 1

    for i, msg in enumerate(messages):
        if use_time_boundary and i > 0 and _is_chat_boundary(messages, i):
            if current_messages:
                emp_name = _find_employee_name(current_messages)
                date = dialog_date
                if not date and current_messages[0].timestamp:
                    ts = current_messages[0].timestamp
                    if len(ts) >= 10:
                        date = ts[:10]
                chats.append(Chat(
                    id=f"{chat_id_prefix}_{chat_idx}",
                    employee_name=emp_name,
                    date=date,
                    messages=current_messages
                ))
                chat_idx += 1
                current_messages = []
        current_messages.append(msg)

    if current_messages:
        emp_name = _find_employee_name(current_messages)
        date = dialog_date
        if not date and current_messages[0].timestamp:
            ts = current_messages[0].timestamp
            if len(ts) >= 10:
                date = ts[:10]
        chats.append(Chat(
            id=f"{chat_id_prefix}_{chat_idx}",
            employee_name=emp_name,
            date=date,
            messages=current_messages
        ))

    return chats


def _is_chat_boundary(messages: List[Message], idx: int) -> bool:
    prev_ts = messages[idx - 1].timestamp
    curr_ts = messages[idx].timestamp
    if prev_ts and curr_ts:
        try:
            for fmt in ["%d.%m.%Y %H:%M:%S", "%d.%m.%Y %H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%H:%M:%S", "%H:%M"]:
                try:
                    from datetime import datetime, timedelta
                    t1 = datetime.strptime(prev_ts, fmt)
                    t2 = datetime.strptime(curr_ts, fmt)
                    diff = (t2 - t1).total_seconds()
                    if "%H" in fmt and "%d" not in fmt and "%Y" not in fmt:
                        if diff < 0:
                            diff += 86400
                    if diff > 7200:
                        return True
                    break
                except ValueError:
                    continue
        except Exception:
            pass
    return False


def _find_employee_name(messages: List[Message]) -> Optional[str]:
    for msg in messages:
        if msg.role == MessageRole.EMPLOYEE and msg.sender not in ["Сотрудник", "Оператор", "Менеджер"]:
            return msg.sender
    return None


def _split_dialogs_by_separator(content: str) -> List[Tuple[str, List[str]]]:
    parts = []
    current_lines = []
    current_id = "1"
    dialog_counter = 0
    for line in content.split("\n"):
        stripped = line.strip()
        m_num = re.match(r"^№\s*:?\s*(\d+)", stripped, re.I)
        m_dialog = re.match(r"^=+\s*(?:диалог|чат|dialog|conversation)\s*(?:№|#|номер)?\s*(\d+)", stripped, re.I)
        if m_num:
            if current_lines:
                parts.append((current_id, current_lines))
            current_id = m_num.group(1)
            current_lines = [line]
        elif m_dialog:
            if current_lines:
                parts.append((current_id, current_lines))
            current_id = m_dialog.group(1)
            current_lines = [line]
        elif _is_separator(stripped) and not current_lines:
            current_lines.append(line)
        else:
            current_lines.append(line)
    if current_lines:
        parts.append((current_id, current_lines))
    return parts


def _enrich_employee_names(chats: List[Chat], known_employees: List[str], block_context: Optional[str] = None) -> None:
    if not known_employees:
        return
    sorted_emps = sorted(known_employees, key=lambda x: len(x), reverse=True)
    ctx_emps = sorted_emps
    if block_context:
        ctx_lower = block_context.strip().lower()
        preferred = [e for e in sorted_emps if e.strip().lower() == ctx_lower]
        if preferred:
            ctx_emps = preferred + [e for e in sorted_emps if e.strip().lower() != ctx_lower]

    def context_match(name: str) -> str:
        nw = set(name.strip().lower().split())
        if not nw:
            return name
        candidates = []
        for emp in ctx_emps:
            ew = set(emp.strip().lower().split())
            if nw == ew or (nw.issubset(ew) and len(nw) < len(ew)):
                candidates.append(emp)
        if len(candidates) == 1:
            return candidates[0]
        if len(candidates) > 1 and block_context:
            ctx_lower = block_context.strip().lower()
            for emp in candidates:
                if emp.strip().lower() == ctx_lower:
                    return emp
        return name

    for chat in chats:
        if chat.employee_name:
            chat.employee_name = context_match(chat.employee_name)
        for msg in chat.messages:
            if msg.role == MessageRole.EMPLOYEE:
                msg.sender = context_match(msg.sender)
            elif msg.role == MessageRole.UNKNOWN:
                matched = context_match(msg.sender)
                if matched != msg.sender:
                    msg.sender = matched
                    msg.role = MessageRole.EMPLOYEE


def _find_block_employee(block_lines: List[str], known_employees: List[str] = None) -> Optional[str]:
    all_text = "\n".join(block_lines)
    m = re.search(r"диалог\s+автоназначен\s+на\s+оператора\s+(\S+(?:\s+\S+)?)", all_text, re.I)
    if m:
        found = m.group(1).strip()
        if known_employees:
            for emp in known_employees:
                if found.lower() in emp.lower():
                    return emp
        return found
    m = re.search(r"оператор\s+(\S+(?:\s+\S+?)?)\s+(?:закрыл|изменил)", all_text, re.I)
    if m:
        found = m.group(1).strip()
        if known_employees:
            for emp in known_employees:
                if found.lower() in emp.lower():
                    return emp
        return found
    return None


def parse_txt(content: str) -> List[Chat]:
    global _BOT_SENDERS
    _BOT_SENDERS = _detect_bot_senders(content)

    known_employees = _detect_operator_names(content)

    dialog_blocks = _split_dialogs_by_separator(content)

    if len(dialog_blocks) <= 1:
        result = _parse_single_block(content.split("\n"), known_employees)
        _enrich_employee_names(result, known_employees)
        return result

    all_chats = []
    for dialog_id, block_lines in dialog_blocks:
        block_employee = _find_block_employee(block_lines, known_employees)
        date = _extract_dialog_date(block_lines)
        messages, matched = _parse_ts_format(block_lines, known_employees)

        if not matched:
            msgs = []
            for line in block_lines:
                stripped = line.strip()
                if not stripped or _is_metadata(stripped):
                    continue
                if ":" in stripped:
                    parts = stripped.split(":", 1)
                    sender = parts[0].strip()
                    text = parts[1].strip() if len(parts) > 1 else ""
                    if _is_system_message(text):
                        continue
                    role = MessageRole.UNKNOWN
                    if is_bot_message(sender, text):
                        role = MessageRole.BOT
                    elif known_employees:
                        role = detect_role(sender, known_employees)
                    if text:
                        msgs.append(Message(
                            timestamp=None,
                            sender=sender,
                            role=role,
                            text=text
                        ))

            if msgs:
                emp_name = _find_employee_name(msgs) or _find_employee_name(messages)
                chats = _group_into_chats(msgs, known_employees, date, chat_id_prefix=dialog_id, use_time_boundary=False)
                for c in chats:
                    if not c.employee_name:
                        c.employee_name = emp_name
                _enrich_employee_names(chats, known_employees, block_employee)
                all_chats.extend(chats)
        else:
            chats = _group_into_chats(messages, known_employees, date, chat_id_prefix=dialog_id, use_time_boundary=False)
            _enrich_employee_names(chats, known_employees, block_employee)
            all_chats.extend(chats)

    _resolve_ambiguous_roles(all_chats, known_employees)

    return all_chats


def _resolve_ambiguous_roles(chats: List[Chat], known_employees: List[str] = None):
    if not known_employees:
        return
    for chat in chats:
        for msg in chat.messages:
            text = msg.text.strip()
            m_assign = re.search(r"автоназначен\s+на\s+оператора\s+(\S+(?:\s+\S+)?)", text, re.I)
            if m_assign:
                found = m_assign.group(1).strip()
                for emp in known_employees:
                    if found.lower() in emp.lower():
                        chat.employee_name = emp
                        break
        if not chat.employee_name:
            continue
        emp_parts = set(chat.employee_name.strip().lower().split())
        for msg in chat.messages:
            sender_parts = set(msg.sender.strip().lower().split())
            if not sender_parts:
                continue
            is_subset = sender_parts.issubset(emp_parts) and len(sender_parts) < len(emp_parts)
            if msg.role == MessageRole.CLIENT and is_subset:
                msg.role = MessageRole.EMPLOYEE
                msg.sender = chat.employee_name
            elif msg.role == MessageRole.EMPLOYEE and is_subset:
                msg.sender = chat.employee_name


def _parse_single_block(lines: List[str], known_employees: List[str]) -> List[Chat]:
    messages, matched = _parse_ts_format(lines, known_employees)

    if not matched:
        messages = []
        for line in lines:
            stripped = line.strip()
            if not stripped or _is_metadata(stripped):
                continue
            if ":" in stripped:
                parts = stripped.split(":", 1)
                sender = parts[0].strip()
                text = parts[1].strip() if len(parts) > 1 else ""
                if _is_system_message(text):
                    continue
                role = MessageRole.UNKNOWN
                if is_bot_message(sender, text):
                    role = MessageRole.BOT
                elif known_employees:
                    role = detect_role(sender, known_employees)
                messages.append(Message(
                    timestamp=None,
                    sender=sender,
                    role=role,
                    text=text
                ))

    all_senders = set()
    for msg in messages:
        if msg.role == MessageRole.EMPLOYEE:
            all_senders.add(msg.sender)

    emp_list = list(all_senders) if all_senders else known_employees or None
    date = _extract_dialog_date(lines)
    chats = _group_into_chats(messages, emp_list, date)

    return chats


def _get_local_tag(elem) -> str:
    tag = elem.tag
    if isinstance(tag, str) and "}" in tag:
        return tag.split("}")[1]
    return str(tag) if tag else ""


def parse_xml(content: bytes) -> List[Chat]:
    chats = []
    try:
        root = ET.fromstring(content)
    except ET.ParseError:
        return _parse_xml_fallback(content)

    for chat_elem in root.iter():
        tag = _get_local_tag(chat_elem)
        if tag.lower() in ("chat", "dialog", "conversation", "чат", "диалог"):
            chat = _parse_xml_chat(chat_elem)
            if chat and len(chat.messages) > 0:
                chats.append(chat)

    if not chats:
        chat = _parse_xml_flat(root)
        if chat and len(chat.messages) > 0:
            chats.append(chat)

    return chats


def _parse_xml_chat(chat_elem) -> Optional[Chat]:
    messages = []
    chat_id = chat_elem.get("id", str(uuid.uuid4())[:8])
    employee_name = chat_elem.get("employee") or chat_elem.get("employee_name") or chat_elem.get("operator") or chat_elem.get("сотрудник") or chat_elem.get("оператор")
    date = chat_elem.get("date") or chat_elem.get("datetime") or chat_elem.get("дата")

    for msg_elem in chat_elem:
        tag = _get_local_tag(msg_elem)
        if tag.lower() in ("message", "msg", "сообщение"):
            text = msg_elem.text or ""
            sender = msg_elem.get("from") or msg_elem.get("sender") or msg_elem.get("от") or msg_elem.get("name") or msg_elem.get("имя") or ""
            timestamp = msg_elem.get("time") or msg_elem.get("timestamp") or msg_elem.get("время") or msg_elem.get("datetime")
            role_str = msg_elem.get("role") or msg_elem.get("type") or msg_elem.get("роль") or msg_elem.get("тип") or ""

            role = MessageRole.UNKNOWN
            if is_bot_message(sender, text):
                role = MessageRole.BOT
            elif role_str.lower() in ("employee", "agent", "operator", "сотрудник", "оператор", "менеджер"):
                role = MessageRole.EMPLOYEE
            elif role_str.lower() in ("client", "customer", "user", "клиент", "пользователь"):
                role = MessageRole.CLIENT
            elif employee_name and sender.strip().lower() == employee_name.strip().lower():
                role = MessageRole.EMPLOYEE

            messages.append(Message(
                timestamp=timestamp,
                sender=sender,
                role=role,
                text=text.strip()
            ))

    if not messages:
        return None

    if not employee_name:
        employee_name = _find_employee_name(messages)

    return Chat(
        id=chat_id,
        employee_name=employee_name,
        date=date,
        messages=messages
    )


def _parse_xml_flat(root) -> Optional[Chat]:
    messages = []
    for elem in root.iter():
        tag = _get_local_tag(elem)
        if tag.lower() in ("message", "msg", "сообщение"):
            text = elem.text or ""
            sender = elem.get("from") or elem.get("sender") or elem.get("name") or ""
            timestamp = elem.get("time") or elem.get("timestamp")
            role_str = elem.get("role") or elem.get("type") or ""

            role = MessageRole.UNKNOWN
            if is_bot_message(sender, text):
                role = MessageRole.BOT
            elif role_str.lower() in ("employee", "agent", "operator", "сотрудник", "оператор"):
                role = MessageRole.EMPLOYEE
            elif role_str.lower() in ("client", "customer", "user", "клиент", "пользователь"):
                role = MessageRole.CLIENT

            messages.append(Message(
                timestamp=timestamp,
                sender=sender,
                role=role,
                text=text.strip()
            ))

    if not messages:
        return None

    return Chat(
        id="1",
        employee_name=_find_employee_name(messages),
        date=None,
        messages=messages
    )


def _parse_xml_fallback(content: bytes) -> List[Chat]:
    try:
        text = content.decode("utf-8", errors="ignore")
    except Exception:
        text = content.decode("latin-1", errors="ignore")
    return parse_txt(text)


def parse_file(file_path: str) -> List[Chat]:
    ext = os.path.splitext(file_path)[1].lower()
    if ext == ".txt":
        for enc in ["utf-8", "utf-8-sig", "windows-1251", "cp1251", "latin-1"]:
            try:
                with open(file_path, "r", encoding=enc) as f:
                    content = f.read()
                return parse_txt(content)
            except (UnicodeDecodeError, UnicodeError):
                continue
        raise ValueError("Не удалось прочитать файл: неизвестная кодировка")
    elif ext in (".xml",):
        with open(file_path, "rb") as f:
            content = f.read()
        return parse_xml(content)
    else:
        raise ValueError(f"Неподдерживаемый формат файла: {ext}. Используйте TXT или XML.")


def get_employees(chats: List[Chat]) -> List[str]:
    employees = set()
    for chat in chats:
        if chat.employee_name:
            employees.add(chat.employee_name)
        for msg in chat.messages:
            if msg.role == MessageRole.EMPLOYEE:
                employees.add(msg.sender)
    return sorted(employees)


def filter_chats_for_employee(chats: List[Chat], employee_name: str, max_chats: int = 0) -> List[Chat]:
    filtered = []
    emp_key = employee_name.strip().lower()

    bot_chat_ids = set()
    for chat in chats:
        if sum(1 for m in chat.messages if m.role == MessageRole.BOT) > 0:
            base_id = chat.id.rsplit("_", 1)[0]
            bot_chat_ids.add(base_id)

    for chat in chats:
        is_assigned = (
            chat.employee_name is not None
            and chat.employee_name.strip().lower() == emp_key
        )

        emp_msg_count = sum(
            1 for m in chat.messages
            if m.role == MessageRole.EMPLOYEE
            and m.sender.strip().lower() == emp_key
        )

        if not is_assigned and emp_msg_count <= 0:
            continue

        has_client = any(m.role == MessageRole.CLIENT for m in chat.messages)
        if not has_client:
            continue

        other_operators = set()
        all_text = "\n".join(m.text for m in chat.messages)
        for match in re.finditer(r'автоназначен на оператора\s+(.+?)(?:\n|$)', all_text, re.IGNORECASE):
            other_operators.add(match.group(1).strip().lower())
        for match in re.finditer(r'Оператор\s+(.+?)\s+закрыл', all_text):
            other_operators.add(match.group(1).strip().lower())

        base_id = chat.id.rsplit("_", 1)[0]
        is_from_bot_chat = base_id in bot_chat_ids

        filtered_messages = [
            m for m in chat.messages
            if m.role == MessageRole.BOT
            or (m.role == MessageRole.EMPLOYEE and m.sender.strip().lower() == emp_key)
            or (m.role == MessageRole.CLIENT and m.sender.strip().lower() not in other_operators)
        ]

        if filtered_messages:
            filtered.append(Chat(
                id=chat.id,
                employee_name=employee_name,
                date=chat.date,
                messages=filtered_messages,
                bot_heavy=is_from_bot_chat
            ))

    if max_chats > 0:
        filtered = filtered[:max_chats]

    return filtered
