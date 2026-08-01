"""Route / smoke tests via Flask's test client (test plan section 2.5)."""


def test_dashboard_ok(auth_client):  # W1
    assert auth_client.get("/").status_code == 200


def test_subjects_page_ok(auth_client):
    assert auth_client.get("/subjects").status_code == 200


def test_create_subject_appears(auth_client):  # W2
    auth_client.post("/subjects", data={"name": "Algorithms"}, follow_redirects=True)
    body = auth_client.get("/subjects").get_data(as_text=True)
    assert "Algorithms" in body


def test_subject_detail_and_chapter_flow(auth_client):  # W3, W4
    auth_client.post("/subjects", data={"name": "Networks"}, follow_redirects=True)
    detail = auth_client.get("/subjects/1")
    assert detail.status_code == 200

    auth_client.post("/subjects/1/modules", data={"name": "TCP"}, follow_redirects=True)
    auth_client.post(
        "/modules/1/chapters",
        data={"title": "Handshake", "kind": "video", "duration_minutes": "90"},
        follow_redirects=True,
    )
    page = auth_client.get("/subjects/1").get_data(as_text=True)
    assert "Handshake" in page
    assert "1h 30m" in page  # 90 minutes displayed as hours + minutes

    auth_client.post(
        "/chapters/1/completion",
        data={"completed_hours": "0", "completed_minutes": "45"},
        follow_redirects=True,
    )
    page = auth_client.get("/subjects/1").get_data(as_text=True)
    assert "45m of 1h 30m" in page  # 45 min completed of a 90-min chapter


def test_completion_update_returns_to_originating_page(auth_client):
    # Saving completion from /today (or /week) should return there, not jump to
    # the subject detail page. We simulate the browser sending a Referer header.
    auth_client.post("/subjects", data={"name": "S"}, follow_redirects=True)
    auth_client.post("/subjects/1/modules", data={"name": "M"}, follow_redirects=True)
    auth_client.post(
        "/modules/1/chapters",
        data={"title": "C", "kind": "video", "duration_minutes": "60"},
        follow_redirects=True,
    )
    for origin in ("/today", "/week"):
        resp = auth_client.post(
            "/chapters/1/completion",
            data={"completed_hours": "0", "completed_minutes": "30"},
            headers={"Referer": f"http://localhost{origin}"},
        )
        assert resp.status_code == 302
        assert resp.headers["Location"].endswith(origin)


def test_today_and_week_ok(auth_client):  # W5
    assert auth_client.get("/today").status_code == 200
    assert auth_client.get("/week").status_code == 200


def test_missing_subject_404(auth_client):
    assert auth_client.get("/subjects/999").status_code == 404


def test_protected_routes_redirect_when_logged_out(client):
    for path in ["/", "/subjects", "/today", "/week"]:
        resp = client.get(path)
        assert resp.status_code == 302
        assert "/login" in resp.headers["Location"]


def _make_chapter(auth_client, duration="60"):
    auth_client.post("/subjects", data={"name": "S"}, follow_redirects=True)
    auth_client.post("/subjects/1/modules", data={"name": "M"}, follow_redirects=True)
    auth_client.post(
        "/modules/1/chapters",
        data={"title": "C", "kind": "video", "duration_minutes": duration},
        follow_redirects=True,
    )


def test_subject_page_completed_is_readonly(auth_client):
    _make_chapter(auth_client)
    page = auth_client.get("/subjects/1").get_data(as_text=True)
    assert "completed-readonly" in page              # read-only display present
    assert 'name="completed_hours"' not in page      # no editable completion input
    assert "done-toggle" not in page                 # no Done checkbox here


def test_plan_page_has_editable_completion(auth_client):
    from datetime import date
    _make_chapter(auth_client)
    auth_client.post("/chapters/1/plan", data={"planned_date": date.today().isoformat()},
                     follow_redirects=True)
    page = auth_client.get("/today").get_data(as_text=True)
    assert 'name="completed_hours"' in page          # editable on the plan page
    assert "done-toggle" in page                     # Done checkbox present


def test_completion_ajax_returns_json(auth_client):
    _make_chapter(auth_client, duration="120")
    resp = auth_client.post(
        "/chapters/1/completion",
        data={"completed_hours": "1", "completed_minutes": "30"},
        headers={"X-Requested-With": "XMLHttpRequest"},
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["completed_minutes"] == 90
    assert data["completed_hm"] == "1h 30m"
    assert data["is_done"] is False


def test_plan_requires_a_date(auth_client):
    # Submitting the plan form without a date must NOT assign (previously it
    # silently defaulted to today).
    _make_chapter(auth_client)
    auth_client.post("/chapters/1/plan", data={}, follow_redirects=True)
    from datetime import date
    # The chapter should not appear in today's plan.
    page = auth_client.get("/today").get_data(as_text=True)
    assert "Today's plan" in page
    # No plan means nothing planned today.
    assert page.count("plan-item") == 0
    # And an error is flashed.
    resp = auth_client.post("/chapters/1/plan", data={"planned_date": ""})
    assert resp.status_code == 302
    followed = auth_client.get("/today").get_data(as_text=True)
    assert "Pick a date to plan" in followed


def test_plan_with_a_date_assigns(auth_client):
    from datetime import date
    _make_chapter(auth_client)
    auth_client.post("/chapters/1/plan", data={"planned_date": date.today().isoformat()},
                     follow_redirects=True)
    page = auth_client.get("/today").get_data(as_text=True)
    assert page.count("plan-item") >= 1        # now it's planned for today


def test_html_pages_are_not_cached(auth_client):
    # Dynamic HTML must not be cached, so the browser never shows a stale view.
    resp = auth_client.get("/today")
    assert resp.headers.get("Cache-Control") == "no-store"
    # Static assets keep their normal (cacheable) headers.
    css = auth_client.get("/static/style.css")
    assert css.headers.get("Cache-Control") != "no-store"


def test_theme_toggle_present_on_every_page(client):
    # The base layout ships the toggle button + the no-flash theme script.
    page = client.get("/login").get_data(as_text=True)
    assert 'id="themeToggle"' in page
    assert "data-theme" in page              # early theme-setting script
    assert "localStorage.getItem(\"theme\")" in page
