from datetime import datetime

from bson import ObjectId

from src.config.database import db


def test_group_attendance_pdf_report(client, seed_users, teacher_headers):
    db.attendance.insert_one({
        "attendance_date": datetime(2026, 8, 8),
        "group_id": ObjectId(seed_users["group_id"]),
        "subject_id": ObjectId(seed_users["subject_id"]),
        "records": [
            {
                "student_id": ObjectId(seed_users["student_id"]),
                "status": "presente",
                "arrival_time": "07:05",
            }
        ],
        "created_at": datetime.utcnow(),
    })

    response = client.get(
        f"/api/v1/reports/groups/{seed_users['group_id']}/attendance/pdf",
        headers=teacher_headers,
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/pdf")
    assert "attachment; filename=" in response.headers["content-disposition"]
    assert response.content.startswith(b"%PDF")
    assert len(response.content) > 1000
