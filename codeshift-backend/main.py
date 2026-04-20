import os
import re
from dataclasses import dataclass
from typing import cast

from fastapi import FastAPI, File, Header, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from openai import OpenAI
from pydantic import BaseModel

app = FastAPI()


def get_allowed_origins():
    raw = os.getenv("CODESHIFT_ALLOWED_ORIGINS", "").strip()
    if raw:
        return [origin.strip() for origin in raw.split(",") if origin.strip()]

    return [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_allowed_origins(),
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


@dataclass
class PrintOperation:
    kind: str
    value: str


@dataclass
class RuleProgram:
    variables: list[tuple[str, str]]
    outputs: list[PrintOperation]


RULE_SUPPORT_SUMMARY = (
    "Current rule-based support covers simple string variables, direct print/log "
    "statements, basic greet(...) examples, and simple string concatenation."
)


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

    return OpenAI(**cast(dict[str, str], kwargs))


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


def extract_string_variables(code: str, language: str):
    patterns = {
        "python": r'(\w+)\s*=\s*"([^"]*)"',
        "cpp": r'(?:std::string|string)\s+(\w+)\s*=\s*"([^"]*)"\s*;',
        "java": r'String\s+(\w+)\s*=\s*"([^"]*)"\s*;',
        "javascript": r'(?:const|let|var)\s+(\w+)\s*=\s*"([^"]*)"\s*;',
    }
    pattern = patterns.get(language)
    if pattern is None:
        return []

    return [(name, value) for name, value in re.findall(pattern, code)]


def parse_concat_expression(
    expression: str,
    variables: dict[str, str],
    separator_pattern: str,
):
    parts = [part.strip() for part in re.split(separator_pattern, expression)]
    if len(parts) < 2:
        return None

    resolved_parts = []
    for part in parts:
        literal_match = re.fullmatch(r'"([^"]*)"', part)
        if literal_match:
            resolved_parts.append(literal_match.group(1))
            continue

        variable_match = re.fullmatch(r'(\w+)', part)
        if variable_match and variable_match.group(1) in variables:
            resolved_parts.append(variables[variable_match.group(1)])
            continue

        return None

    return PrintOperation("literal", "".join(resolved_parts))


def parse_print_expression(expression: str, variables: dict[str, str], language: str):
    value = expression.strip()
    literal_match = re.fullmatch(r'"([^"]*)"', value)
    if literal_match:
        return PrintOperation("literal", literal_match.group(1))

    greet_literal_match = re.fullmatch(r'greet\("([^"]*)"\)', value)
    if greet_literal_match:
        return PrintOperation("greet_literal", greet_literal_match.group(1))

    variable_match = re.fullmatch(r'(\w+)', value)
    if variable_match and variable_match.group(1) in variables:
        return PrintOperation("variable", variable_match.group(1))

    greet_variable_match = re.fullmatch(r'greet\((\w+)\)', value)
    if greet_variable_match and greet_variable_match.group(1) in variables:
        return PrintOperation("greet_variable", greet_variable_match.group(1))

    if language in {"python", "java", "javascript"}:
        concatenated = parse_concat_expression(value, variables, r"\s*\+\s*")
        if concatenated is not None:
            return concatenated

    if language == "cpp":
        concatenated = parse_concat_expression(value, variables, r"\s*<<\s*")
        if concatenated is not None:
            return concatenated

    return None


def extract_print_operations(code: str, language: str, variables: dict[str, str]):
    patterns = {
        "python": r'print\s*\(\s*(.*?)\s*\)',
        "cpp": r'(?:std::)?cout\s*<<\s*(.*?)\s*(?:<<\s*(?:std::)?endl)?\s*;',
        "java": r'System\.out\.println\s*\(\s*(.*?)\s*\)\s*;',
        "javascript": r'console\.log\s*\(\s*(.*?)\s*\)\s*;',
    }
    pattern = patterns.get(language)
    if pattern is None:
        return None

    outputs = []
    matches = list(re.finditer(pattern, code))
    if not matches:
        return []

    for match in matches:
        operation = parse_print_expression(match.group(1), variables, language)
        if operation is None:
            return None
        outputs.append(operation)

    return outputs


def extract_rule_program(code: str, language: str):
    variable_pairs = extract_string_variables(code, language)
    variables = {name: value for name, value in variable_pairs}
    outputs = extract_print_operations(code, language, variables)

    if outputs is None or not outputs:
        return None

    referenced_variables = {
        operation.value
        for operation in outputs
        if operation.kind in {"variable", "greet_variable"}
    }
    kept_variables = [
        (name, value) for name, value in variable_pairs if name in referenced_variables
    ]

    return RuleProgram(variables=kept_variables, outputs=outputs)


def uses_greet(program: RuleProgram):
    return any(
        operation.kind in {"greet_literal", "greet_variable"}
        for operation in program.outputs
    )


def render_python(program: RuleProgram):
    variable_lines = "\n".join(
        [f'{name} = "{value}"' for name, value in program.variables]
    )
    print_lines = []
    for operation in program.outputs:
        if operation.kind == "literal":
            print_lines.append(f'print("{operation.value}")')
        elif operation.kind == "variable":
            print_lines.append(f"print({operation.value})")
        elif operation.kind == "greet_literal":
            print_lines.append(f'print(greet("{operation.value}"))')
        elif operation.kind == "greet_variable":
            print_lines.append(f"print(greet({operation.value}))")

    sections = []
    if uses_greet(program):
        sections.append('def greet(name):\n    return f"Hello, {name}!"')
    if variable_lines:
        sections.append(variable_lines)
    sections.append("\n".join(print_lines))
    return "\n\n".join(section for section in sections if section) + "\n"


def render_cpp(program: RuleProgram):
    variable_lines = "\n".join(
        [f'    string {name} = "{value}";' for name, value in program.variables]
    )
    cout_lines = []
    for operation in program.outputs:
        if operation.kind == "literal":
            cout_lines.append(f'    cout << "{operation.value}" << endl;')
        elif operation.kind == "variable":
            cout_lines.append(f"    cout << {operation.value} << endl;")
        elif operation.kind == "greet_literal":
            cout_lines.append(f'    cout << greet("{operation.value}") << endl;')
        elif operation.kind == "greet_variable":
            cout_lines.append(f"    cout << greet({operation.value}) << endl;")

    greet_section = ""
    if uses_greet(program):
        greet_section = """
string greet(string name) {
    return "Hello, " + name + "!";
}

"""

    main_body_parts = [section for section in [variable_lines, "\n".join(cout_lines)] if section]
    main_body = "\n".join(main_body_parts)
    if main_body:
        main_body += "\n"

    return f"""#include <iostream>
#include <string>
using namespace std;

{greet_section}int main() {{
{main_body}    return 0;
}}
"""


def render_java(program: RuleProgram):
    variable_lines = "\n".join(
        [f'        String {name} = "{value}";' for name, value in program.variables]
    )
    print_lines = []
    for operation in program.outputs:
        if operation.kind == "literal":
            print_lines.append(f'        System.out.println("{operation.value}");')
        elif operation.kind == "variable":
            print_lines.append(f"        System.out.println({operation.value});")
        elif operation.kind == "greet_literal":
            print_lines.append(f'        System.out.println(greet("{operation.value}"));')
        elif operation.kind == "greet_variable":
            print_lines.append(f"        System.out.println(greet({operation.value}));")

    greet_section = ""
    if uses_greet(program):
        greet_section = """    public static String greet(String name) {
        return "Hello, " + name + "!";
    }

"""

    main_body_parts = [section for section in [variable_lines, "\n".join(print_lines)] if section]
    main_body = "\n".join(main_body_parts)
    if main_body:
        main_body += "\n"

    return f"""public class Main {{
{greet_section}    public static void main(String[] args) {{
{main_body}    }}
}}
"""


def render_javascript(program: RuleProgram):
    variable_lines = "\n".join(
        [f'const {name} = "{value}";' for name, value in program.variables]
    )
    log_lines = []
    for operation in program.outputs:
        if operation.kind == "literal":
            log_lines.append(f'console.log("{operation.value}");')
        elif operation.kind == "variable":
            log_lines.append(f"console.log({operation.value});")
        elif operation.kind == "greet_literal":
            log_lines.append(f'console.log(greet("{operation.value}"));')
        elif operation.kind == "greet_variable":
            log_lines.append(f"console.log(greet({operation.value}));")

    greet_section = ""
    if uses_greet(program):
        greet_section = """function greet(name) {
  return `Hello, ${name}!`;
}

"""

    sections = [greet_section.strip(), variable_lines, "\n".join(log_lines)]
    return "\n\n".join(section for section in sections if section) + "\n"


def render_code(program: RuleProgram, language: str):
    if language == "python":
        return render_python(program)
    if language == "cpp":
        return render_cpp(program)
    if language == "java":
        return render_java(program)
    if language == "javascript":
        return render_javascript(program)
    return None


@app.get("/")
async def root():
    return {
        "message": "CodeShift backend is running",
        "allowed_origins": get_allowed_origins(),
    }


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

    program = extract_rule_program(data.code, source_language)

    if program:
        converted = render_code(program, target_language)

        if converted is not None:
            return {
                "success": True,
                "converted_code": converted,
                "message": f"Rule-based conversion used for {source_language} -> {target_language}",
                "source_language": source_language,
                "target_language": target_language,
                "filename": data.filename,
                "rule": RULE_SUPPORT_SUMMARY
            }

    if not data.allow_ai_fallback:
        return {
            "success": False,
            "converted_code": "",
            "message": (
                "No lightweight rule matched this code, and AI fallback is turned off. "
                "Try a simpler print/log example or enable AI fallback."
            ),
            "rule": (
                f"Rule-only mode: no rule matched for {source_language} -> {target_language}. "
                + RULE_SUPPORT_SUMMARY
            )
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
            "rule": (
                f"No lightweight rule matched for {source_language} -> {target_language}. "
                + RULE_SUPPORT_SUMMARY
            )
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
