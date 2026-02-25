# 🛒 Home Assistant Grocery Tracker

> Track your pantry inventory, reduce food waste, and get recipe suggestions — all from Home Assistant.

[![HA Version](https://img.shields.io/badge/HA-2024.1%2B-blue)](https://www.home-assistant.io)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![pyscript](https://img.shields.io/badge/requires-pyscript-orange)](https://github.com/custom-components/pyscript)
[![Version](https://img.shields.io/badge/version-1.6-brightgreen)]()
[![Ko-fi](https://img.shields.io/badge/Ko--fi-Support_this_project-F16061?logo=ko-fi&logoColor=white)](https://ko-fi.com/wizz666)

**Svenska instruktioner:** [README_SV.md](README_SV.md)

---

## What it does

- 📷 **Scan barcodes** via phone camera or dedicated ESP32 scanner stations
- 🔍 **Auto-lookup** product info from [Open Food Facts](https://world.openfoodfacts.org) (3M+ products)
- 📦 **Track your inventory** — quantity, unit, expiry dates, location
- ✏️ **Manual entry** for items without barcodes (eggs, bulk goods)
- 📅 **Set expiry dates** — tap any item in the inventory to set or edit its best-before date
- ⚠️ **Daily expiry alerts** at 16:00 listing what's about to expire
- 🧊 **Location tags** — track items by fridge, freezer or pantry with filter buttons
- 🟠 **Low-stock alerts** — per-item configurable minimum quantity threshold
- 🛒 **Shopping list integration** — auto-adds items when they run out or expire
- 📲 **Push shopping list** to your phone with one tap, opens list directly in HA app
- 🗑️ **Waste log dashboard** — full history of discarded items, grouped by month
- 👨‍🍳 **AI recipe suggestions** — get recipe ideas for ingredients about to expire (Groq, Gemini, Anthropic or HA AI Task)
- ⚙️ **Settings tab in dashboard** — configure recipe provider and API key directly in the UI
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
- HA **Shopping List** integration (built-in, required for shopping list features)
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

### 2. Enable the Shopping List integration

**Settings → Devices & Services → Add integration → search "Shopping List" → Install**

This creates the `todo.shopping_list` entity used for automatic shopping list management.

### 3. Copy files

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

### 4. (Optional) Dedicated dashboard

To get a dedicated **Grocery** entry in your HA sidebar, copy `dashboards/grocery.yaml` to `/config/dashboards/grocery.yaml` and add to `configuration.yaml`:

```yaml
lovelace:
  dashboards:
    grocery-dashboard:
      mode: yaml
      filename: dashboards/grocery.yaml
      title: Grocery
      icon: mdi:fridge
      show_in_sidebar: true
```

### 5. Restart Home Assistant

Full restart required: **Settings → System → Restart → Restart Home Assistant**

### 6. Register Lovelace resource

**Settings → Dashboards → ⋮ → Resources → Add resource**

```
URL:  /local/grocery-scanner-card.js
Type: JavaScript module
```

Hard-refresh your browser after adding.

### 7. Add the card to a dashboard

Either use the dedicated dashboard (step 4) or add the card manually:

```yaml
type: custom:grocery-scanner-card
title: Grocery Scanner
ios_shortcut_add: "Add item"
ios_shortcut_remove: "Remove item"
```

### 8. Verify sensors

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
| `pyscript.grocery_scan_add` | `barcode`, `quantity`, `expiry_date`, `source`, `location`, `name_override` | Add item by barcode |
| `pyscript.grocery_scan_remove` | `barcode`, `source` | Remove/decrement item by barcode (logs to waste log even if not in inventory) |
| `pyscript.grocery_manual_add` | `name`, `quantity`, `unit`, `expiry_date`, `category`, `barcode`, `location`, `min_quantity` | Add item manually |
| `pyscript.grocery_manual_remove` | `item_id` | Remove item by ID (logs to waste log) |
| `pyscript.grocery_set_expiry` | `item_id`, `expiry_date` | Update expiry date |
| `pyscript.grocery_set_min_quantity` | `item_id`, `min_quantity` | Set low-stock alert threshold (0 = disabled) |
| `pyscript.grocery_set_location` | `item_id`, `location` | Set item location: `kyl`, `frys` or `skafferi` |
| `pyscript.grocery_refresh` | — | Reload inventory from file |
| `pyscript.grocery_push_shopping_list` | — | Push shopping list as notification to all devices |
| `pyscript.grocery_generate_shopping_list` | — | Add all expired/expiring items to shopping list |
| `pyscript.grocery_suggest_recipes` | — | Get AI recipe suggestions for expiring ingredients |

---

## Sensors

| Entity | Description |
|--------|-------------|
| `sensor.grocery_total_items` | Total items in inventory (attributes: full items list) |
| `sensor.grocery_expiring_soon` | Items expiring within 2 days |
| `sensor.grocery_expired` | Expired items |
| `sensor.grocery_low_stock` | Items at or below their minimum quantity threshold |
| `sensor.grocery_waste_log` | Total discarded items (attributes: full waste log, last 100 entries) |

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

- [x] AI recipe suggestions based on expiring ingredients (Groq / Gemini / Anthropic / HA AI Task)
- [x] Shopping list integration (HA built-in)
- [x] Low-stock alerts (configurable per-item threshold)
- [x] Location tags (fridge / freezer / pantry)
- [x] Waste log dashboard with monthly summary
- [ ] ESPHome weight sensors for bulk items (coffee, flour)
- [ ] Weekly waste report (Monday summary notification)
- [ ] HACS packaging

---

## Support

If you find this useful, a coffee is always appreciated ☕

[![ko-fi](https://ko-fi.com/img/githubbutton_sm.svg)](https://ko-fi.com/wizz666)

## Credits

- Product data: [Open Food Facts](https://world.openfoodfacts.org) (CC BY-SA)
- Barcode decoding: [jsQR](https://github.com/cozmo/jsQR) (Apache 2.0)

## Changelog

### v1.6 (2026-02-25)
- **New:** AI recipe suggestions — when items are about to expire, get recipe ideas via push notification
- **New:** Multi-provider LLM support: Groq (free), Google Gemini (free), Anthropic (paid), HA AI Task (no key needed)
- **New:** Auto-fallback — if a provider is selected but API key is missing, falls back to `ha_ai_task` automatically
- **New:** Settings tab in the dashboard — choose provider and enter API key directly in the UI (no more Settings → Helpers)
- **New:** Daily expiry alert (16:00) now also triggers recipe suggestions if a provider is configured
- **New:** `grocery_suggest_recipes` service — trigger recipe suggestions manually from the dashboard

### v1.5 (2026-02-25)
- **New:** Waste log dashboard — new "Svinndagbok" sidebar view with monthly summary and full history grouped by month
- **New:** `sensor.grocery_waste_log` — tracks all discarded items with date, name and source
- **New:** Tap any item row in the inventory to set or edit its best-before date inline (iOS compatible)
- **Fixed:** `grocery_manual_remove` (trash button) now logs to waste log
- **Fixed:** `grocery_scan_remove` now logs to waste log even when item is not in inventory — does Open Food Facts lookup for the name
- **Fixed:** Shopping list duplicate check used wrong field (`summary` → `name`)
- **Fixed:** `name_override` parameter added to `grocery_scan_add` so manually entered names are used when product is not found in Open Food Facts

### v1.4 (2026-02-25)
- **New:** Location tags per item — fridge (`kyl`), freezer (`frys`) or pantry (`skafferi`)
- **New:** Location filter buttons in inventory tab with item counts per location
- **New:** Low-stock alerts — set a minimum quantity per item; item is flagged 🟠 and added to shopping list when stock falls to or below threshold
- **New:** `sensor.grocery_low_stock` sensor
- **New:** Services `grocery_set_min_quantity` and `grocery_set_location`
- **Updated:** `grocery_scan_add` — new `location` parameter
- **Updated:** `grocery_manual_add` — new `location` and `min_quantity` parameters

### v1.3 (2026-02-24)
- **New:** Shopping list integration — items automatically added to `todo.shopping_list` when last unit is removed or when they expire
- **New:** `grocery_push_shopping_list` service — sends current shopping list as push notification with tap-to-open
- **New:** `grocery_generate_shopping_list` service — manually add all expired/expiring items to shopping list
- **New:** Dedicated sidebar dashboard (Matlagret) with scanner view and shopping list view
- **New:** Daily 16:00 alert also auto-adds expiring items to shopping list (once per item, via `shopping_list_suggested` flag)
- **Fixed:** Shopping list read via `/config/.shopping_list.json` directly (Supervisor API not available in pyscript context)
- **Requires:** HA Shopping List integration enabled (Settings → Devices & Services → Shopping List)

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
