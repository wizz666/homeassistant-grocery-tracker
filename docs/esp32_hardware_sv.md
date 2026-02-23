# ESP32 Scanner-stationer

Valfria fysiska streckkodsscanner-stationer med ESP32 + GM65-modul.

## Varför hårdvaruscannrar?

- Alltid på — ingen telefon behövs
- Omedelbar skanning, ingen app att öppna
- Kök-station lägger till varor när du packar upp
- Sop-station tar bort varor när du slänger förpackningar

## Hårdvara (per station)

| Komponent | Pris (ca) | Notering |
|-----------|----------|---------|
| ESP32 DevKit v1 | 80 kr | Valfritt ESP32-kort |
| GM65 Barcode Scanner Module | 100–150 kr | AliExpress, UART-gränssnitt |
| Piezo-buzzer | 5 kr | Valfritt, bekräftelsepip |
| LED | 1 kr | Valfritt, statusindikator |
| USB-strömförsörjning 5V/1A | 30–50 kr | |
| **Totalt per station** | **~250 kr** | |

## Kopplingsschema

```
GM65-modul         ESP32
──────────         ──────
VCC (3.3V) ──────→ 3.3V
GND        ──────→ GND
TX         ──────→ GPIO16 (RX2)
RX         ──────→ GPIO17 (TX2)

Valfritt:
LED +      ──────→ GPIO2 (via 220Ω motstånd)
Buzzer +   ──────→ GPIO15
```

> **OBS:** Vissa GM65-moduler kräver 5V. Kontrollera ditt moduls datablad.

## ESPHome-installation

Flasha rätt ESPHome-konfiguration:

- **Kök-station** (lägger till): `esphome/grocery_kitchen.yaml`
- **Sop-station** (tar bort): `esphome/grocery_trash.yaml`

Lägg till i din `secrets.yaml` innan flashning:
```yaml
wifi_ssid: "DittWiFiNamn"
wifi_password: "DittWiFiLösenord"
api_encryption_key: "din32teckenlångbase64nyckel=="
ota_password: "ditt_ota_lösenord"
```

## Hur det fungerar

1. Skanna streckkod → GM65 skickar streckkodssträng via UART
2. ESPHome läser strängen → skickar `grocery_scan`-event till HA
3. HA-automation tar emot event → anropar pyscript-service
4. Kök: `pyscript.grocery_scan_add`
5. Sopor: `pyscript.grocery_scan_remove`

## LED-feedback

| Station | Signal | Betydelse |
|---------|--------|-----------|
| Kök | 1× blink + 1 pip | Vara tillagd |
| Sopor | 2× blink + 2 pip | Vara borttagen |

## Höljesidéer

- 3D-printa en väggfäste
- Använd en projektlåda från en elektronikbutik
- Montera GM65 i vinkel för enkel skanning
- Kök: montera nära kylskåp eller bänkskiva
- Sopor: montera vid källsorteringskärlet i bekväm höjd
