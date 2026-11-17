"""Bounded text extraction in the IO worker. No desktop apps or shell commands."""
import io
from pathlib import Path
from zipfile import ZipFile, BadZipFile
from xml.etree import ElementTree

EXTENSIONS = {'.txt', '.md', '.pdf', '.docx'}
MAX_TEXT = 1_000_000


def extract_text(data: bytes, name: str) -> str:
    ext = Path(name).suffix.lower()
    if ext not in EXTENSIONS:
        raise ValueError('当前支持 TXT、Markdown、PDF 和 DOCX 文件')
    if ext in {'.txt', '.md'}:
        if b'\x00' in data[:4096]:
            raise ValueError('文本编码无法识别，请另存为 UTF-8 后上传')
        try:
            result = data.decode('utf-8-sig')
        except UnicodeDecodeError as exc:
            raise ValueError('文本编码无法识别，请另存为 UTF-8 后上传') from exc
    elif ext == '.pdf':
        from pypdf import PdfReader
        try:
            reader = PdfReader(io.BytesIO(data))
            if reader.is_encrypted:
                raise ValueError('请先移除 PDF 密码后上传')
            if len(reader.pages) > 200:
                raise ValueError('试用版每份 PDF 最多 200 页，请拆分后上传')
            parts = []
            size = 0
            for page in reader.pages:
                content = page.extract_text() or ''
                size += len(content)
                if size > MAX_TEXT:
                    raise ValueError('文档文字过多，请拆分后上传')
                parts.append(content)
            result = '\n\n'.join(parts)
        except ValueError:
            raise
        except Exception as exc:
            raise ValueError('PDF 无法解析，请检查文件是否完整') from exc
    else:
        try:
            with ZipFile(io.BytesIO(data)) as package:
                entry = package.getinfo('word/document.xml')
                if entry.file_size > 10 * 1024 * 1024:
                    raise ValueError('文档文字过多，请拆分后上传')
                root = ElementTree.fromstring(package.read(entry))
                ns = {'w':'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
                result = '\n'.join(''.join(p.itertext()) for p in root.findall('.//w:p', ns))
        except (BadZipFile, KeyError, ElementTree.ParseError, RuntimeError) as exc:
            raise ValueError('DOCX 无法解析，请检查文件是否完整') from exc
    if len(result) > MAX_TEXT:
        raise ValueError('文档文字过多，请拆分后上传')
    if not result.strip():
        raise ValueError('未提取到文字；扫描 PDF 请先识别文字后上传')
    return result.strip()
