/*
 * Cloud-Native RFID Library System - ESP32 Edge Reader Firmware
 * Hardware: ESP32 DevKit V1 + MFRC522 (RC522) RFID Module (SPI)
 * 
 * Features:
 * - SPI Interface to MFRC522 13.56MHz RFID Reader
 * - WiFi connectivity + NTP network time synchronization
 * - Hardware Debounce: Suppresses repeated burst reads within 2000ms
 * - Cryptographic Edge Security: Hardware HMAC-SHA256 signature via mbedtls
 * - Secure HTTPS/HTTP JSON Ingest to Cloud API (/rfid/scan)
 * - LED / Buzzer status feedback (Success vs Alarm)
 */

#include <WiFi.h>
#include <HTTPClient.h>
#include <SPI.h>
#include <MFRC522.h>
#include "mbedtls/md.h"
#include <time.h>

// ----------------- Configuration -----------------
const char* WIFI_SSID     = "University_WiFi";
const char* WIFI_PASSWORD = "CampusSecurePassword";

// Cloud API Endpoint
const char* API_ENDPOINT  = "http://192.168.1.100:8000/rfid/scan";

// Edge Reader Identity & Pre-Shared Secret Key
const char* DEVICE_ID     = "CHECKOUT-01"; // Or RETURN-01, SHELF-CS-01, GATE-01
const char* HMAC_SECRET   = "checkout-secret-key-9988";

// Hardware Pinout (ESP32 DevKit to RC522)
#define SS_PIN    5   // VSPI SS (SDA)
#define RST_PIN   22  // Reset pin
#define LED_GREEN 2   // Built-in LED or Green OK indicator
#define LED_RED   4   // Red Warning/Alarm indicator
#define BUZZER    15  // Active Piezo Buzzer

// NTP Server Settings for UTC Epoch Timestamp
const char* NTP_SERVER    = "pool.ntp.org";
const long  GMT_OFFSET_SEC = 0;       // UTC
const int   DAYLIGHT_OFFSET = 0;

// Hardware Debounce Cache
String lastScannedUID = "";
unsigned long lastScanMillis = 0;
const unsigned long DEBOUNCE_WINDOW_MS = 2000; // 2 seconds

MFRC522 mfrc522(SS_PIN, RST_PIN);

// ----------------- Function Declarations -----------------
void connectToWiFi();
void syncNTPTime();
unsigned long getEpochTime();
String generateNonce();
String computeHMACSHA256(const String& payload, const char* key);
void sendScanEvent(const String& tagUID);
void signalSuccess();
void signalAlarm();

void setup() {
  Serial.begin(115200);
  delay(1000);
  Serial.println("\n==============================================");
  Serial.println("  ESP32 RFID Cloud Edge Terminal Initializing ");
  Serial.println("==============================================");

  pinMode(LED_GREEN, OUTPUT);
  pinMode(LED_RED, OUTPUT);
  pinMode(BUZZER, OUTPUT);
  digitalWrite(LED_GREEN, LOW);
  digitalWrite(LED_RED, LOW);
  digitalWrite(BUZZER, LOW);

  // Initialize SPI bus and RC522 Reader
  SPI.begin();
  mfrc522.PCD_Init();
  delay(50);
  mfrc522.PCD_DumpVersionToSerial();

  // Connect to Network
  connectToWiFi();
  syncNTPTime();

  Serial.println("[STATUS] Edge Reader Ready. Waiting for RFID Tag tap...\n");
  digitalWrite(LED_GREEN, HIGH);
  delay(200);
  digitalWrite(LED_GREEN, LOW);
}

void loop() {
  // Check if WiFi is still connected
  if (WiFi.status() != WL_CONNECTED) {
    connectToWiFi();
  }

  // Look for new RFID card presence
  if (!mfrc522.PICC_IsNewCardPresent()) {
    return;
  }

  // Read card serial (UID)
  if (!mfrc522.PICC_ReadCardSerial()) {
    return;
  }

  // Convert UID bytes to Hex string
  String tagUID = "";
  for (byte i = 0; i < mfrc522.uid.size; i++) {
    if (mfrc522.uid.uidByte[i] < 0x10) tagUID += "0";
    tagUID += String(mfrc522.uid.uidByte[i], HEX);
  }
  tagUID.toUpperCase();

  // Edge Hardware Debounce Check (2000ms window)
  unsigned long now = millis();
  if (tagUID == lastScannedUID && (now - lastScanMillis < DEBOUNCE_WINDOW_MS)) {
    Serial.printf("[EDGE DEBOUNCE] Suppressed duplicate burst read of %s within %lums\n", 
                  tagUID.c_str(), now - lastScanMillis);
    mfrc522.PICC_HaltA();
    mfrc522.PCD_StopCrypto1();
    return;
  }

  lastScannedUID = tagUID;
  lastScanMillis = now;

  Serial.printf("\n[SCAN DETECTED] Tag UID: %s\n", tagUID.c_str());

  // Transmit signed event to cloud
  sendScanEvent(tagUID);

  // Halt PICC
  mfrc522.PICC_HaltA();
  mfrc522.PCD_StopCrypto1();
}

// ----------------- Network & Time -----------------
void connectToWiFi() {
  Serial.printf("[WiFi] Connecting to %s ", WIFI_SSID);
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

  int attempts = 0;
  while (WiFi.status() != WL_CONNECTED && attempts < 20) {
    delay(500);
    Serial.print(".");
    attempts++;
  }

  if (WiFi.status() == WL_CONNECTED) {
    Serial.printf("\n[WiFi] Connected! IP Address: %s\n", WiFi.localIP().toString().c_str());
  } else {
    Serial.println("\n[WiFi] Connection timeout. Operating in retry loop.");
  }
}

void syncNTPTime() {
  Serial.println("[NTP] Synchronizing Real-Time Clock...");
  configTime(GMT_OFFSET_SEC, DAYLIGHT_OFFSET, NTP_SERVER);

  struct tm timeinfo;
  if (!getLocalTime(&timeinfo)) {
    Serial.println("[NTP] Failed to obtain time from NTP server.");
    return;
  }
  Serial.printf("[NTP] Synchronized UTC: %04d-%02d-%02d %02d:%02d:%02d\n",
                timeinfo.tm_year + 1900, timeinfo.tm_mon + 1, timeinfo.tm_mday,
                timeinfo.tm_hour, timeinfo.tm_min, timeinfo.tm_sec);
}

unsigned long getEpochTime() {
  time_t now;
  struct tm timeinfo;
  if (!getLocalTime(&timeinfo)) {
    return (unsigned long)(millis() / 1000);
  }
  time(&now);
  return (unsigned long)now;
}

// ----------------- Cryptographic Security -----------------
String generateNonce() {
  // Uses ESP32 True Random Number Generator (TRNG)
  uint32_t r1 = esp_random();
  uint32_t r2 = esp_random();
  char nonceBuf[17];
  snprintf(nonceBuf, sizeof(nonceBuf), "%08x%08x", r1, r2);
  return String(nonceBuf);
}

String computeHMACSHA256(const String& payload, const char* key) {
  byte hmacResult[32];
  mbedtls_md_context_t ctx;
  mbedtls_md_type_t md_type = MBEDTLS_MD_SHA256;

  mbedtls_md_init(&ctx);
  mbedtls_md_setup(&ctx, mbedtls_md_info_from_type(md_type), 1);
  mbedtls_md_hmac_starts(&ctx, (const unsigned char*)key, strlen(key));
  mbedtls_md_hmac_update(&ctx, (const unsigned char*)payload.c_str(), payload.length());
  mbedtls_md_hmac_finish(&ctx, hmacResult);
  mbedtls_md_free(&ctx);

  String hexSig = "";
  for (int i = 0; i < 32; i++) {
    if (hmacResult[i] < 0x10) hexSig += "0";
    hexSig += String(hmacResult[i], HEX);
  }
  return hexSig;
}

// ----------------- Cloud Ingestion -----------------
void sendScanEvent(const String& tagUID) {
  unsigned long timestamp = getEpochTime();
  String nonce = generateNonce();

  // Signature canonical format: f"{device_id}:{tag_uid}:{timestamp}:{nonce}"
  String canonicalPayload = String(DEVICE_ID) + ":" + tagUID + ":" + String(timestamp) + ":" + nonce;
  String signature = computeHMACSHA256(canonicalPayload, HMAC_SECRET);

  // Construct JSON body
  String jsonBody = "{"
    "\"reader_id\":\"" + String(DEVICE_ID) + "\","
    "\"tag_uid\":\"" + tagUID + "\","
    "\"timestamp\":" + String(timestamp) + ","
    "\"nonce\":\"" + nonce + "\","
    "\"signature\":\"" + signature + "\""
  "}";

  Serial.println("[HTTP] Transmitting HMAC-signed payload to cloud API:");
  Serial.println(jsonBody);

  HTTPClient http;
  http.begin(API_ENDPOINT);
  http.addHeader("Content-Type", "application/json");

  int httpCode = http.POST(jsonBody);

  if (httpCode > 0) {
    String response = http.getString();
    Serial.printf("[HTTP] Status: %d | Response: %s\n", httpCode, response.c_str());

    if (httpCode == 200) {
      if (response.indexOf("\"status\":\"alert\"") != -1) {
        signalAlarm();
      } else {
        signalSuccess();
      }
    } else {
      signalAlarm();
    }
  } else {
    Serial.printf("[HTTP] POST failed. Error: %s\n", http.errorToString(httpCode).c_str());
    digitalWrite(LED_RED, HIGH);
    delay(500);
    digitalWrite(LED_RED, LOW);
  }

  http.end();
}

void signalSuccess() {
  digitalWrite(LED_GREEN, HIGH);
  tone(BUZZER, 2000, 100);
  delay(120);
  tone(BUZZER, 2500, 150);
  delay(200);
  digitalWrite(LED_GREEN, LOW);
}

void signalAlarm() {
  for (int i = 0; i < 3; i++) {
    digitalWrite(LED_RED, HIGH);
    tone(BUZZER, 800, 150);
    delay(150);
    digitalWrite(LED_RED, LOW);
    delay(80);
  }
}
