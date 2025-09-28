import json


def get_json_content(content):
    json_content = content.strip()
    if json_content.startswith('```json') or json_content.startswith('```'):
        lines = json_content.split('\n')
        json_lines = []
        in_json_block = False
        for line in lines:
            line_stripped = line.strip()
            if line_stripped in ['```json', '```']:
                if not in_json_block:
                    in_json_block = True
                else:
                    break
                continue
            elif in_json_block:
                json_lines.append(line)
        json_content = '\n'.join(json_lines)
    parsed_json = json.loads(json_content)
    return parsed_json