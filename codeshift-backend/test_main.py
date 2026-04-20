import json
import os
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.api import app
from app.rule_engine import extract_rule_program, render_code
from app.schemas import PrintOperation, RuleProgram


class RuleProgramTests(unittest.TestCase):
    def test_extracts_python_string_variable_and_print(self):
        program = extract_rule_program(
            'name = "Alice"\nprint(name)\nprint("Done")\n',
            "python",
        )

        self.assertIsNotNone(program)
        self.assertEqual(program.variables, [("name", "Alice")])
        self.assertEqual(
            [(item.kind, item.value) for item in program.outputs],
            [("variable", "name"), ("literal", "Done")],
        )

    def test_extracts_javascript_greet_call(self):
        program = extract_rule_program(
            'const name = "Alice";\nconsole.log(greet(name));\n',
            "javascript",
        )

        self.assertIsNotNone(program)
        self.assertEqual(
            [(item.kind, item.value) for item in program.outputs],
            [("greet_variable", "name")],
        )

    def test_extracts_python_string_concatenation(self):
        program = extract_rule_program(
            'name = "Alice"\nprint("Hello, " + name)\n',
            "python",
        )

        self.assertIsNotNone(program)
        self.assertEqual(
            [(item.kind, item.value) for item in program.outputs],
            [("literal", "Hello, Alice")],
        )

    def test_rejects_unhandled_print_expression(self):
        program = extract_rule_program(
            'print("Hello, " + get_name())\n',
            "python",
        )

        self.assertIsNone(program)

    def test_renders_java_program_for_simple_outputs(self):
        program = RuleProgram(
            variables=[("name", "Alice")],
            outputs=[
                PrintOperation("variable", "name"),
                PrintOperation("literal", "Done"),
            ],
        )

        rendered = render_code(program, "java")

        self.assertIn('String name = "Alice";', rendered)
        self.assertIn("System.out.println(name);", rendered)
        self.assertIn('System.out.println("Done");', rendered)

    def test_extracts_cpp_string_concatenation(self):
        program = extract_rule_program(
            'string name = "Alice";\ncout << "Hello, " << name << endl;\n',
            "cpp",
        )

        self.assertIsNotNone(program)
        self.assertEqual(
            [(item.kind, item.value) for item in program.outputs],
            [("literal", "Hello, Alice")],
        )


class ApiContractTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmpdir.cleanup)
        self.env_patch = patch.dict(
            os.environ,
            {
                "CODESHIFT_STORAGE_DIR": self.tmpdir.name,
            },
            clear=False,
        )
        self.env_patch.start()
        self.addCleanup(self.env_patch.stop)
        self.client = TestClient(app)

    def test_capabilities_reports_v12_contract(self):
        response = self.client.get("/v1/capabilities")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["service_version"], "v1.2")
        self.assertIn("IDEMPOTENCY_KEY_REUSED", payload["error_codes"])

    def test_convert_replays_response_for_same_idempotency_key(self):
        request_body = {
            "code": 'name = "Alice"\nprint("Hello, " + name)\n',
            "filename": "demo.py",
            "source_language": "python",
            "target_language": "javascript",
            "allow_ai_fallback": False,
        }
        headers = {"X-Idempotency-Key": "convert-demo-1"}

        first = self.client.post("/v1/convert", json=request_body, headers=headers)
        second = self.client.post("/v1/convert", json=request_body, headers=headers)

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        first_payload = first.json()
        second_payload = second.json()
        self.assertEqual(first_payload["trace_id"], second_payload["trace_id"])
        self.assertFalse(first_payload["idempotent_replay"])
        self.assertTrue(second_payload["idempotent_replay"])
        self.assertEqual(first_payload["converted_code"], second_payload["converted_code"])

    def test_convert_rejects_reused_key_for_different_request(self):
        headers = {"X-Idempotency-Key": "convert-demo-2"}
        first_body = {
            "code": 'print("hi")\n',
            "filename": "demo.py",
            "source_language": "python",
            "target_language": "javascript",
            "allow_ai_fallback": False,
        }
        second_body = {
            "code": 'print("bye")\n',
            "filename": "demo.py",
            "source_language": "python",
            "target_language": "javascript",
            "allow_ai_fallback": False,
        }

        first = self.client.post("/v1/convert", json=first_body, headers=headers)
        second = self.client.post("/v1/convert", json=second_body, headers=headers)

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        payload = second.json()
        self.assertFalse(payload["success"])
        self.assertEqual(payload["error_code"], "IDEMPOTENCY_KEY_REUSED")
        self.assertEqual(payload["execution_mode"], "idempotency_conflict")

    def test_convert_writes_request_log_entry(self):
        request_body = {
            "code": 'print("hi")\n',
            "filename": "demo.py",
            "source_language": "python",
            "target_language": "javascript",
            "allow_ai_fallback": False,
        }

        response = self.client.post("/v1/convert", json=request_body)

        self.assertEqual(response.status_code, 200)
        log_path = os.path.join(self.tmpdir.name, "logs", "requests.jsonl")
        self.assertTrue(os.path.exists(log_path))
        with open(log_path, "r", encoding="utf-8") as handle:
            entries = [json.loads(line) for line in handle if line.strip()]

        self.assertTrue(entries)
        latest = entries[-1]
        self.assertEqual(latest["endpoint"], "/v1/convert")
        self.assertIn("code_sha256", latest["request"])
        self.assertNotIn("code", latest["request"])
        self.assertIn("request_hash", latest["metadata"])


if __name__ == "__main__":
    unittest.main()
