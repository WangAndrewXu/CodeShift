# Supported Patterns

Current lightweight rule support is intentionally narrow.

## Languages

- Python
- C++
- Java
- JavaScript

## Rule-Matched Shapes

### String variable assignment

Examples:

- `name = "Alice"`
- `const name = "Alice";`
- `String name = "Alice";`
- `string name = "Alice";`

### Direct print or log statements

Examples:

- `print("Done")`
- `print(name)`
- `console.log("Done")`
- `System.out.println(name);`
- `cout << "Done" << endl;`

### Basic `greet(...)` examples

Examples:

- `print(greet("Alice"))`
- `console.log(greet(name));`

### Simple string concatenation

Examples:

- `print("Hello, " + name)`
- `console.log("Hello, " + name)`
- `System.out.println("Hello, " + name);`
- `cout << "Hello, " << name << endl;`

## Non-Goals

These currently fall outside lightweight support:

- Arbitrary expressions
- Nested function calls beyond `greet(...)`
- Loops and conditionals as conversion targets
- Multi-function programs that need semantic preservation
- Multi-file codebases
