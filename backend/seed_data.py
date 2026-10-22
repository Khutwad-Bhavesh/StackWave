import sys
import os
import datetime

# Ensure app package is importable
sys.path.insert(0, os.path.dirname(__file__))

from app.database import Base, engine, SessionLocal
from app.models import User, Member, Book, BookCopy, Reader, Loan, Alert, ScanEvent
from app.security import hash_password

def seed_database(custom_db=None):
    print("Initializing database tables...")
    if custom_db is not None:
        db = custom_db
        should_close = False
    else:
        Base.metadata.create_all(bind=engine)
        db = SessionLocal()
        should_close = True

    try:
        # Check if already seeded
        if db.query(User).count() > 0:
            print("Database already contains data. Skipping re-seed.")
            return

        print("Seeding Users & Staff...")
        admin = User(
            username="admin",
            password_hash=hash_password("admin123"),
            full_name="System Administrator",
            role="admin"
        )
        librarian = User(
            username="librarian",
            password_hash=hash_password("lib123"),
            full_name="Chief Librarian Eleanor",
            role="librarian"
        )
        user_alice = User(
            username="member_alice",
            password_hash=hash_password("alice123"),
            full_name="Alice Johnson",
            role="member"
        )
        user_bob = User(
            username="member_bob",
            password_hash=hash_password("bob123"),
            full_name="Bob Smith",
            role="member"
        )
        db.add_all([admin, librarian, user_alice, user_bob])
        db.commit()

        print("Seeding Members with RFID Cards...")
        member_alice = Member(
            user_id=user_alice.id,
            name="Alice Johnson",
            email="alice.j@university.edu",
            member_card_uid="CARD-ALICE-001",
            max_books=5,
            is_active=True
        )
        member_bob = Member(
            user_id=user_bob.id,
            name="Bob Smith",
            email="bob.smith@university.edu",
            member_card_uid="CARD-BOB-002",
            max_books=5,
            is_active=True
        )
        member_charlie = Member(
            user_id=None,
            name="Charlie Brown",
            email="charlie.b@university.edu",
            member_card_uid="CARD-CHARLIE-003",
            max_books=5,
            is_active=True
        )
        db.add_all([member_alice, member_bob, member_charlie])
        db.commit()

        print("Seeding RFID Readers with Pre-Shared HMAC Keys...")
        readers = [
            Reader(
                device_id="CHECKOUT-01",
                name="Self-Checkout Kiosk 1",
                reader_type="CHECKOUT",
                secret_key="checkout-secret-key-9988",
                location="Circulation Desk A",
                is_active=True,
                last_heartbeat=datetime.datetime.utcnow(),
                total_scans=12
            ),
            Reader(
                device_id="RETURN-01",
                name="Smart Return Chute",
                reader_type="RETURN",
                secret_key="return-secret-key-4455",
                location="Main Lobby Return Drop",
                is_active=True,
                last_heartbeat=datetime.datetime.utcnow(),
                total_scans=8
            ),
            Reader(
                device_id="SHELF-CS-01",
                name="Shelf Antenna - CS Stacks",
                reader_type="SHELF",
                secret_key="shelf-secret-key-1122",
                location="Aisle 3: Computer Science & Systems",
                is_active=True,
                last_heartbeat=datetime.datetime.utcnow(),
                total_scans=25
            ),
            Reader(
                device_id="GATE-01",
                name="Anti-Theft Exit Gate",
                reader_type="EXIT_GATE",
                secret_key="gate-secret-key-7766",
                location="Main Library Exit",
                is_active=True,
                last_heartbeat=datetime.datetime.utcnow(),
                total_scans=15
            )
        ]
        db.add_all(readers)
        db.commit()

        print("Seeding Books and RFID-Tagged Copies...")
        books_data = [
            {
                "title": "Clean Code: A Handbook of Agile Software Craftsmanship",
                "author": "Robert C. Martin",
                "isbn": "978-0132350884",
                "category": "Computer Science",
                "copies": [
                    {"tag_uid": "TAG-BK-CLEAN-01", "shelf": "Aisle 3: Computer Science & Systems"},
                    {"tag_uid": "TAG-BK-CLEAN-02", "shelf": "Aisle 3: Computer Science & Systems"}
                ]
            },
            {
                "title": "Designing Data-Intensive Applications",
                "author": "Martin Kleppmann",
                "isbn": "978-1449373320",
                "category": "Data Engineering",
                "copies": [
                    {"tag_uid": "TAG-BK-DDIA-01", "shelf": "Aisle 3: Computer Science & Systems"},
                    {"tag_uid": "TAG-BK-DDIA-02", "shelf": "Aisle 3: Computer Science & Systems"}
                ]
            },
            {
                "title": "Computer Networks (5th Edition)",
                "author": "Andrew S. Tanenbaum",
                "isbn": "978-0132126953",
                "category": "Networking",
                "copies": [
                    {"tag_uid": "TAG-BK-NET-01", "shelf": "Aisle 2: Networking"}
                ]
            },
            {
                "title": "The Pragmatic Programmer: Your Journey To Mastery",
                "author": "David Thomas, Andrew Hunt",
                "isbn": "978-0135957059",
                "category": "Software Engineering",
                "copies": [
                    {"tag_uid": "TAG-BK-PRAG-01", "shelf": "Aisle 3: Computer Science & Systems"}
                ]
            },
            {
                "title": "Cloud Native Patterns: Designing High-Availability Systems",
                "author": "Cornelia Davis",
                "isbn": "978-1617294297",
                "category": "Cloud Computing",
                "copies": [
                    {"tag_uid": "TAG-BK-CLOUD-01", "shelf": "Aisle 4: Cloud Computing"}
                ]
            },
            {
                "title": "Operating System Concepts (10th Edition)",
                "author": "Abraham Silberschatz, Peter B. Galvin",
                "isbn": "978-1119800361",
                "category": "Operating Systems",
                "copies": [
                    {"tag_uid": "TAG-BK-OS-01", "shelf": "Aisle 1: Systems & Architecture"}
                ]
            }
        ]

        all_copies = []
        for b_info in books_data:
            book = Book(
                title=b_info["title"],
                author=b_info["author"],
                isbn=b_info["isbn"],
                category=b_info["category"]
            )
            db.add(book)
            db.commit()
            db.refresh(book)

            for c_info in b_info["copies"]:
                copy = BookCopy(
                    book_id=book.id,
                    tag_uid=c_info["tag_uid"],
                    shelf_location=c_info["shelf"],
                    status="AVAILABLE",
                    last_seen_reader_id="SHELF-CS-01",
                    last_seen_at=datetime.datetime.utcnow() - datetime.timedelta(hours=2)
                )
                db.add(copy)
                all_copies.append(copy)

        db.commit()

        print("Seeding Initial Circulation Data (Active & Overdue Loans)...")
        now = datetime.datetime.utcnow()

        # Alice has 1 active loan (Clean Code Copy 1) - due in 10 days
        clean_copy_1 = db.query(BookCopy).filter(BookCopy.tag_uid == "TAG-BK-CLEAN-01").first()
        clean_copy_1.status = "CHECKED_OUT"
        clean_copy_1.shelf_location = f"With Member (Alice Johnson)"
        clean_copy_1.last_seen_reader_id = "CHECKOUT-01"
        clean_copy_1.last_seen_at = now - datetime.timedelta(days=4)

        loan_alice = Loan(
            copy_id=clean_copy_1.id,
            member_id=member_alice.id,
            checkout_at=now - datetime.timedelta(days=4),
            due_date=now + datetime.timedelta(days=10),
            renewal_count=0,
            status="ACTIVE"
        )
        db.add(loan_alice)

        # Bob has 1 overdue loan (Operating Systems Copy 1) - overdue by 5 days!
        # This triggers FR4 rule: Bob will be blocked from checking out new books until returned.
        os_copy_1 = db.query(BookCopy).filter(BookCopy.tag_uid == "TAG-BK-OS-01").first()
        os_copy_1.status = "CHECKED_OUT"
        os_copy_1.shelf_location = f"With Member (Bob Smith)"
        os_copy_1.last_seen_reader_id = "CHECKOUT-01"
        os_copy_1.last_seen_at = now - datetime.timedelta(days=19)

        loan_bob_overdue = Loan(
            copy_id=os_copy_1.id,
            member_id=member_bob.id,
            checkout_at=now - datetime.timedelta(days=19),
            due_date=now - datetime.timedelta(days=5),  # 5 days overdue
            renewal_count=0,
            status="ACTIVE"
        )
        db.add(loan_bob_overdue)

        # Seed initial alert
        theft_alert = Alert(
            alert_type="UNAUTHORIZED_EXIT",
            severity="CRITICAL",
            reader_id="GATE-01",
            copy_id=clean_copy_1.id,
            tag_uid="TAG-BK-CLEAN-01",
            message="Resolved Demo Alert: Book detected passing gate before checkout was registered.",
            created_at=now - datetime.timedelta(hours=12),
            resolved=True,
            resolved_by="librarian",
            resolved_at=now - datetime.timedelta(hours=11)
        )
        db.add(theft_alert)

        db.commit()
        print("Database seeded successfully with realistic RFID library dataset!")

    finally:
        if should_close:
            db.close()

if __name__ == "__main__":
    seed_database()
