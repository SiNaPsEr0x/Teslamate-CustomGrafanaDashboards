"""PO catalog overlay and strict Italian plural validation, without dependencies."""
import json
import re


def entries(text):
    output = []
    for block in re.split(r"\n\s*\n", text):
        if not block.strip() or block.lstrip().startswith("#~"):
            continue
        fields = {}
        active = None
        for line in block.splitlines():
            m = re.match(r'(msgctxt|msgid_plural|msgid|msgstr(?:\[\d+\])?)\s+(".*")$', line)
            if m:
                active = m[1]
                fields[active] = json.loads(m[2])
            elif line.startswith('"') and active:
                fields[active] += json.loads(line)
            elif not line.startswith('#'):
                active = None
        if 'msgid' in fields:
            output.append((block, fields))
    return output


def overlay(base, translated):
    target = {(f.get('msgctxt'), f['msgid']): f for _, f in entries(translated)}
    out = []
    for block, fields in entries(base):
        patch = target.get((fields.get('msgctxt'), fields['msgid']), {})
        lines, skipping = [], False
        for line in block.splitlines():
            m = re.match(r'(msgstr(?:\[\d+\])?)\s+', line)
            if m:
                key = m[1]
                value = patch.get(key, fields.get(key, ''))
                lines.append(key + ' ' + json.dumps(value, ensure_ascii=False))
                skipping = True
            elif skipping and line.startswith('"'):
                continue
            else:
                skipping = False
                lines.append(line)
        out.append('\n'.join(lines))
    return '\n\n'.join(out) + '\n'


def validate(text):
    missing = []
    for _, field in entries(text):
        if not field['msgid']:
            continue
        required = ('msgstr[0]', 'msgstr[1]') if 'msgid_plural' in field else ('msgstr',)
        if any(not field.get(key) for key in required):
            missing.append(field['msgid'])
    if missing:
        raise ValueError('Missing Italian translations or plural forms: ' + repr(missing))
    return len(entries(text)) - 1
