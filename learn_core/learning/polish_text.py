"""Pure protection rules ported from learning_ext/text_polish/service.py; no legacy imports."""
from collections import Counter
import re
import uuid

_PROTECTED = re.compile(
    r"(?P<fenced>^[ \t]{0,3}(?P<fence>`{3,}|~{3,})[^\r\n]*"
    r"(?:\r?\n[\s\S]*?(?:^[ \t]{0,3}(?P=fence)[ \t]*(?=\r?$)|\Z)|\Z))"
    r"|(?P<inline>(?P<ticks>`+)[^\r\n]*?(?P=ticks))"
    r"|(?P<url>(?:[A-Za-z][A-Za-z0-9+.-]*://|mailto:|www\.)"
    r"[^\s<>\"`，。！？；、（）【】]+)"
    r"|(?P<mention>(?<![\w@])@[^\s@,，。！？!?;；:<>\"()\[\]{}]+)",
    re.MULTILINE | re.IGNORECASE,
)

_NUMBER = re.compile(r"[+-]?\d+(?:[.,]\d+)*(?:[eE][+-]?\d+)?(?:%|％)?")

_PLACEHOLDER = re.compile(r"⟦KEEP_[^⟧\r\n]*⟧")

def _protected_spans(text: str):
    for match in _PROTECTED.finditer(text):
        value = match.group()
        if match.group("url"):
            value = value.rstrip(".,;:!?")
            for closing, opening in ((")", "("), ("]", "["), ("}", "{")):
                while value.endswith(closing) and value.count(closing) > value.count(opening):
                    value = value[:-1]
        yield match.start(), match.start() + len(value), value

def _protect(text: str) -> tuple[str, list[tuple[str, str]]]:
    nonce = uuid.uuid4().hex
    while nonce in text:
        nonce = uuid.uuid4().hex
    spans = []
    pieces = []
    position = 0
    for index, (start, end, value) in enumerate(_protected_spans(text)):
        token = f"⟦KEEP_{nonce}_{index}⟧"
        pieces.extend((text[position:start], token))
        spans.append((token, value))
        position = end
    pieces.append(text[position:])
    return "".join(pieces), spans

def _restore(text: str, spans: list[tuple[str, str]]) -> str | None:
    positions = []
    for token, _ in spans:
        if text.count(token) != 1:
            return None
        positions.append(text.index(token))
    if positions != sorted(positions):
        return None
    for token, value in spans:
        text = text.replace(token, value)
    return text


def validate_output(source: str, output: str, spans: list[tuple[str, str]], kind: str) -> str:
    if not isinstance(output, str) or not output.strip() or len(output) > 40000:
        raise ValueError('模型未返回有效的润色结果，原文已保留')
    restored = _restore(output.strip(), spans)
    if restored is None or len(restored) > min(16000, max(len(source) * 2, len(source) + 300)):
        raise ValueError('润色结果改动了受保护内容或过长，原文已保留')
    if ([value for _, _, value in _protected_spans(source)] != [value for _, _, value in _protected_spans(restored)]
        or Counter(_NUMBER.findall(source)) != Counter(_NUMBER.findall(restored))
        or Counter(_PLACEHOLDER.findall(source)) != Counter(_PLACEHOLDER.findall(restored))):
        raise ValueError('润色结果改动了代码、链接或数字，原文已保留')
    if kind == 'question' and any(m in source for m in '?？') and not any(m in restored for m in '?？'):
        raise ValueError('润色结果未保留原问题，原文已保留')
    return source if restored == source.strip() else restored
