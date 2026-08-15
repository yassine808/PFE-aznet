"""Prompt library loader.

Module is `prompt_loader`, not `prompts`, because `app/prompts/` is the folder
holding the Markdown — a module and a package of the same name shadow each
other, and which one wins depends on import order.

The prompts live as Markdown in `app/prompts/` so they can be edited, reviewed
and diffed without touching Python — a prompt change is a content change, and
burying it in a string literal makes it invisible in review.

They are read **once, at first use, and cached**, not re-read per request:
per-call file I/O on the hot path buys nothing, and a prompt that can change
between two requests in the same process makes a bad extraction impossible to
reproduce. Restart the API to pick up an edit.

`00-soul.md` is prepended to every model-facing prompt, so identity and the
never-invent rule cannot be forgotten by whoever writes the next one. The STT
vocabulary file is the exception: Whisper treats its `prompt` as preceding
transcript text, not as instructions, so prefixing the soul there would push
French prose into the transcript.
"""
from functools import lru_cache
from pathlib import Path

PROMPT_DIR = Path(__file__).resolve().parent / "prompts"

SOUL = "00-soul.md"
TEXT_EXTRACTION = "extraction-text.md"
IMAGE_EXTRACTION = "extraction-image.md"
STT_VOCABULARY = "stt-vocabulary.md"
PROFILE = "profile.md"


class PromptError(RuntimeError):
    pass


def _strip_front_matter(raw: str) -> str:
    """Drop HTML comments and the leading `# Title` line.

    The files are written to be read by a human first — they carry a title and a
    long rationale comment explaining why each rule exists. None of that should
    be paid for on every API call, so it is stripped before the text is sent.
    """
    out, in_comment = [], False
    for line in raw.splitlines():
        stripped = line.strip()
        if in_comment:
            if "-->" in stripped:
                in_comment = False
            continue
        if stripped.startswith("<!--"):
            in_comment = "-->" not in stripped
            continue
        if stripped.startswith("# ") and not out:
            continue
        out.append(line)
    return "\n".join(out).strip()


@lru_cache(maxsize=None)
def load(name: str, with_soul: bool = True) -> str:
    """Return a prompt, optionally prefixed with the shared identity block.

    Missing or empty files raise: a silently empty prompt would degrade every
    extraction at once while every request still returned 200, which is the
    worst possible failure mode for this pipeline.
    """
    path = PROMPT_DIR / name
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise PromptError(f"prompt {name!r} unreadable at {path}: {exc}") from exc

    body = _strip_front_matter(raw)
    if not body:
        raise PromptError(f"prompt {name!r} is empty after stripping comments — {path}")

    if not with_soul or name == SOUL:
        return body
    return f"{load(SOUL, with_soul=False)}\n\n---\n\n{body}"


def available() -> dict:
    """Prompt name -> character count. Surfaced by /health so an operator can
    see at a glance that the prompts loaded and how much they cost per call."""
    sizes = {}
    for name in (SOUL, TEXT_EXTRACTION, IMAGE_EXTRACTION, STT_VOCABULARY, PROFILE):
        try:
            # STT never gets the soul block, so reporting its size with one
            # would overstate what Whisper is actually sent.
            sizes[name] = len(load(name, with_soul=name != STT_VOCABULARY))
        except PromptError as exc:
            sizes[name] = f"ERROR: {exc}"
    return sizes
