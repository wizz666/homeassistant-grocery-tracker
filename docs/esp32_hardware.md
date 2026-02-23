# ESP32 Scanner Stations

Optional physical barcode scanner stations using ESP32 + GM65 barcode module.

## Why hardware scanners?

- Always on — no phone needed
- Instant scan, no app to open
- Kitchen station adds items when unpacking groceries
- Trash station removes items when discarding packaging

## Hardware (per station)

| Component | Price (approx) | Notes |
|-----------|---------------|-------|
| ESP32 DevKit v1 | €5–8 | Any ESP32 board works |
| GM65 Barcode Scanner Module | €8–15 | From AliExpress, UART interface |
| Piezo buzzer | €0.50 | Optional, for beep confirmation |
| LED | €0.10 | Optional, status indicator |
| USB power supply | €3–5 | 5V/1A |
| **Total per station** | **~€20** | |

## Wiring

```
GM65 Module        ESP32
──────────         ──────
VCC (3.3V) ──────→ 3.3V
GND        ──────→ GND
TX         ──────→ GPIO16 (RX2)
RX         ──────→ GPIO17 (TX2)

Optional:
LED +      ──────→ GPIO2 (via 220Ω resistor)
Buzzer +   ──────→ GPIO15
```

> **Note:** Some GM65 modules require 5V. Check your module's datasheet.

## ESPHome setup

Flash the appropriate ESPHome config:

- **Kitchen station** (adds items): `esphome/grocery_kitchen.yaml`
- **Trash station** (removes items): `esphome/grocery_trash.yaml`

Before flashing, add to your `secrets.yaml`:
```yaml
wifi_ssid: "YourWiFiName"
wifi_password: "YourWiFiPassword"
api_encryption_key: "your32charbase64key=="
ota_password: "your_ota_password"
```

Generate an API encryption key:
```bash
python3 -c "import secrets; print(secrets.token_base64(32))"
```

## GM65 Configuration

The GM65 is plug-and-play at 9600 baud. For best results:

1. **Auto-scan mode** (default): Scanner continuously scans when it detects a barcode
2. **Host trigger mode**: Scanner only scans when it receives a trigger command (UART)

The ESPHome config supports both modes. The boot button (GPIO0) sends a trigger command for host mode.

## LED feedback

| Station | Signal | Meaning |
|---------|--------|---------|
| Kitchen | 1× blink + 1 beep | Item added |
| Trash   | 2× blink + 2 beeps | Item removed |

## How it works

1. Scan barcode → GM65 sends barcode string via UART
2. ESPHome reads string → fires `grocery_scan` HA event
3. HA automation receives event → calls pyscript service
4. Kitchen: `pyscript.grocery_scan_add`
5. Trash: `pyscript.grocery_scan_remove`

## Enclosure ideas

- 3D print a wall-mounted bracket
- Use a project box from electronics store
- Mount the GM65 at an angle for easy scanning
- Kitchen: mount near fridge or countertop
- Trash: mount near recycling bin at comfortable height
