import re

from .schemas import PrintOperation, RuleProgram

RULE_SUPPORT_SUMMARY = (
    "Current rule-based support covers simple string variables, direct print/log "
    "statements, basic greet(...) examples, and simple string concatenation."
)

SUPPORTED_RULE_PATTERNS = [
    "simple string variables",
    "direct print/log statements",
    "basic greet(...) examples",
    "simple string concatenation",
]

SUPPORTED_LANGUAGES = ["python", "cpp", "java", "javascript"]


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

