import argparse
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


def extract_text_from_pdf(path: Path, max_pages: Optional[int] = None) -> Tuple[str, Dict[str, Any]]:
    errors: List[str] = []

    try:
        from pypdf import PdfReader

        reader = PdfReader(str(path))
        page_count = len(reader.pages)
        end = page_count if max_pages is None else min(page_count, max_pages)
        parts: List[str] = []
        for i in range(end):
            parts.append(reader.pages[i].extract_text() or "")
        return "\n".join(parts).strip(), {"page_count": page_count, "library": "pypdf", "used_pages": end}
    except Exception as e:
        errors.append(f"pypdf: {e}")

    try:
        import PyPDF2

        reader = PyPDF2.PdfReader(str(path))
        page_count = len(reader.pages)
        end = page_count if max_pages is None else min(page_count, max_pages)
        parts = []
        for i in range(end):
            parts.append(reader.pages[i].extract_text() or "")
        return "\n".join(parts).strip(), {"page_count": page_count, "library": "PyPDF2", "used_pages": end}
    except Exception as e:
        errors.append(f"PyPDF2: {e}")

    try:
        import pdfplumber

        with pdfplumber.open(str(path)) as pdf:
            page_count = len(pdf.pages)
            end = page_count if max_pages is None else min(page_count, max_pages)
            parts = []
            for i in range(end):
                parts.append(pdf.pages[i].extract_text() or "")
        return "\n".join(parts).strip(), {"page_count": page_count, "library": "pdfplumber", "used_pages": end}
    except Exception as e:
        errors.append(f"pdfplumber: {e}")

    raise RuntimeError(
        "无法解析PDF。请安装以下任一库后重试：pypdf / PyPDF2 / pdfplumber。"
        + (" 解析尝试信息：" + " | ".join(errors) if errors else "")
    )


class ChatGLMClient:
    def __init__(self, api_key: Optional[str] = None, model: str = "glm-4-air"):
        self.api_key = api_key or os.environ.get("ZHIPUAI_API_KEY")
        self.model = model
        self.client = None
        try:
            from zhipuai import ZhipuAI

            if not self.api_key:
                raise ValueError("ZHIPUAI_API_KEY missing")
            self.client = ZhipuAI(api_key=self.api_key)
        except Exception:
            self.client = None

    def available(self) -> bool:
        return self.client is not None

    def chat(self, messages: List[Dict[str, str]], temperature: float = 0.2) -> str:
        if not self.client:
            raise RuntimeError("ChatGLM接口不可用：请安装zhipuai并设置ZHIPUAI_API_KEY")
        resp = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=temperature,
        )
        try:
            msg = resp.choices[0].message
            if isinstance(msg, dict):
                return msg.get("content", "") or ""
            return getattr(msg, "content", "") or ""
        except Exception:
            return ""


@dataclass
class ExtractOptions:
    max_pages: Optional[int] = None
    max_chars: int = 60000


def build_extract_messages(text: str) -> List[Dict[str, str]]:
    sys = "你是文档信息抽取助手，只输出严格JSON，不要输出任何解释文本。"
    user = (
        "从以下PDF文本中提取信息，返回JSON，字段固定如下：\n"
        "doc_title, summary, key_points[], requirements[], entities{organizations[], people[], dates[], numbers[]}\n"
        "要求：\n"
        "1) summary用中文，尽量客观，不超过200字\n"
        "2) key_points最多10条\n"
        "3) requirements只在文本中明确出现时填写\n"
        "4) 没有的信息用空字符串/空数组\n"
        "文本：\n"
        f"{text}"
    )
    return [{"role": "system", "content": sys}, {"role": "user", "content": user}]


def extract_structured_info_from_pdf(pdf_path: Path, client: ChatGLMClient, opt: ExtractOptions) -> Dict[str, Any]:
    pdf_text, meta = extract_text_from_pdf(pdf_path, max_pages=opt.max_pages)
    pdf_text = pdf_text.strip()
    if not pdf_text:
        raise RuntimeError("PDF文本为空，可能是扫描件图片PDF，需先OCR后再抽取")
    if opt.max_chars and len(pdf_text) > opt.max_chars:
        pdf_text = pdf_text[: opt.max_chars]
    messages = build_extract_messages(pdf_text)
    content = client.chat(messages, temperature=0.1)
    data = json.loads(content)
    return {
        "extracted": data,
        "source": {
            "file": str(pdf_path),
            **meta,
            "truncated_chars": opt.max_chars if opt.max_chars else None,
        },
    }


def main():
    parser = argparse.ArgumentParser(prog="pdf-agent", add_help=True)
    parser.add_argument("--pdf", type=str, required=True)
    parser.add_argument("--model", type=str, default="glm-4-air")
    parser.add_argument("--max-pages", type=int, default=15)
    parser.add_argument("--max-chars", type=int, default=60000)
    args = parser.parse_args()

    pdf_path = Path(args.pdf)
    if not pdf_path.exists():
        raise SystemExit(f"文件不存在：{pdf_path}")
    if pdf_path.suffix.lower() != ".pdf":
        raise SystemExit("只支持PDF文件")

    client = ChatGLMClient(model=args.model)
    if not client.available():
        raise SystemExit("ChatGLM接口不可用：请安装zhipuai并设置ZHIPUAI_API_KEY")

    opt = ExtractOptions(
        max_pages=args.max_pages if args.max_pages and args.max_pages > 0 else None,
        max_chars=max(0, int(args.max_chars)),
    )
    result = extract_structured_info_from_pdf(pdf_path, client, opt)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

