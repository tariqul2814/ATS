"""Prompt construction (Req 6). Pure: same prepared input + template -> same messages.

Follows: input preparation (prepare). Precedes: the LLM call (llm_client).
"""

import re
from dataclasses import dataclass
from functools import lru_cache
from importlib import resources
from typing import TypedDict

from app.pipeline.prepare import PreparedInput

USER_SEPARATOR = "\n---USER---\n"
_PLACEHOLDER = re.compile(r"\{\{(CV_TEXT|JOB_DESCRIPTION)\}\}")


class ChatMessage(TypedDict):
    """One chat message in the role/content shape the LLM client expects."""

    role: str
    content: str


@dataclass(frozen=True)
class PromptTemplate:
    """A parsed prompt template: its name and the system and user parts, before placeholder fill."""

    name: str
    system: str
    user: str

    @classmethod
    def parse(cls, name: str, text: str) -> "PromptTemplate":
        """Split template text into system and user parts; raise ValueError if either is malformed."""
        system, sep, user = text.partition(USER_SEPARATOR)
        if not sep or "{{CV_TEXT}}" not in user or "{{JOB_DESCRIPTION}}" not in user:
            raise ValueError(f"prompt template {name!r} needs a ---USER--- part with both placeholders")
        return cls(name=name, system=system.strip(), user=user.strip())


@lru_cache
def load_template(name: str) -> PromptTemplate:
    """Load and parse the named template from app/prompts; raise ValueError on a bad name."""
    if not re.fullmatch(r"[A-Za-z0-9_]+", name):
        raise ValueError(f"invalid prompt template name {name!r}")
    text = resources.files("app.prompts").joinpath(f"{name}.md").read_text(encoding="utf-8")
    return PromptTemplate.parse(name, text)


def build_prompt(prepared: PreparedInput, template: PromptTemplate) -> list[ChatMessage]:
    """Fill the template's placeholders with the prepared inputs and return the chat messages."""
    values = {"CV_TEXT": prepared.cv_text, "JOB_DESCRIPTION": prepared.job_description}
    # Single pass, so placeholder-looking text inside the CV is never expanded.
    user = _PLACEHOLDER.sub(lambda m: values[m.group(1)], template.user)
    return [
        {"role": "system", "content": template.system},
        {"role": "user", "content": user},
    ]


def reformat_messages(previous: list[ChatMessage], bad_output: str, problem: str) -> list[ChatMessage]:
    """Follow-up turn asking the model to fix output that failed validation (Req 8.4)."""
    return [
        *previous,
        {"role": "assistant", "content": bad_output[:4000]},
        {
            "role": "user",
            "content": (
                "Your previous reply could not be used: "
                f"{problem[:300]}. Reply again with ONLY the single JSON object in the exact schema "
                "from the instructions, with every key present and all scores inside their maxima."
            ),
        },
    ]
