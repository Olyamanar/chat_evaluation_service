import sys, os
os.chdir(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, '.')
from parser import parse_file, filter_chats_for_employee
from models import MessageRole

# Test with test_chats.txt
chats = parse_file('data/test_chats.txt')
print(f'Total chats parsed: {len(chats)}')

# Test multi-line message handling
# Create a block with continuation lines that contain ( and - prefixes
from parser import _parse_ts_format, _is_new_message

lines = [
    "[12.05.2024 10:30:15] Иван Петров (сотрудник): У нас есть несколько вариантов:",
    "- Вариант 1",
    "- Вариант 2",
    "(это важно)",
    "[12.05.2024 10:31:00] Клиент: Понял, спасибо!",
]
msgs, matched = _parse_ts_format(lines, ['Иван Петров'])
print(f'\nMulti-line test: matched={matched}, msgs={len(msgs)}')
for m in msgs:
    print(f'  [{m.role}] text={repr(m.text)}')
    lines_in_text = m.text.count('\n') + 1
    print(f'    (contains {lines_in_text} lines)')
assert len(msgs) == 2, f'Expected 2 messages, got {len(msgs)}'
assert msgs[0].text == "У нас есть несколько вариантов:\n- Вариант 1\n- Вариант 2\n(это важно)", \
    f'Multi-line text truncated: {repr(msgs[0].text)}'
print('  OK: multi-line preserved with ( and - prefixes')

# Test unmatched line appended to previous message
lines2 = [
    "[12.05.2024 10:30:00] Иван Петров (сотрудник): Здравствуйте!",
    "какой-то текст без таймштампа",
    "[12.05.2024 10:31:00] Клиент: Привет!",
]
msgs2, matched2 = _parse_ts_format(lines2, ['Иван Петров'])
print(f'\nUnmatched line test: matched={matched2}, msgs={len(msgs2)}')
for m in msgs2:
    print(f'  [{m.role}] text={repr(m.text)}')
assert len(msgs2) == 2, f'Expected 2 messages, got {len(msgs2)}'
assert 'какой-то текст без таймштампа' in msgs2[0].text, \
    f'Unmatched line not appended: {repr(msgs2[0].text)}'
print('  OK: orphan line appended to previous message')

print('\nAll tests passed!')
