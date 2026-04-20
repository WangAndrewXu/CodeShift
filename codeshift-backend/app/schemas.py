from dataclasses import dataclass

from pydantic import BaseModel


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

