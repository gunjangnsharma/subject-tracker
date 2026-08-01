"""Reordering chapters within a module (position column + up/down moves).

Covers the pure index math, the service rule, the legacy-data path (existing
databases that predate `Chapter.position`), ownership isolation, the route, and
that a backup round-trip preserves the order.
"""

from __future__ import annotations

import json

import pytest
from sqlalchemy import inspect, text

from tracker import domain
from tracker.database import Database
from tracker.maintenance import backfill_chapter_positions
from tracker.models import Chapter
from tracker.schema import ensure_columns
from tracker.services.auth_service import AuthService
from tracker.services.backup_service import BackupService
from tracker.services.subject_service import SubjectService

TITLES = ["First", "Second", "Third", "Fourth"]


@pytest.fixture
def module_with_chapters(session, user_id):
    """A module holding four chapters in a known order."""
    service = SubjectService(session, user_id)
    subject = service.add_subject("Maths")
    module = service.add_module(subject.id, "Algebra")
    for title in TITLES:
        service.add_chapter(module.id, title, "video", 60)
    return service, module


def titles(service, module_id):
    return [c.title for c in service.list_module_chapters(module_id)]


# --- Pure domain math -------------------------------------------------------

def test_swap_index_moves_one_step():
    assert domain.swap_index(2, domain.MOVE_UP, 5) == 1
    assert domain.swap_index(2, domain.MOVE_DOWN, 5) == 3


def test_swap_index_returns_none_at_the_ends():
    # First can't go up; last can't go down — "no room" is not an error.
    assert domain.swap_index(0, domain.MOVE_UP, 4) is None
    assert domain.swap_index(3, domain.MOVE_DOWN, 4) is None
    assert domain.swap_index(0, domain.MOVE_DOWN, 1) is None   # single item


def test_swap_index_rejects_bad_direction():
    with pytest.raises(ValueError):
        domain.swap_index(0, "sideways", 3)


def test_swap_index_out_of_range_is_none():
    assert domain.swap_index(9, domain.MOVE_UP, 3) is None
    assert domain.swap_index(-1, domain.MOVE_DOWN, 3) is None


# --- Service ----------------------------------------------------------------

def test_new_chapters_get_sequential_positions(module_with_chapters):
    service, module = module_with_chapters
    chapters = service.list_module_chapters(module.id)
    assert [c.position for c in chapters] == [0, 1, 2, 3]
    assert [c.title for c in chapters] == TITLES


def test_move_down_swaps_with_next(module_with_chapters):
    service, module = module_with_chapters
    first = service.list_module_chapters(module.id)[0]
    assert service.move_chapter(first.id, domain.MOVE_DOWN) is True
    assert titles(service, module.id) == ["Second", "First", "Third", "Fourth"]


def test_move_up_swaps_with_previous(module_with_chapters):
    service, module = module_with_chapters
    third = service.list_module_chapters(module.id)[2]
    assert service.move_chapter(third.id, domain.MOVE_UP) is True
    assert titles(service, module.id) == ["First", "Third", "Second", "Fourth"]


def test_move_up_at_top_is_a_noop(module_with_chapters):
    service, module = module_with_chapters
    first = service.list_module_chapters(module.id)[0]
    assert service.move_chapter(first.id, domain.MOVE_UP) is False
    assert titles(service, module.id) == TITLES


def test_move_down_at_bottom_is_a_noop(module_with_chapters):
    service, module = module_with_chapters
    last = service.list_module_chapters(module.id)[-1]
    assert service.move_chapter(last.id, domain.MOVE_DOWN) is False
    assert titles(service, module.id) == TITLES


def test_move_is_reversible(module_with_chapters):
    service, module = module_with_chapters
    chapter = service.list_module_chapters(module.id)[1]
    service.move_chapter(chapter.id, domain.MOVE_DOWN)
    service.move_chapter(chapter.id, domain.MOVE_UP)
    assert titles(service, module.id) == TITLES


def test_positions_stay_contiguous_after_moves(module_with_chapters):
    service, module = module_with_chapters
    chapter = service.list_module_chapters(module.id)[0]
    service.move_chapter(chapter.id, domain.MOVE_DOWN)
    service.move_chapter(chapter.id, domain.MOVE_DOWN)
    positions = [c.position for c in service.list_module_chapters(module.id)]
    assert positions == [0, 1, 2, 3]     # no gaps, no duplicates


def test_move_rejects_bad_direction(module_with_chapters):
    service, module = module_with_chapters
    chapter = service.list_module_chapters(module.id)[0]
    with pytest.raises(ValueError):
        service.move_chapter(chapter.id, "sideways")


def test_move_unknown_chapter_raises(session, user_id):
    with pytest.raises(ValueError):
        SubjectService(session, user_id).move_chapter(9999, domain.MOVE_DOWN)


def test_reorder_is_confined_to_one_module(session, user_id):
    """Moving a chapter never pulls it into a sibling module."""
    service = SubjectService(session, user_id)
    subject = service.add_subject("Physics")
    first = service.add_module(subject.id, "Mechanics")
    second = service.add_module(subject.id, "Optics")
    a = service.add_chapter(first.id, "Forces", "video", 30)
    service.add_chapter(first.id, "Momentum", "video", 30)
    b = service.add_chapter(second.id, "Lenses", "video", 30)

    # Pushing the last chapter of module one down does not move it to module two.
    service.move_chapter(a.id, domain.MOVE_DOWN)
    service.move_chapter(a.id, domain.MOVE_DOWN)
    assert titles(service, first.id) == ["Momentum", "Forces"]
    assert titles(service, second.id) == ["Lenses"]
    assert service.get_chapter(a.id).module_id == first.id
    assert service.get_chapter(b.id).module_id == second.id


def test_deleting_a_chapter_leaves_the_rest_ordered(module_with_chapters):
    service, module = module_with_chapters
    second = service.list_module_chapters(module.id)[1]
    service.delete_chapter(second.id)
    assert titles(service, module.id) == ["First", "Third", "Fourth"]
    # A gap in positions is harmless: moves renumber, and order still holds.
    moved = service.list_module_chapters(module.id)[-1]
    service.move_chapter(moved.id, domain.MOVE_UP)
    assert titles(service, module.id) == ["First", "Fourth", "Third"]


def test_new_chapter_lands_at_the_end_after_reordering(module_with_chapters):
    service, module = module_with_chapters
    first = service.list_module_chapters(module.id)[0]
    service.move_chapter(first.id, domain.MOVE_DOWN)
    service.add_chapter(module.id, "Latest", "video", 45)
    assert titles(service, module.id)[-1] == "Latest"


# --- Isolation --------------------------------------------------------------

def test_cannot_reorder_another_users_chapter(session, user_id):
    other = AuthService(session).register("intruder", "secret123").id
    mine = SubjectService(session, user_id)
    subject = mine.add_subject("Private")
    module = mine.add_module(subject.id, "Module")
    a = mine.add_chapter(module.id, "One", "video", 30)
    mine.add_chapter(module.id, "Two", "video", 30)

    # The other user's repository reports the chapter as missing -> ValueError.
    with pytest.raises(ValueError):
        SubjectService(session, other).move_chapter(a.id, domain.MOVE_DOWN)
    assert titles(mine, module.id) == ["One", "Two"]     # order untouched


# --- Legacy databases (no position column / all positions 0) ----------------

def test_ensure_columns_adds_position_to_an_old_database(tmp_path):
    """A database created before `position` existed gains the column."""
    url = f"sqlite:///{tmp_path/'legacy.db'}"
    db = Database(url)
    # Hand-build the pre-feature `chapters` table (no `position`), exactly as an
    # older version of the app would have left it, then add a row to it.
    with db.engine.begin() as conn:
        conn.execute(text(
            "CREATE TABLE chapters ("
            " id INTEGER NOT NULL PRIMARY KEY,"
            " module_id INTEGER NOT NULL,"
            " title VARCHAR(300) NOT NULL,"
            " kind VARCHAR(5),"
            " duration_minutes INTEGER,"
            " completed_minutes INTEGER)"
        ))
        conn.execute(text(
            "INSERT INTO chapters (id, module_id, title, kind, duration_minutes,"
            " completed_minutes) VALUES (1, 1, 'Legacy chapter', 'video', 60, 30)"
        ))
    assert "position" not in {c["name"] for c in inspect(db.engine).get_columns("chapters")}

    # create_all() would leave this table alone; ensure_columns patches it.
    added = db.create_all()

    assert [(a.table, a.column) for a in added] == [("chapters", "position")]
    columns = {c["name"] for c in inspect(db.engine).get_columns("chapters")}
    assert "position" in columns
    # The existing row survived and defaulted to 0 (and is now queryable).
    session = db.Session()
    chapter = session.get(Chapter, 1)
    assert chapter.title == "Legacy chapter"
    assert chapter.position == 0
    assert chapter.completed_minutes == 30
    db.remove()


def test_ensure_columns_is_idempotent(tmp_path):
    url = f"sqlite:///{tmp_path/'fresh.db'}"
    db = Database(url)
    db.create_all()
    assert ensure_columns(db.engine) == []      # nothing missing
    assert ensure_columns(db.engine) == []      # and still nothing on a re-run
    db.remove()


def test_legacy_rows_all_at_zero_keep_insertion_order(session, user_id):
    """Rows backfilled to 0 stay in id order thanks to the (position, id) sort."""
    service = SubjectService(session, user_id)
    subject = service.add_subject("Legacy")
    module = service.add_module(subject.id, "Old module")
    for title in TITLES:
        service.add_chapter(module.id, title, "video", 30)
    # Emulate pre-feature data: every row shares position 0.
    for chapter in service.list_module_chapters(module.id):
        chapter.position = 0
    session.commit()

    assert titles(service, module.id) == TITLES


def test_backfill_renumbers_legacy_positions(session, user_id):
    service = SubjectService(session, user_id)
    subject = service.add_subject("Legacy")
    module = service.add_module(subject.id, "Old module")
    for title in TITLES:
        service.add_chapter(module.id, title, "video", 30)
    for chapter in service.list_module_chapters(module.id):
        chapter.position = 0            # pre-feature state
    session.commit()

    result = backfill_chapter_positions(session)
    session.commit()

    assert result.modules_affected == 1
    assert result.chapters_renumbered == 3          # the first was already 0
    assert [c.position for c in service.list_module_chapters(module.id)] == [0, 1, 2, 3]
    assert titles(service, module.id) == TITLES     # order preserved


def test_backfill_is_idempotent(module_with_chapters, session):
    service, module = module_with_chapters
    first = backfill_chapter_positions(session)     # already 0..n-1
    session.commit()
    assert first.modules_affected == 0
    assert first.chapters_renumbered == 0
    assert titles(service, module.id) == TITLES


def test_move_works_on_legacy_all_zero_positions(session, user_id):
    """The first move repairs duplicate positions instead of doing nothing."""
    service = SubjectService(session, user_id)
    subject = service.add_subject("Legacy")
    module = service.add_module(subject.id, "Old module")
    for title in TITLES:
        service.add_chapter(module.id, title, "video", 30)
    for chapter in service.list_module_chapters(module.id):
        chapter.position = 0
    session.commit()

    first = service.list_module_chapters(module.id)[0]
    assert service.move_chapter(first.id, domain.MOVE_DOWN) is True
    assert titles(service, module.id) == ["Second", "First", "Third", "Fourth"]
    assert [c.position for c in service.list_module_chapters(module.id)] == [0, 1, 2, 3]


# --- Route ------------------------------------------------------------------

def _first_module(client):
    """Create a subject/module/chapters through the app; return (subject_id, ids)."""
    client.post("/subjects", data={"name": "Course"}, follow_redirects=True)
    page = client.get("/subjects").get_data(as_text=True)
    subject_id = int(page.split("/subjects/")[1].split('"')[0])
    client.post(f"/subjects/{subject_id}/modules", data={"name": "Unit"}, follow_redirects=True)
    detail = client.get(f"/subjects/{subject_id}").get_data(as_text=True)
    module_id = int(detail.split("/modules/")[1].split("/")[0])
    for title in ("Alpha", "Beta", "Gamma"):
        client.post(
            f"/modules/{module_id}/chapters",
            data={"title": title, "kind": "video", "duration_minutes": "30"},
            follow_redirects=True,
        )
    return subject_id, module_id


def _order_on_page(client, subject_id):
    html = client.get(f"/subjects/{subject_id}").get_data(as_text=True)
    return [t for t in ("Alpha", "Beta", "Gamma") if t in html], html


def test_move_route_reorders_and_redirects(auth_client):
    subject_id, module_id = _first_module(auth_client)
    _, html = _order_on_page(auth_client, subject_id)
    chapter_ids = [int(s.split('"')[0]) for s in html.split('data-chapter-row="')[1:]]

    response = auth_client.post(
        f"/chapters/{chapter_ids[0]}/move", data={"direction": "down"}
    )
    assert response.status_code == 302

    html = auth_client.get(f"/subjects/{subject_id}").get_data(as_text=True)
    new_ids = [int(s.split('"')[0]) for s in html.split('data-chapter-row="')[1:]]
    assert new_ids[:2] == [chapter_ids[1], chapter_ids[0]]


def test_move_route_ajax_returns_new_order(auth_client):
    subject_id, module_id = _first_module(auth_client)
    _, html = _order_on_page(auth_client, subject_id)
    chapter_ids = [int(s.split('"')[0]) for s in html.split('data-chapter-row="')[1:]]

    response = auth_client.post(
        f"/chapters/{chapter_ids[2]}/move",
        data={"direction": "up"},
        headers={"X-Requested-With": "XMLHttpRequest"},
    )
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["moved"] is True
    assert payload["module_id"] == module_id
    assert payload["chapter_ids"] == [chapter_ids[0], chapter_ids[2], chapter_ids[1]]


def test_move_route_reports_noop_without_changing_anything(auth_client):
    subject_id, _ = _first_module(auth_client)
    _, html = _order_on_page(auth_client, subject_id)
    chapter_ids = [int(s.split('"')[0]) for s in html.split('data-chapter-row="')[1:]]

    response = auth_client.post(
        f"/chapters/{chapter_ids[0]}/move",
        data={"direction": "up"},                      # already first
        headers={"X-Requested-With": "XMLHttpRequest"},
    )
    payload = response.get_json()
    assert payload["moved"] is False
    assert payload["chapter_ids"] == chapter_ids


def test_move_route_rejects_bad_direction(auth_client):
    subject_id, _ = _first_module(auth_client)
    _, html = _order_on_page(auth_client, subject_id)
    chapter_id = int(html.split('data-chapter-row="')[1].split('"')[0])
    assert auth_client.post(
        f"/chapters/{chapter_id}/move", data={"direction": "sideways"}
    ).status_code == 400


def test_move_route_404s_for_unknown_chapter(auth_client):
    assert auth_client.post(
        "/chapters/9999/move", data={"direction": "up"}
    ).status_code == 404


def test_move_route_requires_login(client):
    assert client.post("/chapters/1/move", data={"direction": "up"}).status_code == 302


def test_subject_page_renders_reorder_buttons(auth_client):
    subject_id, _ = _first_module(auth_client)
    html = auth_client.get(f"/subjects/{subject_id}").get_data(as_text=True)
    assert 'class="reorder"' in html
    assert 'data-direction="up"' in html
    assert 'data-direction="down"' in html
    # The first row's up button and the last row's down button are disabled.
    rows = html.split('data-chapter-row="')[1:]
    assert 'data-direction="up"' in rows[0] and "disabled" in rows[0].split("</td>")[0]
    assert "disabled" in rows[-1].split("</td>")[0]


# --- Backup round-trip ------------------------------------------------------

def test_export_lists_chapters_in_display_order(session, user_id, module_with_chapters):
    service, module = module_with_chapters
    first = service.list_module_chapters(module.id)[0]
    service.move_chapter(first.id, domain.MOVE_DOWN)

    data = BackupService(session, user_id).export_data()
    exported = [c["title"] for c in data["subjects"][0]["modules"][0]["chapters"]]
    assert exported == ["Second", "First", "Third", "Fourth"]


def test_import_preserves_chapter_order(session, user_id, module_with_chapters):
    """Array order carries the ordering: re-import reproduces it exactly."""
    service, module = module_with_chapters
    chapter = service.list_module_chapters(module.id)[3]
    service.move_chapter(chapter.id, domain.MOVE_UP)
    expected = titles(service, module.id)

    payload = json.loads(json.dumps(BackupService(session, user_id).export_data()))
    other = AuthService(session).register("restored", "secret123").id
    BackupService(session, other).import_data(payload)

    restored = SubjectService(session, other)
    restored_module = restored.list_subjects()[0].modules[0]
    assert [c.title for c in restored_module.chapters] == expected
    assert [c.position for c in restored_module.chapters] == [0, 1, 2, 3]


def test_reexport_after_import_is_identical(session, user_id, module_with_chapters):
    service, module = module_with_chapters
    service.move_chapter(service.list_module_chapters(module.id)[0].id, domain.MOVE_DOWN)

    original = BackupService(session, user_id).export_data()
    other = AuthService(session).register("copy", "secret123").id
    BackupService(session, other).import_data(json.loads(json.dumps(original)))
    roundtripped = BackupService(session, other).export_data()

    assert roundtripped["subjects"] == original["subjects"]
