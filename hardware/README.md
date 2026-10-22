# Hardware Specification: ESP32 + MFRC522 Edge RFID Reader

This document details the edge reader hardware reference implementation for the Cloud-Native RFID Library System.

---

## 1. Hardware Bill of Materials (BOM)

| Component | Specification | Purpose |
|---|---|---|
| **MCU** | ESP32 DevKit V1 (Dual-Core Tensilica Xtensa 32-bit LX6 @ 240MHz, 520KB SRAM, Wi-Fi 802.11 b/g/n) | Edge controller, hardware crypto, NTP client, HTTPS client |
| **RFID Reader Module** | MFRC522 (RC522) 13.56 MHz RFID Transceiver (SPI Interface) | Reads ISO/IEC 14443A RFID tags (Mifare Classic 1K / NTAG213) |
| **Antenna / Tags** | 13.56 MHz High-Frequency (HF) adhesive tags & PVC Member Cards | Physical asset tagging (Books & Patron ID cards) |
| **Audio-Visual Feedback** | Active Piezo Buzzer (5V) + Green/Red 5mm LEDs + 220Ω Resistors | Local sensory feedback (Checkout OK vs Theft Alarm) |
| **Power Supply** | 5V / 2A Micro-USB adapter | Reliable power for MCU and RF field generation |

---

## 2. Wiring & Pinout Diagram

The MFRC522 communicates with the ESP32 via the primary Hardware VSPI bus.

```
       ESP32 DevKit V1                          MFRC522 (RC522)
   ┌──────────────────────┐                 ┌──────────────────────┐
   │                 3V3  │─────────────────│  VCC (3.3V ONLY)     │
   │                 GND  │─────────────────│  GND                 │
   │           GPIO 22    │─────────────────│  RST (Reset)         │
   │           GPIO 5     │─────────────────│  SDA / SS (Slave Sel)│
   │           GPIO 18    │─────────────────│  SCK (SPI Clock)     │
   │           GPIO 19    │─────────────────│  MISO                │
   │           GPIO 23    │─────────────────│  MOSI                │
   │                      │                 └──────────────────────┘
   │           GPIO 2     │──[ 220Ω ]──> [Green LED (Success)]
   │           GPIO 4     │──[ 220Ω ]──> [Red LED (Alarm)]
   │           GPIO 15    │────────────> [Piezo Buzzer (+)]
   └──────────────────────┘
```

> [!CAUTION]
> **Voltage Warning**: The MFRC522 chip operates strictly on **3.3V**. Connecting VCC to the 5V / VIN pin of the ESP32 will permanently damage the RC522 transceiver IC.

---

## 3. Edge Computing & Security Architecture

### 3.1 Hardware Debouncing
Physical RFID antennas continuously emit a 13.56MHz electromagnetic interrogation field. When a book tag lingers near the reader antenna, the hardware generates a burst of 3 to 10 duplicate scans within 500ms.
- **Edge Layer**: The ESP32 firmware caches the `lastScannedUID` and timestamp, suppressing consecutive reads of the same tag within a 2000ms window.
- **Cloud Layer**: The FastAPI backend reinforces this with a distributed sliding-window debounce filter (`RFID_DEBOUNCE_WINDOW_SECONDS=2.0`), protecting against network-level replays and multiple reader collisions.

### 3.2 Cryptographic Signing (Edge-to-Cloud IAM)
Every scan payload is authenticated using **HMAC-SHA256**:
$$\text{Signature} = \text{HMAC-SHA256}(K_{\text{device}}, \text{ReaderID} \parallel \text{TagUID} \parallel \text{Timestamp} \parallel \text{Nonce})$$

- **Entropy**: Nonces are generated using the ESP32 hardware True Random Number Generator (`esp_random()`).
- **Clock Sync**: The ESP32 synchronizes its internal RTC via NTP (`pool.ntp.org`) upon boot.
- **Hardware Acceleration**: The `mbedtls` cryptographic engine on the ESP32 executes SHA-256 operations in hardware registers, completing HMAC calculation in under 1.2ms.

---

## 4. HF (13.56 MHz) vs. UHF (860–960 MHz) Trade-Off Analysis

| Feature | High-Frequency (HF) / NFC (In Our Reference) | Ultra-High-Frequency (UHF) EPC Gen2 (Enterprise Target) |
|---|---|---|
| **Standard** | ISO/IEC 14443A / ISO 15693 | EPC Class 1 Gen 2 / ISO 18000-6C |
| **Operating Frequency** | 13.56 MHz | 860 – 960 MHz |
| **Read Range** | 2 cm – 10 cm (Near-field inductive) | 1 m – 12 m (Far-field radiative) |
| **Multi-Tag Anti-Collision** | Moderate (10–30 tags/sec) | Exceptional (500–1000 tags/sec) |
| **Ideal Kiosk Role** | Self-checkout kiosks, Return drop chute, Member cards | Rapid inventory shelf sweeps, walk-through security gates |
| **Hardware Cost** | Low (~$2 for RC522, ~$0.08 per tag) | High (~$80-$300 for UHF module, ~$0.15 per tag) |
| **Water/Body Detuning** | Minimal absorption by human body/liquids | Readily absorbed by moisture and body tissue |

---

## 5. Arduino IDE Flashing Guide

1. Open Arduino IDE (v2.0 or newer).
2. Install the **ESP32 Board Package** via Boards Manager: `https://raw.githubusercontent.com/espressif/arduino-esp32/gh-pages/package_esp32_index.json`.
3. Install the **MFRC522** library by `GithubCommunity` (Library Manager -> Search "MFRC522").
4. Open [`esp32_rfid_reader.ino`](./esp32_rfid_reader.ino).
5. Update `WIFI_SSID`, `WIFI_PASSWORD`, `API_ENDPOINT`, and `HMAC_SECRET` to match your local setup.
6. Select Board: `DOIT ESP32 DEVKIT V1` and Serial Port.
7. Click **Upload** and monitor at 115200 baud.
