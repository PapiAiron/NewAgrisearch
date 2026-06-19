"""
Migration: Distribution System v2
- Adds request_type, claim_code, claim_location, claim_deadline to distribution_requests
- Creates municipal_offers table
- Creates municipal_offer_claims table

Run: python migrate_distribution_v2.py
"""
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from app import create_app, db
from sqlalchemy import text

app = create_app()

def column_exists(conn, table, column):
    result = conn.execute(text(
        "SELECT COUNT(*) FROM information_schema.columns "
        "WHERE table_schema = DATABASE() AND table_name = :t AND column_name = :c"
    ), {"t": table, "c": column})
    return result.scalar() > 0

def table_exists(conn, table):
    result = conn.execute(text(
        "SELECT COUNT(*) FROM information_schema.tables "
        "WHERE table_schema = DATABASE() AND table_name = :t"
    ), {"t": table})
    return result.scalar() > 0

with app.app_context():
    with db.engine.connect() as conn:

        # ── distribution_requests ────────────────────────────────────────────
        if not column_exists(conn, 'distribution_requests', 'request_type'):
            conn.execute(text(
                "ALTER TABLE distribution_requests "
                "ADD COLUMN request_type VARCHAR(50) NOT NULL DEFAULT 'via_officer'"
            ))
            print("  ✔ distribution_requests.request_type added")
        else:
            print("  · distribution_requests.request_type already exists")

        if not column_exists(conn, 'distribution_requests', 'claim_code'):
            conn.execute(text(
                "ALTER TABLE distribution_requests "
                "ADD COLUMN claim_code VARCHAR(10)"
            ))
            print("  ✔ distribution_requests.claim_code added")
        else:
            print("  · distribution_requests.claim_code already exists")

        if not column_exists(conn, 'distribution_requests', 'claim_location'):
            conn.execute(text(
                "ALTER TABLE distribution_requests "
                "ADD COLUMN claim_location VARCHAR(200)"
            ))
            print("  ✔ distribution_requests.claim_location added")
        else:
            print("  · distribution_requests.claim_location already exists")

        if not column_exists(conn, 'distribution_requests', 'claim_deadline'):
            conn.execute(text(
                "ALTER TABLE distribution_requests "
                "ADD COLUMN claim_deadline DATE"
            ))
            print("  ✔ distribution_requests.claim_deadline added")
        else:
            print("  · distribution_requests.claim_deadline already exists")

        # ── municipal_offers ─────────────────────────────────────────────────
        if not table_exists(conn, 'municipal_offers'):
            conn.execute(text("""
                CREATE TABLE municipal_offers (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    name VARCHAR(200) NOT NULL,
                    supply_name VARCHAR(200) NOT NULL,
                    supply_type VARCHAR(100) NOT NULL,
                    total_quantity FLOAT NOT NULL,
                    quantity_per_farmer FLOAT NOT NULL,
                    unit VARCHAR(50) NOT NULL,
                    claim_location VARCHAR(200) NOT NULL,
                    claim_start DATE,
                    claim_deadline DATE NOT NULL,
                    target_barangay VARCHAR(100),
                    notes TEXT,
                    status VARCHAR(50) NOT NULL DEFAULT 'draft',
                    created_by_id INT NOT NULL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                    FOREIGN KEY (created_by_id) REFERENCES users(id)
                )
            """))
            print("  ✔ municipal_offers table created")
        else:
            print("  · municipal_offers table already exists")

        # ── municipal_offer_claims ───────────────────────────────────────────
        if not table_exists(conn, 'municipal_offer_claims'):
            conn.execute(text("""
                CREATE TABLE municipal_offer_claims (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    offer_id INT NOT NULL,
                    farm_id INT NOT NULL,
                    farmer_id INT NOT NULL,
                    quantity_reserved FLOAT NOT NULL,
                    claim_code VARCHAR(10) UNIQUE,
                    status VARCHAR(50) NOT NULL DEFAULT 'registered',
                    registered_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    claimed_at DATETIME,
                    FOREIGN KEY (offer_id) REFERENCES municipal_offers(id),
                    FOREIGN KEY (farm_id) REFERENCES farms(id),
                    FOREIGN KEY (farmer_id) REFERENCES users(id)
                )
            """))
            print("  ✔ municipal_offer_claims table created")
        else:
            print("  · municipal_offer_claims table already exists")

        conn.commit()

    print("\nMigration complete.")
