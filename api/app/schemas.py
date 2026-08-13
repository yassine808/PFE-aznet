"""Pydantic schemas — the data contract between the AI service and n8n.

The field set mirrors the director's own tracking file (`Tableau de Suivi
projet`), whose journal tab is the record this pipeline feeds: one row per
(date, technicien), typed quantity columns, a location block, a stock block
and a free remarks column.

Two things deliberately absent from `ExtractedReport`:

- **chantier** — routing comes from the org chart (a chef carries the site,
  their technicians inherit it), not from what the model thinks it heard. It
  is stamped onto the row by the pipeline and snapshotted there forever.
- **équipe, heures, JH, ordre du jour, taux de réalisation** — planned before
  the day or judged after it. A technician does not dictate them; the chef
  fills them in the dashboard.
"""
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator


ETAGES = ("RDC", "E1", "E2", "E3", "E4")
AILES = ("Droite", "Gauche")
LOCAUX_TECHNIQUES = ("RG",) + tuple("SR%d" % i for i in range(1, 11))

# `resume` is deliberately excluded: the model always writes one, even for
# "salut". It is the only field that cannot distinguish a report from a
# greeting, which is exactly the distinction `has_data` answers.
#
# The location, stock, remarks and blocker fields ARE in here. A day where the
# crew was stopped for 1h30 or found every office locked produces no quantity
# at all, and it is the report the director most needs to read — as is a
# message that only reports missing material or tomorrow's plan.
DATA_FIELDS = (
    "cables_prepares_m", "cables_installes_m", "goulotte_m",
    "prises_connectees", "panneaux_prises_brassees", "prises_testees",
    "fibre_m", "interconnexions", "connexions_optiques_brins",
    "etages", "ailes", "locaux_techniques",
    "stock_cable_m", "stock_goulotte_m", "stock_fibre_m",
    "remarques", "temps_arret_min", "motif_arret",
    "besoins", "prochaines_etapes",
)

# Formatting the model gets wrong without being wrong about the facts:
# "rdc", "1er étage", "SR 4". Normalizing these is not a fallback — an
# unrecognized value still raises, so an invented floor fails loudly.
_ETAGE_ALIASES = {
    "rdc": "RDC", "rez de chaussee": "RDC", "rez-de-chaussee": "RDC",
    "0": "RDC", "r.d.c": "RDC", "rez de chaussée": "RDC",
}
for _i in range(1, 5):
    for _form in ("e%d", "%d", "%der etage", "%deme etage", "etage %d",
                  "%dere etage", "%d er etage", "%d eme etage"):
        _ETAGE_ALIASES[(_form % _i)] = "E%d" % _i


def _squash(value: str) -> str:
    return " ".join(str(value).strip().lower().replace("è", "e")
                    .replace("é", "e").replace("ê", "e").split())


class ExtractedReport(BaseModel):
    """Structured facts extracted from one daily report."""

    @field_validator("*", mode="before")
    @classmethod
    def _null_strings_to_none(cls, v):
        # LLM JSON mode (Groq/Llama) sometimes emits the *string* "null"
        # for absent fields; the prompt means None, so normalize before parsing.
        if isinstance(v, str) and v.strip().lower() in {"null", "none", ""}:
            return None
        return v

    # --- travaux cuivre ------------------------------------------------
    cables_prepares_m: Optional[float] = Field(
        default=None, ge=0, description="Mètres de câble cuivre préparés (tirés et mesurés)"
    )
    cables_installes_m: Optional[float] = Field(
        default=None, ge=0, description="Mètres de câble cuivre installés et raccordés"
    )
    goulotte_m: Optional[float] = Field(
        default=None, ge=0, description="Mètres de goulotte posés"
    )
    # The same physical port is counted three times in the director's file,
    # at three different stages, and a single day can report three different
    # numbers ("14 prises côté bureaux / 17 côté panneau / 15 testées").
    prises_connectees: Optional[int] = Field(
        default=None, ge=0, description="Prises RJ45 raccordées côté bureau"
    )
    panneaux_prises_brassees: Optional[int] = Field(
        default=None, ge=0, description="Prises raccordées côté panneau de brassage"
    )
    prises_testees: Optional[int] = Field(
        default=None, ge=0, description="Prises testées et étiquetées"
    )

    # --- travaux fibre -------------------------------------------------
    fibre_m: Optional[float] = Field(
        default=None, ge=0, description="Mètres de câble fibre optique posés"
    )
    interconnexions: Optional[int] = Field(
        default=None, ge=0, description="Nombre d'interconnexions installées entre locaux"
    )
    connexions_optiques_brins: Optional[int] = Field(
        default=None, ge=0, description="Brins de fibre optique fusionnés/connectés"
    )

    # --- localisation --------------------------------------------------
    etages: Optional[List[str]] = Field(
        default=None, description="Étages travaillés (RDC, E1..E4)"
    )
    ailes: Optional[List[str]] = Field(default=None, description="Ailes (Droite, Gauche)")
    locaux_techniques: Optional[List[str]] = Field(
        default=None, description="Locaux techniques (RG, SR1..SR10)"
    )

    # --- stock restant sur site ----------------------------------------
    stock_cable_m: Optional[float] = Field(
        default=None, ge=0, description="Mètres de câble restants en stock sur site"
    )
    stock_goulotte_m: Optional[float] = Field(
        default=None, ge=0, description="Mètres de goulotte restants en stock"
    )
    stock_fibre_m: Optional[float] = Field(
        default=None, ge=0, description="Mètres de fibre optique restants en stock"
    )

    remarques: Optional[str] = Field(
        default=None, description="Problèmes, blocages, matériel manquant, remarques"
    )
    # --- blocages, besoins, suite ----------------------------------------
    # A stopped day is a report (bureaux fermés, attente d'instruction), and so
    # is a message that only asks for material or announces tomorrow's plan.
    # These are the three things the director re-keys from remarks prose today,
    # structured so the cook can actually count them.
    temps_arret_min: Optional[float] = Field(
        default=None, ge=0,
        description="Minutes perdues à l'arrêt (attente, bureaux fermés, instruction). « Arrêtés 1h30 » = 90"
    )
    motif_arret: Optional[str] = Field(
        default=None, description="Raison de l'arrêt, une ligne"
    )
    besoins: Optional[str] = Field(
        default=None, description="Matériel manquant ou à commander"
    )
    prochaines_etapes: Optional[str] = Field(
        default=None, description="Ce que le technicien prévoit de faire ensuite"
    )
    resume: str = Field(
        ..., description="Résumé professionnel en français (2-4 phrases)"
    )

    @field_validator("etages", "ailes", "locaux_techniques", mode="before")
    @classmethod
    def _wrap_single(cls, v):
        # "RDC, E1, E2" and "RDC" are both things the model emits for a field
        # the file itself writes as a comma-joined string.
        if isinstance(v, str):
            return [part for part in (p.strip() for p in v.split(",")) if part]
        return v

    @field_validator("etages")
    @classmethod
    def _valid_etages(cls, v):
        return cls._canon(v, _ETAGE_ALIASES, ETAGES, "étage")

    @field_validator("ailes")
    @classmethod
    def _valid_ailes(cls, v):
        return cls._canon(v, {"droit": "Droite", "gauch": "Gauche"}, AILES, "aile")

    @field_validator("locaux_techniques")
    @classmethod
    def _valid_locaux(cls, v):
        return cls._canon(v, {}, LOCAUX_TECHNIQUES, "local technique")

    @staticmethod
    def _match(key, aliases, allowed):
        """One squashed value's canonical form, or None if nothing matched.

        Three passes in order of confidence: an exact alias, the allowed list
        itself ignoring case and spacing, then an alias used as a prefix — so
        "1er étage" and "e1" land on the same floor without "étage" alone
        matching anything.
        """
        hit = aliases.get(key)
        if hit is not None:
            return hit
        squashed = key.replace(" ", "")
        for candidate in allowed:
            if _squash(candidate).replace(" ", "") == squashed:
                return candidate
        for prefix, mapped in aliases.items():
            if key.startswith(prefix):
                return mapped
        return None

    @classmethod
    def _canon(cls, values, aliases, allowed, label):
        if values is None:
            return None
        out = []
        for raw in values:
            hit = cls._match(_squash(raw), aliases, allowed)
            if hit is None:
                # Loud, not dropped: an invented location is a wrong row, and
                # the extraction chain treats it as a model failure and retries.
                raise ValueError(
                    "%s inconnu: %r (attendu: %s)" % (label, raw, ", ".join(allowed))
                )
            if hit not in out:
                out.append(hit)
        return out or None

    def has_data(self) -> bool:
        """True when the message carried at least one extractable fact.

        A greeting extracts cleanly — every field null — and a 200 with an empty
        report is indistinguishable from a real one downstream, so n8n told the
        technician their report was saved. This is what tells the two apart.
        """
        return any(getattr(self, f) is not None for f in DATA_FIELDS)


class TranscriptionInfo(BaseModel):
    """How the audio became text — kept for benchmark and audit trail."""

    text: str
    provider: str
    latency_s: float = Field(..., ge=0)
    confidence: Optional[float] = Field(
        default=None,
        ge=0,
        le=1,
        description=(
            "Confiance du moteur STT (0-1), quand le fournisseur l'expose. "
            "None si le fournisseur ne renvoie aucun signal exploitable "
            "(ex: gemini, hf-darija)."
        ),
    )


class ProcessResponse(BaseModel):
    """Full response consumed by n8n to build the Google Sheets row."""

    rapport_complet: str = Field(
        ..., description="Texte intégral (transcription brute ou texte du formulaire)"
    )
    report: ExtractedReport
    transcription: Optional[TranscriptionInfo] = Field(
        default=None, description="Absent en mode texte (formulaire)"
    )
    warnings: List[str] = Field(
        default_factory=list,
        description="Signaux qualité (ex: transcription douteuse) pour le flagging n8n",
    )
    lien_audio: Optional[str] = Field(
        default=None,
        description=(
            "Lien durable (Google Drive) vers l'audio, quand l'upload a réussi. "
            "n8n le préfère au file_id de la chaîne, qui expire."
        ),
    )
