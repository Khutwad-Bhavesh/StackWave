# StackWave: System Architecture & Workflow Diagrams (Mermaid)

This document contains complete, copy-paste-ready Mermaid diagrams for the StackWave Cloud-Native RFID Library System. You can render these directly in GitHub Markdown, Notion, Mermaid Live Editor, or include them in your academic report.

---

## 1. End-to-End System Architecture

```mermaid
flowchart TD
    subgraph Edge["Edge Hardware & Simulation Layer"]
        R1["Checkout Kiosk 1<br/>(CHECKOUT-01)"]
        R2["Smart Return Chute<br/>(RETURN-01)"]
        R3["Shelf CS Antenna<br/>(SHELF-CS-01)"]
        R4["Anti-Theft Exit Gate<br/>(GATE-01)"]
        ESP["ESP32 + RC522 Firmware<br/>(mbedtls Crypto)"]
        SIM["Virtual Reader Panel /<br/>Python Simulator"]
    end

    subgraph Ingress["Ingress & Load Balancing Layer"]
        NGINX["Nginx Reverse Proxy & Load Balancer<br/>(Port 80 / 8080)"]
        SPA["Dashboard Static SPA<br/>(HTML5 / CSS3 / WebCrypto)"]
    end

    subgraph Cluster["Stateless Application Cluster (Docker Compose / ECS)"]
        API1["FastAPI Replica 1<br/>(:8000)"]
        API2["FastAPI Replica 2<br/>(:8000)"]
        API3["FastAPI Replica 3<br/>(:8000)"]
    end

    subgraph Services["Core Microservice Modules"]
        M1["M1: DevOps, Health & Prometheus /metrics"]
        M2["M2: HMAC Ingest, Replay & 2s Debounce"]
        M3["M3: Circulation & Renewal Engine"]
        M4["M4: Shelf Tracking & Exit Theft Alerts"]
        M5["M5: JWT Auth, RBAC & Live Feed"]
    end

    subgraph Persistence["Storage & Observability Layer"]
        DB[("PostgreSQL 16 Database<br/>(Managed ACID Storage)")]
        LOGS["Structured JSON Logs<br/>(stdout / CloudWatch)"]
        PROM["Prometheus Telemetry<br/>(Scraping /metrics)"]
    end

    R1 -.->|"HTTPS POST /rfid/scan"| NGINX
    R2 -.->|"HTTPS POST /rfid/scan"| NGINX
    R3 -.->|"HTTPS POST /rfid/scan"| NGINX
    R4 -.->|"HTTPS POST /rfid/scan"| NGINX
    ESP -.-> R1
    SIM -.-> R1

    SPA <-->|"HTTP REST & Events"| NGINX
    NGINX -->|"Round-Robin Upstream"| API1
    NGINX -->|"Round-Robin Upstream"| API2
    NGINX -->|"Round-Robin Upstream"| API3

    API1 --- Services
    API2 --- Services
    API3 --- Services

    Services <-->|"SQLAlchemy 2.0 ORM"| DB
    Services --> LOGS
    M1 --> PROM
```

---

## 2. Cryptographic HMAC Ingestion & Anti-Replay Guard Sequence

```mermaid
sequenceDiagram
    autonumber
    actor Patron as Library Patron / Book
    participant Reader as Edge RFID Terminal (ESP32/Simulator)
    participant Nginx as Nginx Load Balancer
    participant API as FastAPI Ingestion Router
    participant Cache as Memory Sliding Window
    participant DB as PostgreSQL Database
    participant UI as Staff Live Dashboard

    Patron->>Reader: Present Tag / Smartcard (13.56 MHz RF)
    Note over Reader: Read Tag UID (Hex)<br/>Check local 2000ms debounce
    Reader->>Reader: Generate UTC timestamp & 16-byte random Nonce
    Reader->>Reader: Compute HMAC-SHA256(SecretKey, ReaderID:TagUID:TS:Nonce)
    Reader->>Nginx: HTTPS POST /rfid/scan (JSON Payload)
    Nginx->>API: Proxy to available API container replica

    API->>DB: Query Reader record by reader_id
    DB-->>API: Return Reader info & pre-shared secret key

    API->>API: Verify HMAC signature (constant-time compare)
    alt Signature Tampered
        API-->>Reader: HTTP 401 Unauthorized (Invalid Signature)
        API->>DB: Log ScanEvent (INVALID_SIGNATURE)
    else Signature Valid
        API->>API: Check Timestamp Freshness (|t_server - t_payload| <= 60s)
        alt Timestamp Drift > 60s
            API-->>Reader: HTTP 200 (REJECTED: Clock Drift)
        else Fresh Timestamp
            API->>Cache: Check Nonce Uniqueness in sliding window
            alt Nonce Reused (Replay Attack)
                API-->>Reader: HTTP 200 (REJECTED: Replay Nonce Consumed)
            else Nonce Unique
                API->>Cache: Check 2.0s Tag Debounce Window
                alt Scan within 2.0s of previous read
                    API-->>Reader: HTTP 200 (DEBOUNCED: Duplicate Read Suppressed)
                else Valid Fresh Scan
                    API->>DB: Process Circulation / Tracking / Security Logic
                    DB-->>API: Transaction Committed
                    API->>UI: Emit Live Scan Event & update KPIs
                    API-->>Reader: HTTP 200 OK (SUCCESS / ALARM)
                end
            end
        end
    end
```

---

## 3. Circulation Lifecycle & Self-Checkout State Machine

```mermaid
stateDiagram-v2
    [*] --> Idle: Terminal Waiting

    state "Idle: Waiting for Card" as Idle
    state "Verifying Member" as VerifyMember
    state "Overdue Blocked" as Blocked
    state "Checkout Session Active" as SessionActive
    state "Evaluating Book Copy" as EvalBook
    state "Book Checked Out" as CheckedOut
    state "Book Returned (Chute)" as Returned
    state "CRITICAL THEFT ALARM" as TheftAlarm

    Idle --> VerifyMember: Patron taps RFID Member Card
    VerifyMember --> Blocked: Patron has overdue loans
    Blocked --> Idle: Reset / Return overdue books first
    VerifyMember --> SessionActive: Account clear & active

    SessionActive --> EvalBook: Patron taps Book Copy tag
    EvalBook --> SessionActive: Loan quota exceeded (> 5 books)
    EvalBook --> SessionActive: Copy not available
    EvalBook --> CheckedOut: Copy available & quota OK

    CheckedOut --> SessionActive: Tap next book
    SessionActive --> Idle: Inactivity timeout (90s) / Finished

    Idle --> Returned: Book dropped in Return Chute
    Returned --> Idle: Fine calculated & copy marked Available

    Idle --> TheftAlarm: Unchecked book passes Exit Gate
    TheftAlarm --> Idle: Staff acknowledges & resolves incident
```

---

## 4. Entity-Relationship Diagram (ERD)

```mermaid
erDiagram
    USERS ||--o| MEMBERS : "links to"
    MEMBERS ||--o{ LOANS : "borrows"
    MEMBERS ||--o{ CHECKOUT_SESSIONS : "opens"
    BOOKS ||--|{ BOOK_COPIES : "contains physical"
    BOOK_COPIES ||--o{ LOANS : "loaned through"
    BOOK_COPIES ||--o{ ALERTS : "triggers"
    READERS ||--o{ SCAN_EVENTS : "logs"

    USERS {
        int id PK
        string username UK
        string password_hash
        string full_name
        string role "admin | librarian | member"
        datetime created_at
    }

    MEMBERS {
        int id PK
        int user_id FK
        string member_card_uid UK
        string name
        string email
        int max_books "default: 5"
        boolean is_active
        datetime created_at
    }

    BOOKS {
        int id PK
        string title
        string author
        string isbn UK
        string category
        text description
        datetime created_at
    }

    BOOK_COPIES {
        int id PK
        int book_id FK
        string tag_uid UK
        string status "AVAILABLE | CHECKED_OUT | LOST"
        string shelf_location
        string last_seen_reader_id
        datetime last_seen_at
    }

    READERS {
        int id PK
        string device_id UK
        string name
        string reader_type "CHECKOUT | RETURN | SHELF | EXIT_GATE"
        string secret_key "HMAC Pre-Shared Key"
        string location
        boolean is_active
        datetime last_heartbeat
        int total_scans
    }

    LOANS {
        int id PK
        int copy_id FK
        int member_id FK
        datetime checkout_at
        datetime due_date
        datetime returned_at
        int renewal_count "max: 1"
        float fine_amount
        string status "ACTIVE | RETURNED | OVERDUE"
    }

    CHECKOUT_SESSIONS {
        int id PK
        string reader_id
        int member_id FK
        string status "OPEN | COMPLETED | TIMED_OUT"
        datetime started_at
        datetime last_activity_at
        int scanned_copies_count
    }

    SCAN_EVENTS {
        int id PK
        string reader_id
        string tag_uid
        string tag_type "MEMBER_CARD | BOOK_TAG | UNKNOWN"
        int timestamp
        string nonce
        boolean signature_valid
        string result_status
        text action_detail
        datetime created_at
    }

    ALERTS {
        int id PK
        string alert_type "UNAUTHORIZED_EXIT | OVERDUE"
        string severity "CRITICAL | WARNING | INFO"
        string reader_id
        int copy_id FK
        string tag_uid
        text message
        datetime created_at
        boolean resolved
        string resolved_by
        datetime resolved_at
    }
```

---

## 5. Elastic Autoscaling & 12-Factor Cloud Topology

```mermaid
flowchart LR
    subgraph Clients["Edge Terminals & Staff Clients"]
        Edge["ESP32 Readers / Simulators"]
        Web["Web Browsers (Dashboard SPA)"]
    end

    subgraph Ingress["Ingress Layer"]
        LB["Nginx Load Balancer<br/>(Port 80/8080)"]
    end

    subgraph ServiceMesh["Stateless Compute Tier (docker compose up --scale api=3)"]
        API1["FastAPI Instance 1<br/>(PID 17, Port 8000)"]
        API2["FastAPI Instance 2<br/>(PID 18, Port 8000)"]
        API3["FastAPI Instance 3<br/>(PID 19, Port 8000)"]
    end

    subgraph DataTier["Data Persistence Tier"]
        DB[("PostgreSQL 16 Database<br/>(Volume: postgres_data)")]
    end

    subgraph Monitor["Observability Tier"]
        Health["/health Endpoint"]
        Prom["/metrics Prometheus Scraping"]
        Logs["Structured JSON Logging"]
    end

    Edge -->|"HMAC-Signed HTTPS"| LB
    Web -->|"REST API & Static Files"| LB

    LB -->|"Round-Robin #1"| API1
    LB -->|"Round-Robin #2"| API2
    LB -->|"Round-Robin #3"| API3

    API1 <-->|"ACID Connection Pool"| DB
    API2 <-->|"ACID Connection Pool"| DB
    API3 <-->|"ACID Connection Pool"| DB

    API1 --- Monitor
    API2 --- Monitor
    API3 --- Monitor
```
