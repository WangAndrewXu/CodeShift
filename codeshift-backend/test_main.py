import unittest

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


if __name__ == "__main__":
    unittest.main()


if __name__ == "__main__":
    unittest.main()
