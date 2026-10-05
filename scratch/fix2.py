import re
with open('tests/test_conversational_bug_fixes_and_rbac.py', 'r') as f:
    content = f.read()
content = re.sub(r'start_time=[\'\"]16:00[\'\"],\s*end_time=[\'\"]17:00[\'\"]', 'time_slot=\"16:00 - 17:00\"', content)
with open('tests/test_conversational_bug_fixes_and_rbac.py', 'w') as f:
    f.write(content)
