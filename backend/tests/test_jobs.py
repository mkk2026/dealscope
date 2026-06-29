from app.pipeline.jobs import _to_doc, detect_boards
from app.pipeline.models import SourceKind


def test_detect_boards_finds_all_three():
    html = ("boards.greenhouse.io/acme jobs.lever.co/beta "
            "jobs.ashbyhq.com/Gamma")
    boards = detect_boards(html)
    assert boards == {"greenhouse": "acme", "lever": "beta", "ashby": "Gamma"}


def test_detect_boards_empty():
    assert detect_boards("nothing here") == {}


def test_fetch_failure_is_not_zero_roles():
    # The critical one: a failed fetch must NOT read as a hiring signal.
    doc = _to_doc("lever", "beta", [], ok=False)
    assert doc.kind == SourceKind.JOBS
    assert doc.meta["open_roles"] is None
    assert doc.meta["fetch_ok"] is False
    assert "unavailable" in doc.title.lower()


def test_genuine_zero_roles_is_reported_as_zero():
    doc = _to_doc("lever", "beta", [], ok=True)
    assert doc.meta["open_roles"] == 0
    assert doc.meta["fetch_ok"] is True


def test_roles_rendered_with_url():
    doc = _to_doc("greenhouse", "acme", ["Eng — Remote", "PM — NY"], ok=True)
    assert doc.meta["open_roles"] == 2
    assert "boards.greenhouse.io/acme" in doc.url
    assert "Eng — Remote" in doc.text
