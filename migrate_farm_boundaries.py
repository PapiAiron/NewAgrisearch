"""
Migration: Farm Lot Boundaries
- Adds lot_boundary_geojson to farms table

Run: python migrate_farm_boundaries.py
"""
import os
import sys

from sqlalchemy import text

sys.path.insert(0, os.path.dirname(__file__))

from app import create_app, db


app = create_app()


def column_exists(conn, table, column):
    result = conn.execute(text(
        "SELECT COUNT(*) FROM information_schema.columns "
        "WHERE table_schema = DATABASE() AND table_name = :t AND column_name = :c"
    ), {"t": table, "c": column})
    return result.scalar() > 0


with app.app_context():
    with db.engine.connect() as conn:
        if not column_exists(conn, 'farms', 'lot_boundary_geojson'):
            conn.execute(text(
                "ALTER TABLE farms "
                "ADD COLUMN lot_boundary_geojson LONGTEXT"
            ))
            print("  ✔ farms.lot_boundary_geojson added")
        else:
            print("  · farms.lot_boundary_geojson already exists")

        conn.commit()

    print("\nMigration complete.")
