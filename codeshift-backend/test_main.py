import json
import os
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.api import app
from app.rule_engine import extract_rule_program, render_code
from app.runtime_store import (
    append_request_log,
    build_idempotency_path,
    build_request_hash,
    load_idempotency_record,
    now_utc,
    now_utc_iso,
    prune_request_logs,
    reset_runtime_store_cache,
    save_idempotency_record,
    reserve_idempotency_key,
    get_runtime_storage_backend_name,
    runtime_storage_is_multi_instance_safe,
)
from app.schemas import PrintOperation, RuleProgram


SNAPSHOT_PATH = Path(__file__).resolve().parent / "contract_snapshots" / "v1.5.json"
with open(SNAPSHOT_PATH, "r", encoding="utf-8") as handle:
    CONTRACT_SNAPSHOT = json.load(handle)


def assert_required_keys(testcase: unittest.TestCase, payload: dict, expected_keys: list[str]):
    testcase.assertEqual(set(payload.keys()), set(expected_keys))


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
                "CODESHIFT_CONVERT_REQUESTS_PER_MINUTE": "20",
                "CODESHIFT_PROVIDER_TEST_REQUESTS_PER_MINUTE": "10",
                "CODESHIFT_RATE_LIMIT_WINDOW_SECONDS": "60",
                "CODESHIFT_RUNTIME_STORE_BACKEND": "filesystem",
            },
            clear=False,
        )
        self.env_patch.start()
        reset_runtime_store_cache()
        self.addCleanup(reset_runtime_store_cache)
        self.addCleanup(self.env_patch.stop)
        self.client = TestClient(app)

    def test_capabilities_reports_v15_contract(self):
        response = self.client.get("/v1/capabilities")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        snapshot = CONTRACT_SNAPSHOT["capabilities"]
        assert_required_keys(self, payload, snapshot["required_keys"])
        for key, value in snapshot["expected_values"].items():
            self.assertEqual(payload[key], value)
        for error_code in snapshot["required_error_codes"]:
            self.assertIn(error_code, payload["error_codes"])
        for provider_name in snapshot["required_provider_names"]:
            self.assertIn(provider_name, payload["allowed_provider_names"])
        self.assertEqual(payload["runtime_storage_backend"], get_runtime_storage_backend_name())
        self.assertEqual(payload["multi_instance_safe"], runtime_storage_is_multi_instance_safe())

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

    def test_convert_returns_snapshot_shape_for_success_response(self):
        request_body = {
            "code": 'name = "Alice"\nprint("Hello, " + name)\n',
            "filename": "demo.py",
            "source_language": "python",
            "target_language": "javascript",
            "allow_ai_fallback": False,
        }
        headers = {"X-Idempotency-Key": "ci-contract-check"}

        response = self.client.post("/v1/convert", json=request_body, headers=headers)

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        snapshot = CONTRACT_SNAPSHOT["convert"]
        assert_required_keys(self, payload, snapshot["success_required_keys"])
        self.assertTrue(payload["trace_id"].startswith("trace_"))
        self.assertTrue(payload["success"])
        for key, value in snapshot["success_example"].items():
            self.assertEqual(payload[key], value)

    def test_convert_returns_snapshot_shape_for_rule_only_failure(self):
        request_body = {
            "code": 'print("Hello, " + get_name())\n',
            "filename": "demo.py",
            "source_language": "python",
            "target_language": "javascript",
            "allow_ai_fallback": False,
        }

        response = self.client.post("/v1/convert", json=request_body)

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        snapshot = CONTRACT_SNAPSHOT["convert"]
        assert_required_keys(self, payload, snapshot["failure_required_keys"])
        self.assertTrue(payload["trace_id"].startswith("trace_"))
        self.assertFalse(payload["success"])
        self.assertIn("Try a simpler print/log example", payload["message"])
        self.assertTrue(payload["capability_hint"])
        for key, value in snapshot["failure_example"].items():
            self.assertEqual(payload[key], value)

    def test_convert_rejects_unknown_provider_name(self):
        request_body = {
            "code": 'print("hi")\n',
            "filename": "demo.py",
            "source_language": "python",
            "target_language": "javascript",
            "allow_ai_fallback": True,
        }

        response = self.client.post(
            "/v1/convert",
            json=request_body,
            headers={"X-Provider-Name": "anthropic"},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        for key, value in CONTRACT_SNAPSHOT["convert"]["provider_policy_failure"].items():
            self.assertEqual(payload[key], value)
        self.assertIn("Allowed provider names", payload["capability_hint"])

    def test_convert_rate_limits_excessive_requests(self):
        with patch.dict(
            os.environ,
            {
                "CODESHIFT_STORAGE_DIR": self.tmpdir.name,
                "CODESHIFT_CONVERT_REQUESTS_PER_MINUTE": "1",
                "CODESHIFT_RATE_LIMIT_WINDOW_SECONDS": "60",
                "CODESHIFT_RUNTIME_STORE_BACKEND": "filesystem",
            },
            clear=False,
        ):
            request_body = {
                "code": 'print("hi")\n',
                "filename": "demo.py",
                "source_language": "python",
                "target_language": "javascript",
                "allow_ai_fallback": False,
            }
            self.client.post("/v1/convert", json=request_body)
            response = self.client.post("/v1/convert", json=request_body)

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        for key, value in CONTRACT_SNAPSHOT["convert"]["rate_limit_failure"].items():
            self.assertEqual(payload[key], value)
        self.assertIn("Retry after", payload["message"])

    def test_provider_test_rate_limits_excessive_requests(self):
        with patch.dict(
            os.environ,
            {
                "CODESHIFT_STORAGE_DIR": self.tmpdir.name,
                "CODESHIFT_PROVIDER_TEST_REQUESTS_PER_MINUTE": "1",
                "CODESHIFT_RATE_LIMIT_WINDOW_SECONDS": "60",
                "CODESHIFT_RUNTIME_STORE_BACKEND": "filesystem",
            },
            clear=False,
        ):
            self.client.post("/test-provider")
            response = self.client.post("/test-provider")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["error_code"], "RATE_LIMIT_EXCEEDED")
        assert_required_keys(self, payload, CONTRACT_SNAPSHOT["provider_test"]["failure_required_keys"])
        for key, value in CONTRACT_SNAPSHOT["provider_test"]["rate_limit_failure"].items():
            self.assertEqual(payload[key], value)

    def test_provider_test_returns_snapshot_shape_for_success_response(self):
        with patch("app.api.test_ai_connection", return_value=(True, "Connection successful via openai using model gpt-5.4-mini.")):
            response = self.client.post(
                "/test-provider",
                headers={
                    "X-API-Key": "test-key",
                    "X-Base-URL": "https://api.openai.com/v1",
                    "X-Model": "gpt-5.4-mini",
                    "X-Provider-Name": "openai",
                },
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        snapshot = CONTRACT_SNAPSHOT["provider_test"]
        assert_required_keys(self, payload, snapshot["success_required_keys"])
        self.assertTrue(payload["trace_id"].startswith("trace_"))
        self.assertEqual(payload["message"], "Connection successful via openai using model gpt-5.4-mini.")
        self.assertEqual(payload["warnings"], [])
        self.assertEqual(payload["capability_hint"], "")
        for key, value in snapshot["success_example"].items():
            self.assertEqual(payload[key], value)

    def test_provider_test_returns_snapshot_shape_for_policy_failure(self):
        response = self.client.post(
            "/test-provider",
            headers={"X-Provider-Name": "anthropic"},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        snapshot = CONTRACT_SNAPSHOT["provider_test"]
        assert_required_keys(self, payload, snapshot["failure_required_keys"])
        self.assertTrue(payload["trace_id"].startswith("trace_"))
        self.assertIn("Allowed provider names", payload["capability_hint"])
        for key, value in snapshot["provider_policy_failure"].items():
            self.assertEqual(payload[key], value)

    def test_provider_test_returns_snapshot_shape_for_generic_failure(self):
        response = self.client.post("/test-provider")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        snapshot = CONTRACT_SNAPSHOT["provider_test"]
        assert_required_keys(self, payload, snapshot["failure_required_keys"])
        self.assertTrue(payload["trace_id"].startswith("trace_"))
        self.assertEqual(payload["message"], "No API key was provided.")
        self.assertIn("Check API key", payload["capability_hint"])
        for key, value in snapshot["failure_example"].items():
            self.assertEqual(payload[key], value)

    def test_load_file_returns_snapshot_shape_for_success_response(self):
        response = self.client.post(
            "/load-file",
            files={"file": ("demo.py", b'print("hi")\n', "text/plain")},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        snapshot = CONTRACT_SNAPSHOT["load_file"]
        assert_required_keys(self, payload, snapshot["success_required_keys"])
        self.assertTrue(payload["trace_id"].startswith("trace_"))
        self.assertEqual(payload["warnings"], [])
        self.assertEqual(payload["message"], "")
        self.assertEqual(payload["capability_hint"], "")
        for key, value in snapshot["success_example"].items():
            self.assertEqual(payload[key], value)

    def test_load_file_returns_snapshot_shape_for_invalid_utf8_failure(self):
        response = self.client.post(
            "/load-file",
            files={"file": ("demo.py", b"\xff\xfe\xfd", "application/octet-stream")},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        snapshot = CONTRACT_SNAPSHOT["load_file"]
        assert_required_keys(self, payload, snapshot["failure_required_keys"])
        self.assertTrue(payload["trace_id"].startswith("trace_"))
        self.assertEqual(payload["message"], "This file is not valid UTF-8 text.")
        self.assertEqual(payload["warnings"], [])
        for key, value in snapshot["invalid_utf8_failure"].items():
            self.assertEqual(payload[key], value)

    def test_convert_returns_pending_for_matching_in_progress_key(self):
        request_body = {
            "code": 'print("hi")\n',
            "filename": "demo.py",
            "source_language": "python",
            "target_language": "javascript",
            "allow_ai_fallback": False,
        }
        headers = {"X-Idempotency-Key": "convert-pending-1"}
        request_hash = build_request_hash(
            {
                "request": request_body,
                "provider": {
                    "base_url": "",
                    "model": "",
                    "provider_name": "",
                    "api_key_sha256": "",
                },
            }
        )
        reserved = reserve_idempotency_key(headers["X-Idempotency-Key"], request_hash)
        self.assertTrue(reserved)

        response = self.client.post("/v1/convert", json=request_body, headers=headers)

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        for key, value in CONTRACT_SNAPSHOT["convert"]["pending_failure"].items():
            self.assertEqual(payload[key], value)
        self.assertIn("still in progress", payload["message"])

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
                "CODESHIFT_RUNTIME_STORE_BACKEND": "filesystem",
            },
            clear=False,
        )
        self.env_patch.start()
        reset_runtime_store_cache()
        self.addCleanup(reset_runtime_store_cache)
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
                "service_version": "v1.5",
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
                "service_version": "v1.5",
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
                    "service_version": "v1.5",
                    "warnings": [],
                    "trace_id": "trace_123",
                    "converted_code": 'console.log("hi");',
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
