from __future__ import annotations

from io import BytesIO
from datetime import datetime

from bson import ObjectId
from reportlab.lib import colors
from reportlab.lib.pagesizes import landscape, letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from src.config.database import db


def _resolve_object_id(value: str, field_name: str):
    try:
        return ObjectId(value)
    except Exception:
        raise ValueError(f"Invalid {field_name} format")


def _parse_month_year(month: int | None, year: int | None) -> tuple[datetime | None, datetime | None, str]:
    if month is None and year is None:
        return None, None, "todas_las_fechas"

    now = datetime.utcnow()
    year = year or now.year

    if month is None:
        return datetime(year, 1, 1), datetime(year + 1, 1, 1), f"{year}"

    if month < 1 or month > 12:
        raise ValueError("month must be between 1 and 12")

    start = datetime(year, month, 1)
    if month == 12:
        end = datetime(year + 1, 1, 1)
    else:
        end = datetime(year, month + 1, 1)

    return start, end, f"{year}-{month:02d}"


def _format_date(value) -> str:
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d")
    return str(value) if value else ""


def _group_name(group_doc: dict | None) -> str:
    if not group_doc:
        return "N/A"
    return group_doc.get("name") or "N/A"


def _load_group_attendance(group_oid: ObjectId, start_date: datetime | None, end_date: datetime | None):
    query = {"group_id": group_oid}
    if start_date and end_date:
        query["attendance_date"] = {"$gte": start_date, "$lt": end_date}
    return list(db.attendance.find(query).sort([("attendance_date", 1)]))


def _build_student_rows(students: list[dict], sessions: list[dict]) -> list[list[str]]:
    rows = [["Estudiante", "Presentes", "Ausentes", "Tardanzas", "Total", "% Asistencia"]]

    for student in students:
        counts = {"presente": 0, "ausente": 0, "tardanza": 0}
        for session in sessions:
            record = next((r for r in session.get("records", []) if r.get("student_id") == student["_id"]), None)
            status = (record or {}).get("status", "ausente")
            counts[status] = counts.get(status, 0) + 1

        total = sum(counts.values())
        present = counts["presente"]
        attendance_pct = (present / total * 100) if total else 0.0
        rows.append([
            f"{student.get('first_name', '')} {student.get('last_name', '')}".strip(),
            str(present),
            str(counts["ausente"]),
            str(counts["tardanza"]),
            str(total),
            f"{attendance_pct:.1f}%",
        ])

    return rows


def _build_session_rows(sessions: list[dict], students: list[dict]) -> list[list[str]]:
    rows = [["Fecha", "Presentes", "Ausentes", "Tardanzas", "Total estudiantes", "% Asistencia"]]
    total_students = len(students)

    for session in sessions:
        counts = {"presente": 0, "ausente": 0, "tardanza": 0}
        records = {str(r.get("student_id")): r.get("status", "ausente") for r in session.get("records", [])}

        for student in students:
            status = records.get(str(student["_id"]), "ausente")
            counts[status] = counts.get(status, 0) + 1

        present = counts["presente"]
        attendance_pct = (present / total_students * 100) if total_students else 0.0
        rows.append([
            _format_date(session.get("attendance_date")),
            str(present),
            str(counts["ausente"]),
            str(counts["tardanza"]),
            str(total_students),
            f"{attendance_pct:.1f}%",
        ])

    return rows


def generate_group_attendance_pdf(group_id: str, month: int | None = None, year: int | None = None) -> tuple[BytesIO, str]:
    group_oid = _resolve_object_id(group_id, "group_id")
    group = db.groups.find_one({"_id": group_oid})
    if not group:
        raise ValueError("Group not found")

    start_date, end_date, period_label = _parse_month_year(month, year)
    sessions = _load_group_attendance(group_oid, start_date, end_date)
    students = list(db.users.find({"group_id": group_oid, "role": "student", "active": True}).sort([("last_name", 1), ("first_name", 1)]))

    buffer = BytesIO()
    document = SimpleDocTemplate(
        buffer,
        pagesize=landscape(letter),
        rightMargin=0.4 * inch,
        leftMargin=0.4 * inch,
        topMargin=0.5 * inch,
        bottomMargin=0.4 * inch,
    )

    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="ReportTitle", parent=styles["Title"], fontSize=18, leading=22, textColor=colors.HexColor("#14324a"), spaceAfter=8))
    styles.add(ParagraphStyle(name="ReportSubTitle", parent=styles["Normal"], fontSize=10, leading=12, textColor=colors.HexColor("#4b5563"), spaceAfter=6))
    styles.add(ParagraphStyle(name="ReportNote", parent=styles["Normal"], fontSize=9, leading=11, textColor=colors.HexColor("#4b5563")))

    story = []
    story.append(Paragraph("EduConecta CR", styles["ReportTitle"]))
    story.append(Paragraph(f"Reporte de asistencia del grupo {_group_name(group)}", styles["Heading2"]))
    story.append(Paragraph(f"Periodo: {period_label.replace('_', ' ')}", styles["ReportSubTitle"]))
    story.append(Paragraph(f"Generado el: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}", styles["ReportSubTitle"]))
    story.append(Spacer(1, 0.2 * inch))

    summary_rows = [
        ["Group", _group_name(group)],
        ["Total students", str(len(students))],
        ["Attendance sessions", str(len(sessions))],
    ]
    summary_table = Table(summary_rows, colWidths=[2.0 * inch, 6.2 * inch])
    summary_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#dbeafe")),
        ("TEXTCOLOR", (0, 0), (-1, -1), colors.black),
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ROWBACKGROUNDS", (0, 0), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(summary_table)
    story.append(Spacer(1, 0.2 * inch))

    if sessions:
        story.append(Paragraph("Resumen por sesión", styles["Heading3"]))
        session_table = Table(_build_session_rows(sessions, students), repeatRows=1, colWidths=[1.5 * inch, 1.1 * inch, 1.1 * inch, 1.0 * inch, 1.3 * inch, 1.2 * inch])
        session_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1d4ed8")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
            ("ALIGN", (1, 1), (-1, -1), "CENTER"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ]))
        story.append(session_table)
        story.append(Spacer(1, 0.2 * inch))

    story.append(Paragraph("Porcentaje de asistencia por estudiante", styles["Heading3"]))
    student_rows = _build_student_rows(students, sessions)
    student_table = Table(student_rows, repeatRows=1, colWidths=[3.0 * inch, 0.9 * inch, 0.9 * inch, 0.9 * inch, 0.8 * inch, 1.2 * inch])
    student_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0f766e")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
        ("ALIGN", (1, 1), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    story.append(student_table)
    story.append(Spacer(1, 0.15 * inch))
    story.append(Paragraph("El porcentaje de asistencia se calcula con base en los registros presentes sobre el total de sesiones del periodo seleccionado.", styles["ReportNote"]))

    document.build(story)
    buffer.seek(0)
    filename = f"reporte_asistencia_grupo_{group.get('name', group_oid)}_{period_label}.pdf".replace(" ", "_")
    return buffer, filename
