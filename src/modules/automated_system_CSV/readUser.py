# Lector y separador de CSV de usuarios (sin modificar ninguna BD)
# Formato esperado (separador `;`):
# cedula;nombre;apellido1;apellido2;correo;telefono;tipo_usuario;accion

import csv
import logging
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

# Permite importar src.* cuando el archivo se ejecuta como script standalone
_root = str(Path(__file__).resolve().parents[3])
if _root not in sys.path:
    sys.path.insert(0, _root)

DEFAULT_CSV = Path(__file__).parent / "Example_CSV" / "users.csv"

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")


@dataclass
class UserEntry:
    cedula: str
    nombre: str
    apellido1: str
    apellido2: str
    correo: str
    telefono: str
    tipo_usuario: str
    accion: str
    tipo_normalizado: Optional[str] = None
    accion_normalizada: Optional[str] = None
    raw: Dict[str, str] = field(default_factory=dict)


class UserCSVProcessor:
    def __init__(self, csv_path: Optional[Path] = None):
        self.csv_path = csv_path or DEFAULT_CSV
        self.entries: List[UserEntry] = []
        self.groups: Dict[str, Dict[str, List[UserEntry]]] = {
            "docente": {},
            "padres": {},
            "skipped": {},
        }

    @staticmethod
    def normalize_tipo(tipo: str) -> Optional[str]:
        if not tipo:
            return None
        t = tipo.strip().lower()
        if t.startswith("doc") or t == "docente":
            return "docente"
        if t in {"padre", "madre", "padres", "madre/padre", "progenitor", "abuelo", "abuelos", "abuela", "abuelas", "encargado",
                 "encargada", "encargados", "encargadas"} or "padre" in t or "madre" in t:
            return "padres"
        return None

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

    def read_entries(self) -> List[UserEntry]:
        self.entries = []
        if not self.csv_path.exists():
            logging.error(f"Archivo CSV no encontrado: {self.csv_path}")
            return self.entries

        with self.csv_path.open(newline="", encoding="utf-8") as fh:
            reader = csv.DictReader(fh, delimiter=";")
            for row in reader:
                tipo_raw = (row.get("tipo_usuario") or "").strip()
                accion_raw = (row.get("accion") or "").strip()
                tipo_normalizado = self.normalize_tipo(tipo_raw)
                accion_normalizada = self.normalize_accion(accion_raw)
                entry = UserEntry(
                    cedula=(row.get("cedula") or "").strip(),
                    nombre=(row.get("nombre") or "").strip(),
                    apellido1=(row.get("apellido1") or "").strip(),
                    apellido2=(row.get("apellido2") or "").strip(),
                    correo=(row.get("correo") or "").strip(),
                    telefono=(row.get("telefono") or "").strip(),
                    tipo_usuario=tipo_raw,
                    accion=accion_raw,
                    tipo_normalizado=tipo_normalizado,
                    accion_normalizada=accion_normalizada,
                    raw=row,
                )
                self.entries.append(entry)
        return self.entries

    def group_by_action(self) -> Dict[str, Dict[str, List[UserEntry]]]:
        if not self.entries:
            self.read_entries()

        self.groups = {
            "docente": {},
            "padres": {},
            "skipped": {},
        }
        for entry in self.entries:
            if entry.tipo_normalizado is None:
                self.groups.setdefault("skipped", {}).setdefault("tipo_desconocido", []).append(entry)
                continue
            if entry.accion_normalizada is None:
                self.groups.setdefault("skipped", {}).setdefault("accion_desconocida", []).append(entry)
                continue
            self.groups.setdefault(entry.tipo_normalizado, {}).setdefault(entry.accion_normalizada, []).append(entry)
        return self.groups

    def process(self) -> Dict[str, Dict[str, List[UserEntry]]]:
        self.read_entries()
        return self.group_by_action()

    def insert_records(self) -> int:
        if not self.groups["docente"] and not self.groups["padres"]:
            self.group_by_action()
        from src.modules.users.users_service import create as svc_create
        count = 0
        for tipo in ["docente", "padres"]:
            role = "teacher" if tipo == "docente" else "parent"
            for entry in self.groups.get(tipo, {}).get("insertar", []):
                try:
                    svc_create({
                        'id_number':  entry.cedula,
                        'first_name': entry.nombre,
                        'last_name':  f"{entry.apellido1} {entry.apellido2}".strip(),
                        'email':      entry.correo or None,
                        'phone':      entry.telefono or None,
                        'role':       role,
                    })
                    logging.info(f"Insertado: {entry.cedula} ({tipo})")
                    count += 1
                except Exception as e:
                    if 'unique' in str(e).lower() or 'already exists' in str(e).lower():
                        logging.warning(f"Ya existe {entry.cedula}, saltando")
                    else:
                        logging.error(f"Error insertando {entry.cedula}: {e}")
        return count

    def update_records(self) -> int:
        if not self.groups["docente"] and not self.groups["padres"]:
            self.group_by_action()
        from src.modules.users.users_service import update as svc_update
        from src.config.database import db
        count = 0
        for tipo in ["docente", "padres"]:
            role = "teacher" if tipo == "docente" else "parent"
            for entry in self.groups.get(tipo, {}).get("update", []):
                try:
                    found = db.users.find_one({'id_number': entry.cedula})
                    if not found:
                        logging.warning(f"No encontrado para actualizar: {entry.cedula}")
                        continue
                    svc_update(str(found['_id']), {
                        'first_name': entry.nombre,
                        'last_name':  f"{entry.apellido1} {entry.apellido2}".strip(),
                        'email':      entry.correo or None,
                        'phone':      entry.telefono or None,
                        'role':       role,
                        'type':       None,
                        'group_id':   None,
                        'active':     True,
                    })
                    logging.info(f"Actualizado: {entry.cedula} ({tipo})")
                    count += 1
                except Exception as e:
                    logging.error(f"Error actualizando {entry.cedula}: {e}")
        return count

    def delete_records(self) -> int:
        if not self.groups["docente"] and not self.groups["padres"]:
            self.group_by_action()
        from src.modules.users.users_service import deactivate as svc_deactivate
        from src.config.database import db
        count = 0
        for tipo in ["docente", "padres"]:
            for entry in self.groups.get(tipo, {}).get("eliminar", []):
                try:
                    found = db.users.find_one({'id_number': entry.cedula})
                    if not found:
                        logging.warning(f"No encontrado para eliminar: {entry.cedula}")
                        continue
                    svc_deactivate(str(found['_id']))
                    logging.info(f"Eliminado (desactivado): {entry.cedula} ({tipo})")
                    count += 1
                except Exception as e:
                    logging.error(f"Error eliminando {entry.cedula}: {e}")
        return count

    def print_summary(self, groups: Dict[str, Dict[str, List[UserEntry]]]) -> None:
        logging.info("Resumen de separación:")
        for tipo, acciones in groups.items():
            if not acciones:
                logging.info(f"- {tipo}: 0")
                continue
            total = sum(len(v) for v in acciones.values())
            logging.info(f"- {tipo}: {total}")
            for accion, rows in acciones.items():
                logging.info(f"  - {accion}: {len(rows)}")

    def print_groups(self, groups: Dict[str, Dict[str, List[UserEntry]]], max_per_group: int = 20) -> None:
        logging.info("\nDetalle por tipo y acción:")
        for tipo in sorted(groups.keys()):
            acciones = groups.get(tipo) or {}
            if not acciones:
                continue
            logging.info(f"\n=== Tipo: {tipo} ===")
            for accion in sorted(acciones.keys()):
                rows = acciones.get(accion, [])
                logging.info(f"-- Acción: {accion} ({len(rows)} filas)")
                for entry in rows[:max_per_group]:
                    logging.info(
                        f"  {entry.cedula} | {entry.nombre} {entry.apellido1} {entry.apellido2}"
                        f" | {entry.correo} | {entry.telefono}"
                    )
                if len(rows) > max_per_group:
                    logging.info(f"  ... y {len(rows)-max_per_group} filas más")


def main(csv_path: Optional[str] = None) -> Dict[str, Dict[str, List[UserEntry]]]:
    processor = UserCSVProcessor(Path(csv_path) if csv_path else None)
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
