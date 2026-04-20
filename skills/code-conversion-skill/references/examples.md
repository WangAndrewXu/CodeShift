# Examples

## Rule-only conversion

Input:

```json
{
  "code": "name = \"Alice\"\nprint(\"Hello, \" + name)\n",
  "filename": "demo.py",
  "source_language": "python",
  "target_language": "javascript",
  "allow_ai_fallback": false
}
```

Typical output:

```json
{
  "success": true,
  "converted_code": "console.log(\"Hello, Alice\");\n",
  "execution_mode": "rule_based"
}
```

## Rule miss without AI

Input:

```json
{
  "code": "print(\"Hello, \" + get_name())\n",
  "filename": "demo.py",
  "source_language": "python",
  "target_language": "javascript",
  "allow_ai_fallback": false
}
```

Typical output:

```json
{
  "success": false,
  "execution_mode": "rule_only_failed"
}
```
