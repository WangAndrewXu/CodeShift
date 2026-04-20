import os
from typing import cast

from openai import OpenAI


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
    provider_name: str | None = None,
):
    client = get_ai_client(api_key, base_url)
    if client is None:
        return False, "No API key was provided."

    final_model = model or os.getenv("OPENAI_MODEL") or "gpt-5.4-mini"
    provider_label = provider_name or "AI provider"

    try:
        response = client.responses.create(
            model=final_model,
            input="Reply with exactly the single word: OK",
        )

        text = response.output_text.strip()
        if not text:
            return False, f"{provider_label} returned an empty response during test."

        return True, f"Connection successful via {provider_label} using model {final_model}."
    except Exception as exc:
        return False, f"Connection failed via {provider_label}: {str(exc)}"


def ai_convert_fallback(
    code: str,
    source_language: str,
    target_language: str,
    api_key: str | None = None,
    base_url: str | None = None,
    model: str | None = None,
    provider_name: str | None = None,
):
    client = get_ai_client(api_key, base_url)
    if client is None:
        return None, (
            "Rule-based conversion failed, and AI fallback is unavailable because no API key "
            "was provided."
        )

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
            input=prompt,
        )

        converted = response.output_text.strip()
        if not converted:
            return None, f"{provider_label} returned an empty result."

        return converted, f"AI fallback used via {provider_label} with model {final_model}"
    except Exception as exc:
        return None, f"AI fallback failed via {provider_label}: {str(exc)}"

