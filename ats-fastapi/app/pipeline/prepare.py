"""Input preparation (Req 5): normalise, neutralise, and bound the CV and job description.

Follows: text extraction (extract). Precedes: prompt construction (prompt).
Pure: no I/O, deterministic. See design §Input size budget for the three-band policy.
"""

import re
from dataclasses import dataclass

from app.pipeline.errors import InputTooLargeError

CV_TAG = "candidate_cv"
JD_TAG = "job_description"
TRUNCATION_MARKER = "\n[… truncated …]\n"
HEAD_SHARE = 0.85
# How far a cut may move to land on a line break instead of mid-line.
SNAP_WINDOW = 200

_DELIMITER = re.compile(rf"<\s*/?\s*({CV_TAG}|{JD_TAG})\s*>", re.IGNORECASE)
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_BLANK_RUNS = re.compile(r"\n{3,}")
_TRAILING_SPACE = re.compile(r"[ \t]+\n")


@dataclass(frozen=True)
class InputLimits:
    """Character budgets for the CV and job description, plus the hard reject ceiling."""

    max_cv_chars: int
    max_jd_chars: int
    hard_ceiling_chars: int


@dataclass(frozen=True)
class PreparedInput:
    """The CV and job description after normalising and truncation, with what was cut recorded."""

    cv_text: str
    job_description: str
    truncated: bool
    original_chars: int
    original_jd_chars: int
    cv_truncated: bool
    jd_truncated: bool


def prepare_input(cv_text: str, job_description: str, limits: InputLimits) -> PreparedInput:
    """Normalise and neutralise both inputs, then truncate to budget.

    Raises InputTooLargeError if either input exceeds the hard ceiling before truncation.
    """
    cv = _neutralise(_normalise(cv_text))
    jd = _neutralise(_normalise(job_description))

    if len(cv) > limits.hard_ceiling_chars:
        raise InputTooLargeError(f"CV text is {len(cv)} chars (ceiling {limits.hard_ceiling_chars})")
    if len(jd) > limits.hard_ceiling_chars:
        raise InputTooLargeError(f"job description is {len(jd)} chars (ceiling {limits.hard_ceiling_chars})")

    cv_out = _truncate_head_tail(cv, limits.max_cv_chars)
    jd_out = _truncate_head(jd, limits.max_jd_chars)
    cv_cut, jd_cut = cv_out != cv, jd_out != jd
    return PreparedInput(
        cv_text=cv_out,
        job_description=jd_out,
        truncated=cv_cut or jd_cut,
        original_chars=len(cv),
        original_jd_chars=len(jd),
        cv_truncated=cv_cut,
        jd_truncated=jd_cut,
    )


def _normalise(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = _CONTROL.sub("", text)
    text = _TRAILING_SPACE.sub("\n", text)
    return _BLANK_RUNS.sub("\n\n", text).strip()


def _neutralise(text: str) -> str:
    """Stop untrusted text from opening or closing the prompt's own sections (Req 5.3)."""
    return _DELIMITER.sub(lambda m: m.group(0).replace("<", "‹").replace(">", "›"), text)


def _truncate_head_tail(text: str, budget: int) -> str:
    """Keep the front of the CV (summary, skills, recent roles) and its end (education, certs)."""
    if len(text) <= budget:
        return text
    room = budget - len(TRUNCATION_MARKER)
    if room <= 0:
        return text[:budget]
    head_len = int(room * HEAD_SHARE)
    head = _snap_end(text[:head_len])
    tail = _snap_start(text[len(text) - (room - len(head)) :])
    return head + TRUNCATION_MARKER + tail


def _truncate_head(text: str, budget: int) -> str:
    if len(text) <= budget:
        return text
    room = budget - len(TRUNCATION_MARKER)
    if room <= 0:
        return text[:budget]
    return _snap_end(text[:room]) + TRUNCATION_MARKER.rstrip("\n")


def _snap_end(chunk: str) -> str:
    cut = chunk.rfind("\n", max(0, len(chunk) - SNAP_WINDOW))
    return chunk[:cut] if cut > 0 else chunk


def _snap_start(chunk: str) -> str:
    cut = chunk.find("\n", 0, SNAP_WINDOW)
    return chunk[cut + 1 :] if cut >= 0 else chunk
