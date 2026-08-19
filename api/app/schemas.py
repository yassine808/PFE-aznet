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
from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, Field, field_validator


ETAGES = ("RDC", "E1", "E2", "E3", "E4")
AILES = ("Droite", "Gauche")
LOCAUX_TECHNIQUES = ("RG",) + tuple("SR%d" % i for i in range(1, 11))

# --- articles du bordereau -------------------------------------------------
#
# The nine quantity fields above cover the *journal*: what a crew does in a day,
# measured the way the director's daily tab measures it. They do not cover the
# *bordereau* — the contract line items each site is delivered against, which
# until now were followed by hand because no field carried them.
#
# These 25 are the union of the three real bordereaux (DGH, Extralait, ACAPS),
# collapsed so that one physical thing is one field: DGH's "Câble CAT.6A",
# Extralait's "Câble informatique Catégorie 6 IPS" and ACAPS's "Cable UTP" are
# all `cables_installes_m`, which already existed. Only what had no field at
# all is new. Suffixes are the unit the bordereaux themselves use: `_m` for
# métrage (ML), `_u` for a countable piece (U).
#
# They are ordinary optional fields, so a report that mentions none of them is
# unchanged — and `null` still means "not mentioned", never zero.
ARTICLE_FIELDS = (
    # cuivre
    "cordons_brassage_1m_u", "cordons_liaison_3m_u",
    "flexible_arme_d16_m", "guide_cable_u",
    # fibre
    "tiroir_optique_24_u", "tiroir_optique_12_u", "pigtail_sc_u",
    "jarretiere_om3_u", "jarretiere_sc_lc_u", "jarretiere_lc_lc_u",
    # actif / réseau
    "switch_federateur_u", "switch_acces_u", "point_acces_ap_u",
    "module_sfp_plus_u", "module_sfp_u", "module_sfp_rj45_u",
    "cable_dac_u", "coffret_12u_u", "onduleur_u",
    # électricité
    "cable_elec_3x2_5_m", "fiche_2p_t_u", "disjoncteur_2x16a_u",
    "bandeau_elec_12p_u", "passe_cable_u", "borne_2_5_u",
)

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
    "besoins", "prochaines_etapes", "livraisons", "articles_libres",
    "heure_entree", "heure_sortie", "equipe",
) + ARTICLE_FIELDS

# Every quantity the journal counts, in the director's own order.
# `journal.NUMERIC_COLUMNS` maps exactly these to their Sheet columns, and a
# test pins the two together — the list lives here because `journal` imports
# `schemas` and not the other way round.
QUANTITY_FIELDS = (
    "cables_prepares_m", "cables_installes_m", "goulotte_m",
    "prises_connectees", "panneaux_prises_brassees", "prises_testees",
    "fibre_m", "interconnexions", "connexions_optiques_brins",
    "temps_arret_min",
) + ARTICLE_FIELDS

# What a supplier can deliver. An arrêt is minutes lost, not merchandise, so it
# is the one quantity that can never appear on a bon de livraison.
DELIVERABLE_FIELDS = tuple(f for f in QUANTITY_FIELDS if f != "temps_arret_min")

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


# The tokens a model emits when it means "absent" but is answering in JSON mode.
# One definition, used by both the wildcard validator and the list one — two
# copies would drift the first time a new vendor invents another spelling.
_NULLISH = {"null", "none", "nan", "n/a", "na", "-", ""}


def _is_nullish(value: str) -> bool:
    return str(value).strip().lower() in _NULLISH


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
        if isinstance(v, str) and _is_nullish(v):
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

    # --- articles du bordereau ------------------------------------------
    # Contract line items. See ARTICLE_FIELDS above for why these are one
    # field per physical thing rather than one per bordereau line. Counts are
    # ints because half a jarretière is a transcription error, not a quantity.
    cordons_brassage_1m_u: Optional[int] = Field(
        default=None, ge=0, description="Cordons de brassage 1 m posés"
    )
    cordons_liaison_3m_u: Optional[int] = Field(
        default=None, ge=0, description="Cordons de liaison 3 m posés"
    )
    flexible_arme_d16_m: Optional[float] = Field(
        default=None, ge=0, description="Mètres de flexible armé D16 posés"
    )
    guide_cable_u: Optional[int] = Field(
        default=None, ge=0, description="Guides de câble à balais 19\" posés"
    )
    tiroir_optique_24_u: Optional[int] = Field(
        default=None, ge=0, description="Tiroirs optiques 24 ports installés"
    )
    tiroir_optique_12_u: Optional[int] = Field(
        default=None, ge=0, description="Tiroirs optiques 12 ports installés"
    )
    pigtail_sc_u: Optional[int] = Field(
        default=None, ge=0, description="Pigtails SC installés"
    )
    jarretiere_om3_u: Optional[int] = Field(
        default=None, ge=0, description="Jarretières OM3 posées"
    )
    jarretiere_sc_lc_u: Optional[int] = Field(
        default=None, ge=0, description="Jarretières SC/LC posées"
    )
    jarretiere_lc_lc_u: Optional[int] = Field(
        default=None, ge=0, description="Jarretières LC/LC posées"
    )
    switch_federateur_u: Optional[int] = Field(
        default=None, ge=0, description="Switchs fédérateurs installés"
    )
    switch_acces_u: Optional[int] = Field(
        default=None, ge=0, description="Switchs d'accès installés"
    )
    point_acces_ap_u: Optional[int] = Field(
        default=None, ge=0, description="Points d'accès WiFi (AP) installés"
    )
    module_sfp_plus_u: Optional[int] = Field(
        default=None, ge=0, description="Modules optiques SFP+ installés"
    )
    module_sfp_u: Optional[int] = Field(
        default=None, ge=0, description="Modules optiques SFP installés"
    )
    module_sfp_rj45_u: Optional[int] = Field(
        default=None, ge=0, description="Modules optiques SFP-RJ45 installés"
    )
    cable_dac_u: Optional[int] = Field(
        default=None, ge=0, description="Câbles DAC installés"
    )
    coffret_12u_u: Optional[int] = Field(
        default=None, ge=0, description="Coffrets/baies 12U installés"
    )
    onduleur_u: Optional[int] = Field(
        default=None, ge=0, description="Onduleurs installés"
    )
    cable_elec_3x2_5_m: Optional[float] = Field(
        default=None, ge=0, description="Mètres de câble électrique 3x2,5 posés"
    )
    fiche_2p_t_u: Optional[int] = Field(
        default=None, ge=0, description="Fiches F 2P+T posées"
    )
    disjoncteur_2x16a_u: Optional[int] = Field(
        default=None, ge=0, description="Disjoncteurs 2x16A posés"
    )
    bandeau_elec_12p_u: Optional[int] = Field(
        default=None, ge=0, description="Bandeaux électriques 12P posés"
    )
    passe_cable_u: Optional[int] = Field(
        default=None, ge=0, description="Passe-câbles posés"
    )
    borne_2_5_u: Optional[int] = Field(
        default=None, ge=0, description="Bornes 2,5 posées"
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
    # --- la journée : heures et équipe ------------------------------------
    #
    # These three used to be `journal.CHEF_COLUMNS`: filled by a chef in the
    # dashboard, never written by extraction, never merged. The premise was
    # that a technician does not dictate them, and it was simply wrong — they
    # say "je suis entré à 7h, sorti à 8h du soir" in the voice note, and the
    # journal had nowhere to put it, so the sheet stayed empty while the
    # information sat in the transcript.
    #
    # Stored as spoken, normalized to HH:MM. Never inferred: a note that does
    # not give an hour leaves the cell empty rather than guessing a shift.
    heure_entree: Optional[str] = Field(
        default=None,
        description="Heure d'arrivée sur le chantier, format HH:MM. « entré à 7h » = 07:00",
    )
    heure_sortie: Optional[str] = Field(
        default=None,
        description="Heure de départ du chantier, format HH:MM. « sorti à 8h du soir » = 20:00",
    )
    equipe: Optional[str] = Field(
        default=None,
        description="Les personnes présentes, telles que nommées. « j'étais avec Hamid » = Hamid",
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
    # Le chantier tel qu'il a été *prononcé*, verbatim. Deliberately NOT in
    # DATA_FIELDS: `has_data` answers "is this a report?", and naming a site is
    # addressing, not work done — "je suis à la DGH" and nothing else must stay
    # `no_report_content`, or the pipeline would answer "✅ Rapport enregistré"
    # and open a journal row with every quantity blank. The name is resolved
    # against the `chantiers` table in journal.resolve_site, never trusted as a
    # tab name: a mis-transcription must land on the existing site, not create
    # a fourth spelling of it.
    chantier_mentionne: Optional[str] = Field(
        default=None,
        description="Nom du chantier tel qu'énoncé par le technicien, sinon null",
    )
    # The day the report is *about*, when the technician states it himself.
    #
    # 2026-08-19: a note opening « Salam 17-08-2026 » was filed under the 19th,
    # the day the pipeline happened to run it — a voice note sent late, or a
    # write replayed from `failed_writes` days after the fact, lands on the
    # wrong row and every per-day total moves with it. Extracted verbatim and
    # never guessed: `journal.resolve_date` normalizes it and falls back to the
    # transmitted date when it is unparseable, in the future, or too old.
    #
    # Not in `DATA_FIELDS`: dating a report is addressing, like naming the site,
    # not work done — « Salam 17-08-2026 » alone must stay `no_report_content`.
    date_declaree: Optional[str] = Field(
        default=None,
        description="Date énoncée dans le message (« Salam 17-08-2026 »), telle quelle, sinon null",
    )
    # --- réception de matériel ---------------------------------------------
    #
    # A bon de livraison is not a day's work, and until 2026-08-16 the image
    # prompt told the model to read one into the *installed* article columns —
    # so 500 m of cable delivered was booked as 500 m posed, inflating the very
    # number the bordereau's avancement and every stock warning are computed
    # from. Latent only because no article column had a value yet.
    #
    # `nature` must be set positively: absent means `pose`, so every existing
    # row, every voice note and every photo of a wall keeps behaving exactly as
    # before. A delivery is only ever a delivery because the model said so.
    nature: Optional[Literal["pose", "livraison"]] = Field(
        default=None,
        description="'livraison' uniquement pour un bon de livraison / une réception de matériel ; sinon null",
    )
    # Quantities *received*, keyed by the same field names as the quantities
    # installed — one vocabulary, already in both prompts, already validated.
    # A key the schema does not know raises rather than being dropped, the same
    # rule `etages` follows: the extraction chain then retries instead of
    # writing an invented article into the ledger.
    livraisons: Optional[Dict[str, float]] = Field(
        default=None,
        description="Quantités reçues par champ (cables_installes_m, pigtail_sc_u, …), pour un bon de livraison",
    )
    #: Articles the schema has no field for, as {désignation: quantité}.
    #:
    #: Added 2026-08-19 after a real report listed four double sockets, thirteen
    #: single ones, three surface-mounted, nine switches, one two-way switch and
    #: two electrical panels — forty items across eight article types — and
    #: every one of them was lost to prose, because none of the thirty-five
    #: quantity fields is an electrical socket, a switch or a panel. The model
    #: was behaving correctly: it is told never to invent, and there was nowhere
    #: to put them.
    #:
    #: Free text on purpose, unlike `livraisons`, which is validated against the
    #: known field names. The whole point is the article that is NOT known yet;
    #: validating it against the list would throw away exactly the information
    #: this field exists to carry. It is normalised and registered downstream,
    #: where a new column and a confirmation step give it a home.
    articles_libres: Optional[Dict[str, float]] = Field(
        default=None,
        description=(
            "Articles posés qui ne correspondent à AUCUN champ existant, "
            "{désignation courte au singulier: quantité}. "
            "INCLURE AUSSI les longueurs en mètres d'articles sans champ "
            "(chemin de câbles, câble électrique) — un chemin de câbles n'est "
            "PAS une goulotte. Additionner les mentions répétées du même "
            "article. Exemple : {\"prise double étanche encastrée\": 4, "
            "\"tableau électrique\": 2, \"chemin de câbles (m)\": 8}"
        ),
    )
    resume: str = Field(
        ..., description="Résumé professionnel en français (2-4 phrases)"
    )

    @field_validator("livraisons", mode="after")
    @classmethod
    def _known_articles(cls, v):
        """Every delivered line must name a quantity field this schema tracks.

        Unknown key raises, like an unrecognized étage: a ledger entry against
        an article nobody can join to a contract line is worse than a visible
        failure, because it silently under-reports what is on site.
        """
        if not v:
            return None
        unknown = sorted(k for k in v if k not in DELIVERABLE_FIELDS)
        if unknown:
            raise ValueError(f"article inconnu dans livraisons: {', '.join(unknown)}")
        kept = {k: float(q) for k, q in v.items() if q is not None and float(q) > 0}
        return kept or None

    @field_validator("etages", "ailes", "locaux_techniques", mode="before")
    @classmethod
    def _wrap_single(cls, v):
        # "RDC, E1, E2" and "RDC" are both things the model emits for a field
        # the file itself writes as a comma-joined string.
        #
        # The null-ish check is repeated here on purpose. `_null_strings_to_none`
        # above is a wildcard validator, but pydantic runs a field-specific
        # before-validator FIRST, so it never protected these three fields: a
        # Groq model emitting the *string* "null" for an unmentioned floor got
        # wrapped into ["null"] and then raised "étage inconnu: 'null'".
        # Loud rather than silent, so no wrong row — but it burned that model's
        # attempt on every report that does not name a floor, which is most of
        # them, and quietly defeated the vendor-alternation the free tiers are
        # split across. Found by the 2026-08-15 text benchmark, where it failed
        # 13 of 20 cases on both Llama models.
        if isinstance(v, str) and _is_nullish(v):
            return None
        if isinstance(v, str):
            v = [part for part in (p.strip() for p in v.split(",")) if part]
        if isinstance(v, list):
            kept = [x for x in v if not (isinstance(x, str) and _is_nullish(x))]
            return kept or None
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
    # Echoed straight back so n8n can rejoin this answer to the message that
    # caused it. Its own `pairedItem` chain does not survive the media branch
    # (media URL + binary download), which is why a WhatsApp voice note used to
    # be answered without the quoted original.
    correlation_id: Optional[str] = Field(
        default=None, description="Trace id reçu à l'appel, renvoyé tel quel (jointure n8n)"
    )
    message_id: Optional[str] = Field(
        default=None, description="Clé du message reçue à l'appel, renvoyée telle quelle (jointure n8n)"
    )
    # Where this report is headed, resolved read-only so the reply can say it.
    # The write happens later in /journal (reply-first ordering), so without
    # this the technician is told "Rapport enregistré" and never learns which
    # site it was filed under — and a wrong site is the one error that silently
    # moves a whole day onto the director's wrong sheet.
    chantier: Optional[str] = Field(
        default=None, description="Chantier retenu pour ce message (résolution en lecture seule)"
    )
    chantier_source: Optional[str] = Field(
        default=None,
        description=(
            "D'où vient ce chantier : voix | repris | org | nouveau | aucun. "
            "n8n s'en sert pour qualifier la ligne « Chantier » de la réponse."
        ),
    )
