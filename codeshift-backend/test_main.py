import json
import os
import tempfile
import unittest
from datetime import timedelta
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.api import app
from app.rule_engine import extract_rule_program, render_code
from app.runtime_store import (
    append_request_log,
    build_idempotency_path,
    load_idempotency_record,
    now_utc,
    now_utc_iso,
    prune_request_logs,
    save_idempotency_record,
)
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
                "CODESHIFT_REQUEST_LOG_RETENTION_DAYS": "7",
                "CODESHIFT_IDEMPOTENCY_TTL_DAYS": "3",
            },
            clear=False,
        )
        self.env_patch.start()
        self.addCleanup(self.env_patch.stop)
        self.client = TestClient(app)

    def test_capabilities_reports_v13_contract(self):
        response = self.client.get("/v1/capabilities")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["service_version"], "v1.3")
        self.assertIn("IDEMPOTENCY_KEY_REUSED", payload["error_codes"])
        self.assertEqual(payload["request_log_retention_days"], 7)
        self.assertEqual(payload["idempotency_ttl_days"], 3)

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
        self.assertIn("Response replayed from idempotency store.", second_payload["warnings"])

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


class RuntimeStoreTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmpdir.cleanup)
        self.env_patch = patch.dict(
            os.environ,
            {
                "CODESHIFT_STORAGE_DIR": self.tmpdir.name,
                "CODESHIFT_REQUEST_LOG_RETENTION_DAYS": "7",
                "CODESHIFT_IDEMPOTENCY_TTL_DAYS": "3",
            },
            clear=False,
        )
        self.env_patch.start()
        self.addCleanup(self.env_patch.stop)

    def test_prune_request_logs_removes_expired_entries(self):
        old_timestamp = (now_utc() - timedelta(days=10)).isoformat()
        fresh_timestamp = now_utc_iso()
        append_request_log(
            {
                "timestamp": old_timestamp,
                "endpoint": "/v1/convert",
                "trace_id": "trace_old",
                "success": True,
                "error_code": "",
                "execution_mode": "rule_based",
                "service_version": "v1.3",
                "request": {"code_sha256": "old", "code_length": 1},
                "metadata": {},
            }
        )
        append_request_log(
            {
                "timestamp": fresh_timestamp,
                "endpoint": "/v1/convert",
                "trace_id": "trace_new",
                "success": True,
                "error_code": "",
                "execution_mode": "rule_based",
                "service_version": "v1.3",
                "request": {"code_sha256": "new", "code_length": 1},
                "metadata": {},
            }
        )

        prune_request_logs()

        log_path = os.path.join(self.tmpdir.name, "logs", "requests.jsonl")
        with open(log_path, "r", encoding="utf-8") as handle:
            entries = [json.loads(line) for line in handle if line.strip()]

        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["trace_id"], "trace_new")

    def test_expired_idempotency_record_is_removed_on_load(self):
        save_idempotency_record(
            "expired-key",
            {
                "request_hash": "abc123",
                "response": {
                    "success": True,
                    "message": "ok",
                    "error_code": "",
                    "capability_hint": "",
                    "service_version": "v1.3",
                    "warnings": [],
                    "trace_id": "trace_123",
                    "converted_code": "console.log(\"hi\");",
                    "source_language": "python",
                    "target_language": "javascript",
                    "filename": "demo.py",
                    "execution_mode": "rule_based",
                    "rule_match_type": "direct_print",
                    "rule": "test",
                    "idempotency_key": "expired-key",
                    "idempotent_replay": False,
                },
            },
        )

        path = build_idempotency_path("expired-key")
        with open(path, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
        payload["expires_at"] = (now_utc() - timedelta(minutes=1)).isoformat()
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(payload, handle)

        loaded = load_idempotency_record("expired-key")

        self.assertIsNone(loaded)
        self.assertFalse(os.path.exists(path))


if __name__ == "__main__":
    unittest.main()
