"""Mail rendering and the SMTP conversation (`app/mailer.py`).

Nothing here opens a socket: `smtplib.SMTP` is replaced by a recorder, so the
tests cover the two things that have actually gone wrong in this module — the
partial-refusal contract (`send` must return what the server *took*, not what
we asked it to take) and the HTML the reader ends up looking at.
"""
import smtplib

import pytest

from app import mailer


# --- _escape / _is_figure --------------------------------------------------

def test_escape_neutralises_markup_from_a_report_body():
    assert mailer._escape('<b>a</b> & "b"') == "&lt;b&gt;a&lt;/b&gt; &amp; &quot;b&quot;"


@pytest.mark.parametrize("value,figure", [
    ("12", True),
    ("3 jours avant l'échéance", True),      # still a reading
    ("21/08/2026", True),
    ("Prévoir le matériel fibre pour la semaine prochaine", False),  # prose
    ("deux\nlignes", False),
    ("x" * 29, False),                        # too long for one mono line
])
def test_a_figure_is_decided_by_shape_not_by_type(value, figure):
    assert mailer._is_figure(value) is figure


# --- render_rich_text ------------------------------------------------------

def test_headings_bullets_and_paragraphs_are_the_three_shapes_recognised():
    html = mailer.render_rich_text(
        "## Synthèse\n"
        "\n"
        "- 120 m de goulottes\n"
        "* deuxième puce\n"
        "• troisième puce\n"
        "Une phrase ordinaire.\n"
    )
    assert "SYNTH" in html.upper()
    assert html.count("&bull;") == 3
    assert "120 m de goulottes" in html
    assert "Une phrase ordinaire." in html
    # Not a Markdown parser: the markers themselves never survive.
    assert "##" not in html


def test_rich_text_escapes_what_the_model_wrote():
    assert "<script>" not in mailer.render_rich_text("- <script>alert(1)</script>")


# --- render_document -------------------------------------------------------

def _doc(**kwargs):
    base = {"title": "Rapport", "lead": "Une journée.", "rows": []}
    return mailer.render_document(**{**base, **kwargs})


def test_figures_go_to_the_ledger_and_prose_gets_its_own_band():
    html = _doc(rows=[
        ("Rapports", "12"),
        ("Notes", "Prévoir le matériel fibre pour la semaine prochaine"),
        ("Vide", ""),          # falsy values are dropped entirely
    ])
    assert "CHIFFRES" in html.upper()
    assert "NOTES" in html.upper()
    assert "Prévoir le matériel" in html
    assert "Vide" not in html


def test_a_document_with_no_rows_draws_neither_band():
    html = _doc()
    assert "CHIFFRES" not in html.upper()
    # The lead still gets its "Objet" band in the plain path.
    assert "OBJET" in html.upper()


def test_the_rich_path_writes_its_own_headings_instead_of_an_objet_band():
    html = _doc(lead="## Synthèse\n- une puce", rich=True)
    assert "OBJET" not in html.upper()
    assert "&bull;" in html


def test_the_call_to_action_is_a_bulletproof_button():
    html = _doc(cta=("Ouvrir", "https://dash.example/#/daily"))
    assert 'href="https://dash.example/#/daily"' in html
    assert ">Ouvrir</a>" in html


def test_the_footer_and_the_period_stamp_are_optional():
    plain = _doc()
    assert "cid:" in plain  # the mark always travels
    full = _doc(footer="Envoyé automatiquement.", caption="Exemple")
    assert "Envoyé automatiquement." in full
    assert "EXEMPLE" in full


def test_the_short_banner_drops_the_positioning_line():
    assert "CÂBLAGE" in _doc(banner=True)
    assert "CÂBLAGE" not in _doc(banner=False)


def test_the_title_is_escaped_at_render_time_not_at_the_call_site():
    assert "<img onerror" not in _doc(title='<img onerror=x>')


# --- logo_png --------------------------------------------------------------

def test_a_missing_mark_costs_the_image_never_the_message(monkeypatch, tmp_path, capsys):
    mailer.logo_png.cache_clear()
    monkeypatch.setattr(mailer, "_LOGO_PATH", tmp_path / "gone.png")
    try:
        assert mailer.logo_png() is None
        assert "logo unavailable" in capsys.readouterr().out
    finally:
        mailer.logo_png.cache_clear()


def test_the_real_mark_is_readable_and_cached():
    mailer.logo_png.cache_clear()
    blob = mailer.logo_png()
    assert blob
    assert blob[:4] == b"\x89PNG"
    assert mailer.logo_png() is blob


# --- sample_report ---------------------------------------------------------

def test_the_test_probe_sends_the_shape_of_a_real_report(monkeypatch):
    monkeypatch.setattr(mailer.settings, "dashboard_url", "https://dash.example/")
    subject, html = mailer.sample_report("chef@example.com")
    assert "test de notification" in subject
    assert "chef@example.com" in html
    # The deep link has no double slash: dashboard_url is rstrip'd.
    assert "https://dash.example/#/daily?date=" in html
    # Randomised on purpose — a fixed set would be read as today's real data.
    assert "fictifs" in html


# --- _compose --------------------------------------------------------------

def _parts(msg):
    return [p.get_content_type() for p in msg.walk()]


def test_a_plain_message_carries_no_alternative():
    msg = mailer._compose(["a@example.com"], "Sujet", "Texte", False, None, ())
    assert msg["To"] == "a@example.com"
    assert _parts(msg) == ["text/plain"]


def test_html_true_without_a_body_keeps_the_line_breaks():
    msg = mailer._compose(["a@example.com"], "S", "l1\nl2", True, None, ())
    assert "text/html" in _parts(msg)
    html = list(msg.walk())[-1].get_content()
    assert "l1<br>l2" in html


def test_the_mark_is_attached_only_when_the_html_references_it():
    with_mark = mailer._compose(["a@example.com"], "S", "t", False,
                                f'<img src="cid:{mailer.LOGO_CID}">', ())
    assert "image/png" in _parts(with_mark)

    without = mailer._compose(["a@example.com"], "S", "t", False, "<p>plain</p>", ())
    assert "image/png" not in _parts(without)


def test_an_unreadable_mark_still_sends_the_message(monkeypatch):
    monkeypatch.setattr(mailer, "logo_png", lambda: None)
    msg = mailer._compose(["a@example.com"], "S", "t", False,
                          f'<img src="cid:{mailer.LOGO_CID}">', ())
    assert "image/png" not in _parts(msg)


def test_attachments_land_after_the_alternatives_with_their_mime_split():
    msg = mailer._compose(
        ["a@example.com"], "S", "t", False, "<p>x</p>",
        [("rapport.docx", b"PK", "application/vnd.openxmlformats-officedocument"
                                 ".wordprocessingml.document"),
         ("brut.bin", b"\x00", "")],
    )
    names = [p.get_filename() for p in msg.walk() if p.get_filename()]
    assert names == ["rapport.docx", "brut.bin"]
    # An empty mime falls back rather than producing a malformed header.
    binary = next(p for p in msg.walk() if p.get_filename() == "brut.bin")
    assert binary.get_content_type() == "application/octet-stream"


# --- send ------------------------------------------------------------------

class FakeSMTP:
    """Records the conversation. `refused` mimics smtplib's partial answer."""

    instances = []

    def __init__(self, host, port, timeout=0):
        self.host, self.port, self.timeout = host, port, timeout
        self.logged_in = None
        self.sent = None
        self.refused = {}
        FakeSMTP.instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return False

    def starttls(self):
        self.tls = True

    def login(self, user, password):
        self.logged_in = (user, password)

    def send_message(self, msg):
        self.sent = msg
        return self.refused


@pytest.fixture
def smtp(monkeypatch):
    FakeSMTP.instances = []
    monkeypatch.setattr(mailer.settings, "smtp_user", "bot@example.com")
    monkeypatch.setattr(mailer.settings, "smtp_password", "app-password")
    monkeypatch.setattr(mailer.settings, "smtp_host", "smtp.example.com")
    monkeypatch.setattr(mailer.settings, "smtp_port", 587)
    monkeypatch.setattr(smtplib, "SMTP", FakeSMTP)
    return FakeSMTP


def test_send_returns_every_accepted_address(smtp):
    out = mailer.send([" a@example.com ", "b@example.com"], "S", "T")
    assert out == ["a@example.com", "b@example.com"]
    conn = smtp.instances[0]
    assert conn.tls is True
    assert conn.logged_in == ("bot@example.com", "app-password")


def test_a_refused_address_is_dropped_from_the_answer(smtp, capsys, monkeypatch):
    """The caller stores this list as `sent_to`. A refused chef listed there is
    a chef who silently stops receiving reports."""
    class Refusing(FakeSMTP):
        def send_message(self, msg):
            return {"b@example.com": (550, b"no such user")}

    monkeypatch.setattr(smtplib, "SMTP", Refusing)
    out = mailer.send(["a@example.com", "b@example.com"], "S", "T")
    assert out == ["a@example.com"]
    assert "b@example.com (550)" in capsys.readouterr().out


def test_send_refuses_an_empty_recipient_list(smtp):
    with pytest.raises(mailer.MailError, match="aucun destinataire"):
        mailer.send(["  ", ""], "S", "T")


def test_send_says_which_settings_are_missing(monkeypatch):
    monkeypatch.setattr(mailer.settings, "smtp_user", "")
    monkeypatch.setattr(mailer.settings, "smtp_password", "")
    with pytest.raises(mailer.MailError, match="SMTP_USER and SMTP_PASSWORD"):
        mailer.send(["a@example.com"], "S", "T")


def test_any_smtp_failure_becomes_one_error_type(smtp, monkeypatch):
    class Broken(FakeSMTP):
        def login(self, user, password):
            raise smtplib.SMTPAuthenticationError(535, b"bad credentials")

    monkeypatch.setattr(smtplib, "SMTP", Broken)
    with pytest.raises(mailer.MailError, match="envoi échoué"):
        mailer.send(["a@example.com"], "S", "T")


def test_the_from_header_falls_back_to_the_login_user(smtp, monkeypatch):
    monkeypatch.setattr(mailer.settings, "smtp_from", "")
    mailer.send(["a@example.com"], "S", "T")
    assert smtp.instances[0].sent["From"] == "bot@example.com"
