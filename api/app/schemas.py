"""Pydantic schemas — the data contract between the AI service and n8n.

Field set mirrors cahier des charges §3/§6. Metadata fields (date, heure,
technicien, lien_audio) are added by n8n from the WhatsApp message context;
this service only returns what it can derive from the audio/text itself.
"""
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator


# `resume` is deliberately excluded: the model always writes one, even for
# "salut". It is the only field that cannot distinguish a report from a
# greeting, which is exactly the distinction `has_data` answers.
DATA_FIELDS = (
    "chantier", "client", "type_activite", "goulottes_m", "cables_m",
    "bureaux_termines", "panneaux_raccordes", "autres_travaux", "observations",
)


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

    chantier: Optional[str] = Field(None, description="Nom du chantier mentionné")
    client: Optional[str] = Field(None, description="Nom du client mentionné")
    type_activite: Optional[str] = Field(
        None, description="Type d'activité principal (ex: câblage, finition)"
    )
    goulottes_m: Optional[float] = Field(
        None, ge=0, description="Mètres de goulotte installés"
    )
    cables_m: Optional[float] = Field(
        None, ge=0, description="Mètres de câble réseau posés"
    )
    bureaux_termines: Optional[int] = Field(
        None, ge=0, description="Nombre de bureaux terminés"
    )
    panneaux_raccordes: Optional[int] = Field(
        None, ge=0, description="Nombre de panneaux de brassage raccordés"
    )
    autres_travaux: Optional[str] = Field(
        None, description="Travaux ne rentrant dans aucune quantité standard"
    )
    observations: Optional[str] = Field(
        None, description="Problèmes, remarques, besoins matériels signalés"
    )
    resume: str = Field(
        ..., description="Résumé professionnel en français (2-4 phrases)"
    )

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
        None,
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
        None, description="Absent en mode texte (formulaire)"
    )
    warnings: List[str] = Field(
        default_factory=list,
        description="Signaux qualité (ex: transcription douteuse) pour le flagging n8n",
    )
    lien_audio: Optional[str] = Field(
        None,
        description=(
            "Lien durable (Google Drive) vers l'audio, quand l'upload a réussi. "
            "n8n le préfère au file_id de la chaîne, qui expire."
        ),
    )
