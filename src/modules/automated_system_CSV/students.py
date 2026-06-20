# Lector y separador de CSV de estudiantes (sin modificar ninguna BD)
# Formato esperado (separador `;`):
# cedula;nombre;apellido1;apellido2;nivel;seccion;cedula_padre;accion

import csv
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

DEFAULT_CSV = Path(__file__).parent / "src" / "csv" / "students.csv"

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")


@dataclass
class StudentEntry:
    cedula: str
    nombre: str
    apellido1: str
    apellido2: str
    nivel: str
    seccion: str
    cedula_padre: str
    accion: str
    accion_normalizada: Optional[str] = None
    raw: Dict[str, str] = field(default_factory=dict)


class StudentCSVProcessor:
    def __init__(self, csv_path: Optional[Path] = None):
        self.csv_path = csv_path or DEFAULT_CSV
        self.entries: List[StudentEntry] = []
        self.groups: Dict[str, List[StudentEntry]] = {
            "insertar": [],
            "update": [],
            "eliminar": [],
            "skipped": [],
        }

    @staticmethod
    def normalize_accion(accion: str) -> Optional[str]:
        if not accion:
            return None
        a = accion.strip().lower()
        if a in {"insertar", "insert", "crear"}:
            return "insertar"
        if a in {"update", "actualizar", "modificar"}:
            return "update"
        if a in {"eliminar", "delete", "borrar"}:
            return "eliminar"
        return None

    def read_entries(self) -> List[StudentEntry]:
        self.entries = []
        if not self.csv_path.exists():
            logging.error(f"Archivo CSV no encontrado: {self.csv_path}")
            return self.entries

        with self.csv_path.open(newline="", encoding="utf-8") as fh:
            reader = csv.DictReader(fh, delimiter=";")
            for row in reader:
                accion_raw = (row.get("accion") or "").strip()
                accion_normalizada = self.normalize_accion(accion_raw)
                entry = StudentEntry(
                    cedula=(row.get("cedula") or "").strip(),
                    nombre=(row.get("nombre") or "").strip(),
                    apellido1=(row.get("apellido1") or "").strip(),
                    apellido2=(row.get("apellido2") or "").strip(),
                    nivel=(row.get("nivel") or "").strip(),
                    seccion=(row.get("seccion") or "").strip(),
                    cedula_padre=(row.get("cedula_padre") or "").strip(),
                    accion=accion_raw,
                    accion_normalizada=accion_normalizada,
                    raw=row,
                )
                self.entries.append(entry)
        return self.entries

    def group_by_action(self) -> Dict[str, List[StudentEntry]]:
        if not self.entries:
            self.read_entries()

        self.groups = {
            "insertar": [],
            "update": [],
            "eliminar": [],
            "skipped": [],
        }
        for entry in self.entries:
            if entry.accion_normalizada is None:
                self.groups["skipped"].append(entry)
            else:
                self.groups.setdefault(entry.accion_normalizada, []).append(entry)
        return self.groups

    def process(self) -> Dict[str, List[StudentEntry]]:
        self.read_entries()
        return self.group_by_action()

    def insert_records(self) -> int:
        """Recorre los registros de insertar y aplica la lógica de inserción."""
        if not self.groups["insertar"]:
            self.group_by_action()
        count = 0
        for entry in self.groups["insertar"]:
            # Aquí va la lógica real de inserción. Por ahora solo se prepara el registro.
            logging.info(f"Preparando insertar: {entry.cedula} - {entry.nombre} {entry.apellido1}")
            count += 1
        return count

    def update_records(self) -> int:
        """Recorre los registros de update y aplica la lógica de actualización."""
        if not self.groups["update"]:
            self.group_by_action()
        count = 0
        for entry in self.groups["update"]:
            logging.info(f"Preparando update: {entry.cedula} - {entry.nombre} {entry.apellido1}")
            count += 1
        return count

    def delete_records(self) -> int:
        """Recorre los registros de eliminar y aplica la lógica de eliminación."""
        if not self.groups["eliminar"]:
            self.group_by_action()
        count = 0
        for entry in self.groups["eliminar"]:
            logging.info(f"Preparando eliminar: {entry.cedula} - {entry.nombre} {entry.apellido1}")
            count += 1
        return count

    def print_summary(self, groups: Dict[str, List[StudentEntry]]) -> None:
        logging.info("Resumen de separación:")
        for accion, rows in groups.items():
            logging.info(f"- {accion}: {len(rows)}")

    def print_groups(self, groups: Dict[str, List[StudentEntry]], max_per_group: int = 20) -> None:
        logging.info("\nDetalle por acción:")
        for accion in ["insertar", "update", "eliminar", "skipped"]:
            rows = groups.get(accion, [])
            if not rows:
                continue
            logging.info(f"-- Acción: {accion} ({len(rows)} filas)")
            for entry in rows[:max_per_group]:
                logging.info(
                    f"  {entry.cedula} | {entry.nombre} {entry.apellido1} {entry.apellido2}"
                    f" | {entry.nivel} {entry.seccion} | padre: {entry.cedula_padre}"
                )
            if len(rows) > max_per_group:
                logging.info(f"  ... y {len(rows)-max_per_group} filas más")


def main(csv_path: Optional[str] = None) -> Dict[str, List[StudentEntry]]:
    processor = StudentCSVProcessor(Path(csv_path) if csv_path else None)
    groups = processor.process()
    processor.print_summary(groups)
    processor.print_groups(groups)

    inserted = processor.insert_records()
    updated = processor.update_records()
    deleted = processor.delete_records()

    logging.info(f"\nOperaciones preparadas: insertar={inserted}, update={updated}, eliminar={deleted}")
    return groups


if __name__ == "__main__":
    main()
