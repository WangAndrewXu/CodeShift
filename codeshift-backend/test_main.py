import unittest

import main


class RuleProgramTests(unittest.TestCase):
    def test_extracts_python_string_variable_and_print(self):
        program = main.extract_rule_program(
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
        program = main.extract_rule_program(
            'const name = "Alice";\nconsole.log(greet(name));\n',
            "javascript",
        )

        self.assertIsNotNone(program)
        self.assertEqual(
            [(item.kind, item.value) for item in program.outputs],
            [("greet_variable", "name")],
        )

    def test_rejects_unhandled_print_expression(self):
        program = main.extract_rule_program(
            'print("Hello, " + name)\n',
            "python",
        )

        self.assertIsNone(program)

    def test_renders_java_program_for_simple_outputs(self):
        program = main.RuleProgram(
            variables=[("name", "Alice")],
            outputs=[
                main.PrintOperation("variable", "name"),
                main.PrintOperation("literal", "Done"),
            ],
        )

        rendered = main.render_code(program, "java")

        self.assertIn('String name = "Alice";', rendered)
        self.assertIn("System.out.println(name);", rendered)
        self.assertIn('System.out.println("Done");', rendered)


if __name__ == "__main__":
    unittest.main()
