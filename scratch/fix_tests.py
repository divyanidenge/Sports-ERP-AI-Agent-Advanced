import os, re

files = [os.path.join(r, f) for r, d, files in os.walk('tests') for f in files if f.endswith('.py')]
for file in files:
    with open(file, 'r', encoding='utf-8') as f:
        content = f.read()
    new_content = re.sub(r'\'time_slot\':\s*\'(\d{2}:\d{2})\s*-\s*(\d{2}:\d{2})\'', r"'start_time': '\1', 'end_time': '\2'", content)
    new_content = re.sub(r'\"time_slot\":\s*\"(\d{2}:\d{2})\s*-\s*(\d{2}:\d{2})\"', r'"start_time": "\1", "end_time": "\2"', new_content)
    new_content = re.sub(r'time_slot=\"(\d{2}:\d{2})\s*-\s*(\d{2}:\d{2})\"', r'start_time="\1", end_time="\2"', new_content)
    if new_content != content:
        with open(file, 'w', encoding='utf-8') as f:
            f.write(new_content)
        print(f'Updated {file}')
