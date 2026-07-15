"""Pydantic schemas — the data contract between the AI service and n8n.

Field set mirrors cahier des charges §3/§6. Metadata fields (date, heure,
technicien, lien_audio) are added by n8n from the WhatsApp message context;
this service only returns what it can derive from the audio/text itself.
"""
from typing import List, Optional

from pydantic import BaseModel, Field


class ExtractedReport(BaseModel):
    """Structured facts extracted from one daily report."""

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


class TranscriptionInfo(BaseModel):
    """How the audio became text — kept for benchmark and audit trail."""

    text: str
    provider: str
    latency_s: float = Field(..., ge=0)


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
