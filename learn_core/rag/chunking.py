"""把长文档切成检索块。

切分规则尽量简单可解释：先按空行分段，段落超长再按句末标点切，
最后按 ``max_chars`` 硬切。相邻块保留 ``overlap`` 个字符，
避免答案正好跨在切口上。
"""

from __future__ import annotations

import re

_SENTENCE_END = re.compile(r"(?<=[。！？!?；;])\s*")
_PARAGRAPH = re.compile(r"\n\s*\n")


def split_text(text: str, max_chars: int = 800, overlap: int = 80) -> list[str]:
    if max_chars <= 0:
        raise ValueError("max_chars must be positive")
    if overlap < 0 or overlap >= max_chars:
        raise ValueError("overlap must be in [0, max_chars)")

    text = text.replace("\r\n", "\n").strip()
    if not text:
        return []

    units: list[str] = []
    for para in _PARAGRAPH.split(text):
        para = para.strip()
        if not para:
            continue
        if len(para) <= max_chars:
            units.append(para)
            continue
        buf = ""
        for sentence in _SENTENCE_END.split(para):
            sentence = sentence.strip()
            if not sentence:
                continue
            if len(sentence) > max_chars:
                if buf:
                    units.append(buf)
                    buf = ""
                for i in range(0, len(sentence), max_chars):
                    units.append(sentence[i : i + max_chars])
                continue
            if len(buf) + len(sentence) + 1 > max_chars:
                units.append(buf)
                buf = sentence
            else:
                buf = f"{buf} {sentence}".strip()
        if buf:
            units.append(buf)

    chunks: list[str] = []
    current = ""
    for unit in units:
        if not current:
            current = unit
        elif len(current) + len(unit) + 2 <= max_chars:
            current = f"{current}\n\n{unit}"
        else:
            chunks.append(current)
            tail = current[-overlap:] if overlap else ""
            room = max_chars - len(unit) - 2
            if room <= 0:
                tail = ""
            elif len(tail) > room:
                tail = tail[-room:]
            current = f"{tail}\n\n{unit}" if tail else unit
    if current:
        chunks.append(current)
    return chunks


def tokenize_for_tsv(text: str) -> str:
    """写 ``tsvector('simple')`` 用的分词串。

    中文没有空格，Postgres 的 simple 字典会把整句当一个词。
    jieba 可用时按词切；不可用时退化为「单字 + 原句」，
    至少保证单字能命中。
    """
    try:
        import jieba  # type: ignore

        tokens = [t for t in jieba.cut_for_search(text) if t.strip()]
    except Exception:  # pragma: no cover - jieba 是可选的
        tokens = list(text)
    return " ".join(tokens)
