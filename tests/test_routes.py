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
    assert "1.5h" in page  # 90 minutes displayed as hours

    auth_client.post("/chapters/1/completion", data={"completion": "5"}, follow_redirects=True)
    page = auth_client.get("/subjects/1").get_data(as_text=True)
    assert "0.75h done" in page  # 90 * 5/10 = 45 min = 0.75h


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
            data={"completion": "3"},
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


def test_theme_toggle_present_on_every_page(client):
    # The base layout ships the toggle button + the no-flash theme script.
    page = client.get("/login").get_data(as_text=True)
    assert 'id="themeToggle"' in page
    assert "data-theme" in page              # early theme-setting script
    assert "localStorage.getItem(\"theme\")" in page
