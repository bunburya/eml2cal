#!/usr/bin/env python

import sys
import re

sensitive_terms_file = sys.argv[1]
file_to_redact = sys.argv[2]


def redacted_text(to_redact: str) -> str:
    if to_redact.isdigit():
        c = '0'
    else:
        c = 'X'
    return c * len(to_redact)


with open(sensitive_terms_file) as f:
    sensitive_terms = f.readlines()


with open(file_to_redact) as f:
    content = f.read()


for t_raw in sensitive_terms:
    t = t_raw.strip()
    if not t:
        continue
    pattern = rf"\b{t}\b"
    content = re.sub(pattern, redacted_text(t), content, flags=re.IGNORECASE)

print(content)

