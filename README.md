# 🛒 Home Assistant Grocery Tracker

> Track your pantry inventory, reduce food waste, and get recipe suggestions — all from Home Assistant.

[![HA Version](https://img.shields.io/badge/HA-2024.1%2B-blue)](https://www.home-assistant.io)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![pyscript](https://img.shields.io/badge/requires-pyscript-orange)](https://github.com/custom-components/pyscript)
[![Version](https://img.shields.io/badge/version-1.1-brightgreen)]()

**Svenska instruktioner:** [README_SV.md](README_SV.md)

---

## What it does

- 📷 **Scan barcodes** via phone camera or dedicated ESP32 scanner stations
- 🔍 **Auto-lookup** product info from [Open Food Facts](https://world.openfoodfacts.org) (3M+ products)
- 📦 **Track your inventory** — quantity, unit, expiry dates
- ✏️ **Manual entry** for items without barcodes (eggs, bulk goods)
- ⚠️ **Daily expiry alerts** at 16:00 listing what's about to expire
- 🗑️ **Waste logging** — track what you throw away over time
- 📱 **iPhone support** via iOS Shortcuts
- 🔌 **ESP32 stations** — one in the kitchen (add), one at the bin (remove)

## Screenshots

| Scanner Card | Inventory | Expiry Alert |
|---|---|---|
| *(scan tab)* | *(inventory tab)* | *(notification)* |

---

## Requirements

- Home Assistant 2024.1+
- [pyscript](https://github.com/custom-components/pyscript) (HACS)
- Internet access (for Open Food Facts lookups)

---

## Installation

### 1. Install pyscript (if not already installed)

In HACS → Integrations → search **pyscript** → Install.

Then add to `configuration.yaml`:
```yaml
pyscript:
  allow_all_imports: true
  hass_is_global: true
```

### 2. Copy files

Copy the following files to your HA config directory:

| Source | Destination |
|--------|-------------|
| `pyscript/grocery_tracker.py` | `/config/pyscript/grocery_tracker.py` |
| `www/grocery-scanner-card.js` | `/config/www/grocery-scanner-card.js` |
| `packages/grocery.yaml` | `/config/packages/grocery.yaml` |

Make sure packages are enabled in `configuration.yaml`:
```yaml
homeassistant:
  packages: !include_dir_named packages
```

### 3. Restart Home Assistant

Full restart required: **Settings → System → Restart → Restart Home Assistant**

### 4. Register Lovelace resource

**Settings → Dashboards → ⋮ → Resources → Add resource**

```
URL:  /local/grocery-scanner-card.js
Type: JavaScript module
```

Hard-refresh your browser after adding.

### 5. Add the card to a dashboard

Edit any dashboard → Add card → Manual → paste:

```yaml
type: custom:grocery-scanner-card
title: Grocery Scanner
ios_shortcut_add: "Add item"
ios_shortcut_remove: "Remove item"
```

### 6. Verify sensors

**Developer Tools → States** — search `grocery`:

| Entity | Expected value |
|--------|---------------|
| `sensor.grocery_total_items` | `0` |
| `sensor.grocery_expiring_soon` | `0` |
| `sensor.grocery_expired` | `0` |

---

## Card configuration

```yaml
type: custom:grocery-scanner-card
title: Grocery Scanner              # optional, card title
ios_shortcut_add: "Add item"        # iOS Shortcut name for adding
ios_shortcut_remove: "Remove item"  # iOS Shortcut name for removing
```

---

## Platform support

| Platform | Scanning method |
|----------|----------------|
| Android (HA App / Chrome) | Native BarcodeDetector API → jsQR fallback (camera works) |
| iPhone | **iOS Shortcuts** (primary) — HA Companion App WebView blocks camera access |
| Desktop | jsQR via camera |

> **iPhone note:** The HA Companion App's WebView blocks camera access, so jsQR does not work on iPhone. iOS Shortcuts is the recommended and supported method.

### Android setup

See [docs/android_setup.md](docs/android_setup.md) — try the card first, use HTTP Shortcuts app as fallback.

### iPhone / iOS Shortcuts setup

See [docs/ios_shortcuts.md](docs/ios_shortcuts.md) for step-by-step instructions.

---

## Available services

Call these from automations, scripts or Developer Tools:

| Service | Parameters | Description |
|---------|-----------|-------------|
| `pyscript.grocery_scan_add` | `barcode`, `quantity`, `expiry_date`, `source` | Add item by barcode |
| `pyscript.grocery_scan_remove` | `barcode`, `source` | Remove/decrement item by barcode |
| `pyscript.grocery_manual_add` | `name`, `quantity`, `unit`, `expiry_date`, `category`, `barcode` | Add item manually |
| `pyscript.grocery_manual_remove` | `item_id` | Remove item by ID |
| `pyscript.grocery_set_expiry` | `item_id`, `expiry_date` | Update expiry date |
| `pyscript.grocery_refresh` | — | Reload inventory from file |

---

## Sensors

| Entity | Description |
|--------|-------------|
| `sensor.grocery_total_items` | Total items in inventory (attributes: full items list) |
| `sensor.grocery_expiring_soon` | Items expiring within 2 days |
| `sensor.grocery_expired` | Expired items |

---

## ESP32 Scanner Stations (optional)

For dedicated scanner stations in the kitchen and at the bin — see [docs/esp32_hardware.md](docs/esp32_hardware.md).

**Hardware per station (~€20):**
- ESP32 DevKit v1
- GM65 Barcode Scanner Module (UART)
- Optional: LED + piezo buzzer

Kitchen station → scans **add** items
Trash station → scans **remove** items

---

## Data storage

Inventory is stored as JSON at `/config/grocery_inventory.json`:

```json
{
  "items": [
    {
      "id": "uuid",
      "barcode": "7310500143006",
      "name": "Arla Milk 1.5%",
      "category": "dairy",
      "quantity": 1,
      "unit": "st",
      "added_date": "2026-02-23",
      "expiry_date": "2026-02-28",
      "source": "mobile"
    }
  ],
  "waste_log": []
}
```

---

## Roadmap

- [ ] Claude AI recipe suggestions based on expiring ingredients
- [ ] Shopping list integration (HA built-in / Todoist)
- [ ] ESPHome weight sensors for bulk items (coffee, flour)
- [ ] Weekly waste statistics dashboard
- [ ] HACS packaging

---

## Credits

- Product data: [Open Food Facts](https://world.openfoodfacts.org) (CC BY-SA)
- Barcode decoding: [jsQR](https://github.com/cozmo/jsQR) (Apache 2.0)

## Changelog

### v1.1 (2026-02-24)
- **Fixed:** pyscript blocks the `open()` builtin — file I/O now uses `pathlib.Path.read_text/write_text` via `task.executor`
- **Fixed:** iOS webhook automation template crash (`trigger.data.barcode`) — now uses safe `.get()` access
- **Fixed:** HTTP lookups to Open Food Facts now use `aiohttp` (async) instead of `requests` in executor
- **Clarified:** iPhone camera scanning is not supported in HA Companion App — iOS Shortcuts is the primary method

### v1.0 (2026-02-23)
- Initial release

---

## License

MIT — see [LICENSE](LICENSE)
