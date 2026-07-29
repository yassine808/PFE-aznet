"""Technician profiles — the fifth model.

Writes one short French paragraph about a technician, from their own past
reports, so the extraction prompt knows who is writing to it.

Three things make this cheap and safe:

- It runs on a **cron at 03:00**, never on the reply path. A technician waiting
  for their summary must not also wait for us to tidy a profile, and a failure
  here must never turn into "❌ Erreur" on their phone.
- It reads the **Sheet**, which is already the permanent record of every report
  ever sent. There is no second store of facts to keep in sync.
- The profile is **derived, never authoritative**. A bad one is fixed by
  regenerating it; nothing is lost, because nothing was ever only here.

The prompt forbids inventing and forbids numbers, for a reason worth keeping in
mind: this text is injected into the extraction prompt, so a fabricated
"pose environ 40 m par jour" would be sitting there as context the next time the
model has to decide what `goulottes_m` is on a message that never said.
"""
from typing import Any, Dict, List, Optional, Tuple

from app import prompt_loader
from app.config import settings

# Reports older than this are ignored. A technician who moved site in March
# should not be described in September by what they did in January.
PROFILE_WINDOW_REPORTS = 40

# Ceiling on what one profile costs to build. Well above a normal technician's
# monthly volume; it exists so a single prolific sender cannot produce a prompt
# that fails on token limits at 3am with nobody watching.
MAX_CHARS_PER_REPORT = 400


class ProfileError(RuntimeError):
    pass


_PROMPT = prompt_loader.load(prompt_loader.PROFILE)


def _parse_chain(raw: str) -> List[Tuple[str, str]]:
    chain = []
    for item in (part.strip() for part in raw.split(",")):
        if not item:
            continue
        provider, _, model = item.partition(":")
        if not provider or not model:
            raise ProfileError(f"malformed chain entry {item!r} — expected 'provider:model'")
        chain.append((provider, model))
    if not chain:
        raise ProfileError("empty profile chain")
    return chain


def collect(rows: List[Dict[str, Any]], name: str) -> str:
    """The reports written by `name`, newest first, as the model's input.

    Matched on the `technicien` column because that is what n8n writes into the
    Sheet, and it is the person's name — the same name both channel identities
    resolve to. That is what makes one profile cover both channels.
    """
    mine = [r for r in rows if (r.get("technicien") or "").strip().lower() == name.strip().lower()]
    mine = mine[-PROFILE_WINDOW_REPORTS:]
    lines = []
    for row in reversed(mine):
        text = (row.get("rapport_complet") or row.get("resume") or "").strip()
        if not text:
            continue
        lines.append("- %s | %s | %s" % (
            row.get("date") or "?",
            (row.get("chantier") or "?").strip(),
            text[:MAX_CHARS_PER_REPORT],
        ))
    return "\n".join(lines)


def _call_gemini(model: str, prompt: str) -> str:
    if not settings.gemini_api_key:
        raise ProfileError("GEMINI_API_KEY not configured")
    from google import genai

    client = genai.Client(api_key=settings.gemini_api_key)
    resp = client.models.generate_content(model=model, contents=prompt)
    return (resp.text or "").strip()


def _call_groq(model: str, prompt: str) -> str:
    if not settings.groq_api_key:
        raise ProfileError("GROQ_API_KEY not configured")
    from groq import Groq

    client = Groq(api_key=settings.groq_api_key)
    resp = client.chat.completions.create(
        model=model, messages=[{"role": "user", "content": prompt}]
    )
    return (resp.choices[0].message.content or "").strip()


_CALLERS = {"gemini": _call_gemini, "groq": _call_groq}


def build(name: str, role: Optional[str], reports: str) -> Tuple[str, str]:
    """Return (profile, model that answered). Raises if every model failed.

    Same ordered-fallback shape as extraction: tried left to right, first
    success wins, all failures raise one combined error. Never a silent empty
    profile — an empty string would overwrite a good profile with nothing.
    """
    if not reports.strip():
        raise ProfileError(f"no reports to summarise for {name!r}")

    prompt = "%s\n\n## Technicien\n%s%s\n\n## Rapports\n%s" % (
        _PROMPT, name, f" ({role})" if role else "", reports,
    )
    failures = []
    for provider, model in _parse_chain(settings.profile_chain):
        caller = _CALLERS.get(provider)
        if caller is None:
            failures.append(f"{provider}: unknown provider")
            continue
        try:
            text = caller(model, prompt)
        except Exception as exc:  # noqa: BLE001
            failures.append(f"{provider}/{model}: {exc}")
            continue
        if text:
            return text, f"{provider}/{model}"
        failures.append(f"{provider}/{model}: empty response")
    raise ProfileError("every profile model failed — " + " | ".join(failures))


def refresh_person(person: Dict[str, Any], rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Rebuild one person's profile. Never raises: called in a loop by the
    scheduler, and one technician with no reports must not stop the rest."""
    from app import logs  # local: keeps memory importable without psycopg2

    name = person["name"]
    try:
        reports = collect(rows, name)
        profile, model = build(name, person.get("role"), reports)
    except ProfileError as exc:
        # Left as-is rather than cleared: yesterday's profile is better context
        # than none, and clearing on failure would erase a good summary because
        # a free-tier model was busy at 3am.
        return {"person_id": person["id"], "name": name, "updated": False, "reason": str(exc)}
    logs.save_profile(person["id"], profile)
    return {"person_id": person["id"], "name": name, "updated": True, "model": model,
            "profile": profile}
