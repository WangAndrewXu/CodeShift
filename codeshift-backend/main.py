from fastapi import FastAPI, UploadFile, File, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from openai import OpenAI
import os
import re

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ConvertRequest(BaseModel):
    code: str
    filename: str
    source_language: str
    target_language: str
    allow_ai_fallback: bool = True


def normalize_language(language: str) -> str:
    value = language.strip().lower()

    if value in {"python", "py"}:
        return "python"
    if value in {"c++", "cpp", "cc", "cxx"}:
        return "cpp"
    if value in {"java"}:
        return "java"
    if value in {"javascript", "js"}:
        return "javascript"

    return value


def detect_language_from_filename(filename: str) -> str:
    lower_name = filename.lower()

    if lower_name.endswith(".py"):
        return "python"
    if lower_name.endswith(".cpp") or lower_name.endswith(".cc") or lower_name.endswith(".cxx"):
        return "cpp"
    if lower_name.endswith(".java"):
        return "java"
    if lower_name.endswith(".js"):
        return "javascript"

    return "unknown"


def get_ai_client(api_key: str | None = None, base_url: str | None = None):
    final_key = api_key or os.getenv("OPENAI_API_KEY")
    final_base_url = base_url or os.getenv("OPENAI_BASE_URL")

    if not final_key:
        return None

    kwargs = {"api_key": final_key}
    if final_base_url:
        kwargs["base_url"] = final_base_url

    return OpenAI(**kwargs)


def test_ai_connection(
    api_key: str | None = None,
    base_url: str | None = None,
    model: str | None = None,
    provider_name: str | None = None
):
    client = get_ai_client(api_key, base_url)
    if client is None:
        return False, "No API key was provided."

    final_model = model or os.getenv("OPENAI_MODEL") or "gpt-5.4-mini"
    provider_label = provider_name or "AI provider"

    try:
        response = client.responses.create(
            model=final_model,
            input="Reply with exactly the single word: OK"
        )

        text = response.output_text.strip()
        if not text:
            return False, f"{provider_label} returned an empty response during test."

        return True, f"Connection successful via {provider_label} using model {final_model}."
    except Exception as e:
        return False, f"Connection failed via {provider_label}: {str(e)}"


def ai_convert_fallback(
    code: str,
    source_language: str,
    target_language: str,
    api_key: str | None = None,
    base_url: str | None = None,
    model: str | None = None,
    provider_name: str | None = None
):
    client = get_ai_client(api_key, base_url)
    if client is None:
        return None, "Rule-based conversion failed, and AI fallback is unavailable because no API key was provided."

    final_model = model or os.getenv("OPENAI_MODEL") or "gpt-5.4-mini"
    provider_label = provider_name or "AI provider"

    prompt = f"""
You are a code translation assistant.

Convert the following code from {source_language} to {target_language}.

Requirements:
1. Return ONLY the converted code.
2. Preserve the intent of the original program.
3. If the code has small syntax issues, repair obvious ones if possible.
4. Keep the output simple and runnable when reasonable.
5. Do not include markdown fences.
6. Do not include explanations.

Source code:
{code}
"""

    try:
        response = client.responses.create(
            model=final_model,
            input=prompt
        )

        converted = response.output_text.strip()

        if not converted:
            return None, f"{provider_label} returned an empty result."

        return converted, f"AI fallback used via {provider_label} with model {final_model}"
    except Exception as e:
        return None, f"AI fallback failed via {provider_label}: {str(e)}"


def extract_python_names(code: str):
    variables = dict(re.findall(r'(\w+)\s*=\s*"([^"]+)"', code))
    result = []

    direct_calls = re.findall(r'print\s*\(\s*greet\("([^"]+)"\)\s*\)', code)
    result.extend(direct_calls)

    variable_calls = re.findall(r'print\s*\(\s*greet\((\w+)\)\s*\)', code)
    for var in variable_calls:
        if var in variables:
            result.append(variables[var])

    return result


def extract_cpp_names(code: str):
    variables = dict(
        re.findall(r'(?:std::string|string)\s+(\w+)\s*=\s*"([^"]+)"\s*;', code)
    )
    result = []

    direct_calls = re.findall(
        r'(?:std::)?cout\s*<<\s*greet\("([^"]+)"\)\s*(?:<<\s*(?:std::)?endl)?\s*;',
        code
    )
    result.extend(direct_calls)

    variable_calls = re.findall(
        r'(?:std::)?cout\s*<<\s*greet\((\w+)\)\s*(?:<<\s*(?:std::)?endl)?\s*;',
        code
    )
    for var in variable_calls:
        if var in variables:
            result.append(variables[var])

    return result


def extract_java_names(code: str):
    variables = dict(
        re.findall(r'String\s+(\w+)\s*=\s*"([^"]+)"\s*;', code)
    )
    result = []

    direct_calls = re.findall(
        r'System\.out\.println\s*\(\s*greet\("([^"]+)"\)\s*\)\s*;',
        code
    )
    result.extend(direct_calls)

    variable_calls = re.findall(
        r'System\.out\.println\s*\(\s*greet\((\w+)\)\s*\)\s*;',
        code
    )
    for var in variable_calls:
        if var in variables:
            result.append(variables[var])

    return result


def extract_javascript_names(code: str):
    variables = dict(
        re.findall(r'(?:const|let|var)\s+(\w+)\s*=\s*"([^"]+)"\s*;', code)
    )
    result = []

    direct_calls = re.findall(
        r'console\.log\s*\(\s*greet\("([^"]+)"\)\s*\)\s*;',
        code
    )
    result.extend(direct_calls)

    variable_calls = re.findall(
        r'console\.log\s*\(\s*greet\((\w+)\)\s*\)\s*;',
        code
    )
    for var in variable_calls:
        if var in variables:
            result.append(variables[var])

    return result


def extract_names(code: str, language: str):
    if language == "python":
        return extract_python_names(code)
    if language == "cpp":
        return extract_cpp_names(code)
    if language == "java":
        return extract_java_names(code)
    if language == "javascript":
        return extract_javascript_names(code)
    return []


def render_python(names):
    print_lines = "\n".join([f'print(greet("{name}"))' for name in names])
    return f'''def greet(name):
    return f"Hello, {{name}}!"

{print_lines}
'''


def render_cpp(names):
    cout_lines = "\n".join(
        [f'    cout << greet("{name}") << endl;' for name in names])
    return f"""#include <iostream>
#include <string>
using namespace std;

string greet(string name) {{
    return "Hello, " + name + "!";
}}

int main() {{
{cout_lines}
    return 0;
}}
"""


def render_java(names):
    print_lines = "\n".join(
        [f'        System.out.println(greet("{name}"));' for name in names]
    )
    return f"""public class Main {{
    public static String greet(String name) {{
        return "Hello, " + name + "!";
    }}

    public static void main(String[] args) {{
{print_lines}
    }}
}}
"""


def render_javascript(names):
    log_lines = "\n".join([f'console.log(greet("{name}"));' for name in names])
    return f"""function greet(name) {{
  return `Hello, ${{name}}!`;
}}

{log_lines}
"""


def render_code(names, language: str):
    if language == "python":
        return render_python(names)
    if language == "cpp":
        return render_cpp(names)
    if language == "java":
        return render_java(names)
    if language == "javascript":
        return render_javascript(names)
    return None


@app.get("/")
async def root():
    return {"message": "CodeShift backend is running"}


@app.post("/load-file")
async def load_file(file: UploadFile = File(...)):
    try:
        raw = await file.read()
        content = raw.decode("utf-8")
        language = detect_language_from_filename(file.filename)

        return {
            "success": True,
            "filename": file.filename,
            "content": content,
            "language": language
        }
    except UnicodeDecodeError:
        return {
            "success": False,
            "message": "This file is not valid UTF-8 text."
        }
    except Exception as e:
        return {
            "success": False,
            "message": f"Failed to load file: {str(e)}"
        }


@app.post("/test-provider")
async def test_provider(
    x_api_key: str | None = Header(default=None),
    x_base_url: str | None = Header(default=None),
    x_model: str | None = Header(default=None),
    x_provider_name: str | None = Header(default=None)
):
    success, message = test_ai_connection(
        api_key=x_api_key,
        base_url=x_base_url,
        model=x_model,
        provider_name=x_provider_name,
    )

    return {
        "success": success,
        "message": message,
        "provider_name": x_provider_name or "",
        "model": x_model or "",
        "base_url": x_base_url or "",
    }


@app.post("/convert")
async def convert_code(
    data: ConvertRequest,
    x_api_key: str | None = Header(default=None),
    x_base_url: str | None = Header(default=None),
    x_model: str | None = Header(default=None),
    x_provider_name: str | None = Header(default=None)
):
    source_language = normalize_language(data.source_language)
    target_language = normalize_language(data.target_language)

    names = extract_names(data.code, source_language)

    if names:
        converted = render_code(names, target_language)

        if converted is not None:
            return {
                "success": True,
                "converted_code": converted,
                "message": f"Rule-based conversion used for {source_language} -> {target_language}",
                "source_language": source_language,
                "target_language": target_language,
                "filename": data.filename,
                "rule": f"Rule-based conversion used for {source_language} -> {target_language}"
            }

    if not data.allow_ai_fallback:
        return {
            "success": False,
            "converted_code": "",
            "message": "No custom rule matched, and AI fallback is currently turned off.",
            "rule": f"Rule-only mode: no custom rule matched for {source_language} -> {target_language}"
        }

    converted, ai_message = ai_convert_fallback(
        data.code,
        source_language,
        target_language,
        api_key=x_api_key,
        base_url=x_base_url,
        model=x_model,
        provider_name=x_provider_name,
    )

    if converted is None:
        return {
            "success": False,
            "converted_code": "",
            "message": ai_message,
            "rule": f"No custom rule matched for {source_language} -> {target_language}"
        }

    return {
        "success": True,
        "converted_code": converted,
        "message": ai_message,
        "source_language": source_language,
        "target_language": target_language,
        "filename": data.filename,
        "rule": ai_message
    }
