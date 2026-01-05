import argparse
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple         
from zhipuai import ZhipuAI


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
        "无法解析PDF。请安装以下任一库后重试:pypdf / PyPDF2 / pdfplumber。"
        + (" 解析尝试信息：" + " | ".join(errors) if errors else "")
    )


class ChatGLMClient:
    def __init__(self, api_key: Optional[str] = None, model: str = "glm-4-air"):
        self.api_key = api_key or os.environ.get("ZHIPUAI_API_KEY")
        self.model = model
        self.client = None
        try:
            if not self.api_key:
                raise ValueError("ZHIPUAI_API_KEY missing")
            self.client = ZhipuAI(api_key=self.api_key)
        except Exception:
            self.client = None

    def available(self) -> bool:
        return self.client is not None

    def chat(self, messages: List[Dict[str, str]], temperature: float = 0.2) -> str:
        if not self.client:
            raise RuntimeError("ChatGLM接口不可用:请安装zhipuai并设置ZHIPUAI_API_KEY")
        resp = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=temperature,
        )
        try:
            msg = resp.choices[0].message
            content = None
            if isinstance(msg, dict):
                content = msg.get("content", None)
            else:
                content = getattr(msg, "content", None)
            if isinstance(content, list):
                parts = []
                for it in content:
                    t = None
                    if isinstance(it, dict):
                        t = it.get("text", None) or it.get("content", None)
                    elif isinstance(it, str):
                        t = it
                    if t:
                        parts.append(str(t))
                return "\n".join(parts)
            if isinstance(content, str):
                return content
            return str(content or "")
        except Exception:
            return ""


@dataclass
class ExtractOptions:
    max_pages: Optional[int] = None
    max_chars: int = 60000



def build_extract_messages(text: str) -> List[Dict[str, str]]:
    system_prompt = """你是一名电力系统行业专家,具有10年以上输变电工程设计与运维经验。
熟悉国家电网、电力行业相关规范与技术标准。

你的任务是：从给定的电力行业文档中，提取结构化工程信息。

【强制规则】
1. 必须严格按照给定的 JSON 结构返回结果，不得新增、删除或重命名任何字段
2. 仅当文档中“明确出现”对应信息时才填写
3. 文档中未出现或无法确定的信息，必须填写 null
4. 严禁主观推断、猜测或补全
5. 只输出 JSON,不得包含任何解释性文字
6. 不要使用 Markdown,不要使用 ``` 包裹
7. 即使未提取到任何有效信息，也必须返回完整 JSON 结构
"""

    user_prompt = f"""请从以下 PDF 文本中提取电力工程相关信息。

【输出要求】
- 输出必须是一个合法的 JSON 对象
- JSON 结构必须与下方【JSON 模板】完全一致
- 不得新增字段、不得删除字段、不得修改字段名称
- 所有未明确出现的信息统一填写 null
- 数值保持原始单位，不进行换算
- 文本中的符号、角度、单位需如实保留

【JSON 模板】
<此处放完整 JSON 模板，不得省略>

【PDF 文本】
{text}
"""

    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]


def extract_structured_info_from_pdf(pdf_path: Path, client: ChatGLMClient, opt: ExtractOptions) -> Dict[str, Any]:
    pdf_text, meta = extract_text_from_pdf(pdf_path, max_pages=opt.max_pages)
    pdf_text = pdf_text.strip()
    if not pdf_text:
        raise RuntimeError("PDF文本为空,可能是扫描件图片PDF,需先OCR后再抽取")
    if opt.max_chars and len(pdf_text) > opt.max_chars:
        pdf_text = pdf_text[: opt.max_chars]
    messages = build_extract_messages(pdf_text)
    content = client.chat(messages, temperature=0.1)
    def _try_json(s: str):
        try:
            return json.loads(s)
        except Exception:
            pass
        if "```" in s:
            parts = s.split("```")
            for p in parts:
                p = p.strip()
                if p.startswith("{") and p.endswith("}"):
                    try:
                        return json.loads(p)
                    except Exception:
                        continue
        i = s.find("{")
        if i != -1:
            depth = 0
            for j in range(i, len(s)):
                ch = s[j]
                if ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
                    if depth == 0:
                        candidate = s[i : j + 1]
                        try:
                            return json.loads(candidate)
                        except Exception:
                            break
        raise RuntimeError("模型未返回合法JSON，请重试或缩短PDF内容")
    if not content or not content.strip():
        raise RuntimeError("模型输出为空，请检查API Key或稍后重试")
    data = _try_json(content.strip())
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
    parser.add_argument("--max-pages", type=int, default=20)
    parser.add_argument("--max-chars", type=int, default=80000)
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
