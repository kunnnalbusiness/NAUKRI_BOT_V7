"""
Resume Upload Validation Tests: magic-byte check, size limit, filename sanitising.
"""

import io

import pytest
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.core.config import settings

client = TestClient(app)


@pytest.fixture(scope="module")
def admin_token():
    res = client.post(
        "/api/auth/login",
        json={
            "username": settings.ADMIN_USERNAME,
            "password": settings.ADMIN_PASSWORD,
        },
    )
    assert res.status_code == 200
    return res.json()["token"]


def _upload(token: str, filename: str, content: bytes):
    return client.post(
        "/api/profile/resume",
        files={"file": (filename, io.BytesIO(content), "application/pdf")},
        headers={"Authorization": f"Bearer {token}"},
    )


class TestResumeUploadValidation:
    def test_rejects_non_pdf_content_with_pdf_extension(self, admin_token):
        """A text file renamed to .pdf must be rejected by the magic-byte check."""
        res = _upload(admin_token, "fake.pdf", b"this is definitely not a pdf")
        assert res.status_code == 400
        assert "not a valid PDF" in res.json()["detail"]

    def test_rejects_non_pdf_extension(self, admin_token):
        res = _upload(admin_token, "notes.txt", b"%PDF-1.4 fake")
        assert res.status_code == 400

    def test_rejects_oversized_file(self, admin_token):
        big = b"%PDF-1.4\n" + b"x" * (5 * 1024 * 1024 + 100)
        res = _upload(admin_token, "big.pdf", big)
        assert res.status_code == 400
        assert "5 MB" in res.json()["detail"]

    def test_accepts_valid_pdf_and_sanitises_filename(self, admin_token):
        minimal_pdf = b"%PDF-1.4\n1 0 obj\nendobj\ntrailer<<>>\n%%EOF"
        res = _upload(admin_token, "../../evil name<>.pdf", minimal_pdf)
        assert res.status_code == 200, res.text
        body = res.json()
        assert body["success"] is True
        # Path traversal characters must be stripped from the stored name
        assert ".." not in body["filename"]
        assert "/" not in body["filename"]
