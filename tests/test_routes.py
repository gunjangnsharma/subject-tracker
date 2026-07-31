"""Route / smoke tests via Flask's test client (test plan section 2.5)."""


def test_dashboard_ok(client):  # W1
    assert client.get("/").status_code == 200


def test_subjects_page_ok(client):
    assert client.get("/subjects").status_code == 200


def test_create_subject_appears(client):  # W2
    client.post("/subjects", data={"name": "Algorithms"}, follow_redirects=True)
    body = client.get("/subjects").get_data(as_text=True)
    assert "Algorithms" in body


def test_subject_detail_and_chapter_flow(client):  # W3, W4
    client.post("/subjects", data={"name": "Networks"}, follow_redirects=True)
    # Subject id is 1 in a fresh in-memory DB.
    detail = client.get("/subjects/1")
    assert detail.status_code == 200

    client.post("/subjects/1/modules", data={"name": "TCP"}, follow_redirects=True)
    client.post(
        "/modules/1/chapters",
        data={"title": "Handshake", "kind": "video", "duration_minutes": "90"},
        follow_redirects=True,
    )
    page = client.get("/subjects/1").get_data(as_text=True)
    assert "Handshake" in page
    assert "1.5h" in page  # 90 minutes displayed as hours

    # Update completion.
    client.post("/chapters/1/completion", data={"completion": "5"}, follow_redirects=True)
    page = client.get("/subjects/1").get_data(as_text=True)
    assert "0.75h done" in page  # 90 * 5/10 = 45 min = 0.75h


def test_today_and_week_ok(client):  # W5
    assert client.get("/today").status_code == 200
    assert client.get("/week").status_code == 200


def test_missing_subject_404(client):
    assert client.get("/subjects/999").status_code == 404
