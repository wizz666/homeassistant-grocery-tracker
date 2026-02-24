# 🛒 Home Assistant Grocery Tracker

> Håll koll på ditt kylskåp och skafferi, minska matsvinn och få receptförslag — direkt i Home Assistant.

[![HA Version](https://img.shields.io/badge/HA-2024.1%2B-blue)](https://www.home-assistant.io)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![pyscript](https://img.shields.io/badge/kräver-pyscript-orange)](https://github.com/custom-components/pyscript)
[![Version](https://img.shields.io/badge/version-1.1-brightgreen)]()

---

## Vad gör det?

- 📷 **Skanna streckkoder** via mobilkameran eller dedikerade ESP32-stationer
- 🔍 **Automatisk produktinfo** från [Open Food Facts](https://world.openfoodfacts.org) (3M+ produkter)
- 📦 **Lagerspårning** — antal, enhet, bäst-före-datum
- ✏️ **Manuell inmatning** för varor utan streckkod (ägg, lösvikt)
- ⚠️ **Daglig påminnelse kl 16:00** om vad som snart går ut
- 🗑️ **Svinndagbok** — se vad du slänger över tid
- 📱 **iPhone-stöd** via iOS Genvägar
- 🔌 **ESP32-stationer** — en i köket (lägg till), en vid soporna (ta bort)

---

## Krav

- Home Assistant 2024.1+
- [pyscript](https://github.com/custom-components/pyscript) (installeras via HACS)
- Internetåtkomst (för Open Food Facts-lookup)

---

## Installation

### 1. Installera pyscript (om det inte redan är gjort)

HACS → Integrationer → sök **pyscript** → Installera.

Lägg sedan till i `configuration.yaml`:
```yaml
pyscript:
  allow_all_imports: true
  hass_is_global: true
```

### 2. Kopiera filer

Kopiera följande filer till din HA-konfigurationsmapp:

| Fil | Destination |
|-----|-------------|
| `pyscript/grocery_tracker.py` | `/config/pyscript/grocery_tracker.py` |
| `www/grocery-scanner-card.js` | `/config/www/grocery-scanner-card.js` |
| `packages/grocery.yaml` | `/config/packages/grocery.yaml` |

Se till att packages är aktiverat i `configuration.yaml`:
```yaml
homeassistant:
  packages: !include_dir_named packages
```

### 3. Starta om Home Assistant

Fullständig omstart krävs: **Inställningar → System → Starta om → Starta om Home Assistant**

### 4. Registrera Lovelace-resurs

**Inställningar → Dashboards → ⋮ → Resurser → Lägg till resurs**

```
URL:  /local/grocery-scanner-card.js
Typ:  JavaScript-modul
```

Gör en hård-refresh av webbläsaren efteråt.

### 5. Lägg till kortet på en dashboard

Redigera valfri dashboard → Lägg till kort → Manuellt → klistra in:

```yaml
type: custom:grocery-scanner-card
title: Matscanner
ios_shortcut_add: "Lägg till vara"
ios_shortcut_remove: "Ta bort vara"
```

### 6. Verifiera sensorerna

**Developer Tools → Stater** — sök `grocery`:

| Entitet | Förväntat värde |
|---------|----------------|
| `sensor.grocery_total_items` | `0` |
| `sensor.grocery_expiring_soon` | `0` |
| `sensor.grocery_expired` | `0` |

---

## Kortkonfiguration

```yaml
type: custom:grocery-scanner-card
title: Matscanner                        # valfritt
ios_shortcut_add: "Lägg till vara"       # namn på din iOS Genväg
ios_shortcut_remove: "Ta bort vara"      # namn på din iOS Genväg
```

---

## Plattformsstöd

| Plattform | Skanningsmetod |
|-----------|---------------|
| Android (HA-appen / Chrome) | Native BarcodeDetector → jsQR-fallback |
| iPhone | **iOS Genvägar** (primär metod) — HA Companion App blockerar kameraåtkomst |
| Desktop | jsQR via kamera |

> **iPhone:** HA Companion App's WebView blockerar kameraåtkomst, så kameraskanning fungerar inte på iPhone. iOS Genvägar är den rekommenderade och verifierade metoden.

### iPhone — iOS Genvägar

Se [docs/ios_shortcuts_sv.md](docs/ios_shortcuts_sv.md) för steg-för-steg-instruktioner.

---

## Tillgängliga tjänster

| Tjänst | Parametrar | Beskrivning |
|--------|-----------|-------------|
| `pyscript.grocery_scan_add` | `barcode`, `quantity`, `expiry_date`, `source` | Lägg till vara via streckkod |
| `pyscript.grocery_scan_remove` | `barcode`, `source` | Ta bort/minska vara via streckkod |
| `pyscript.grocery_manual_add` | `name`, `quantity`, `unit`, `expiry_date`, `category`, `barcode` | Lägg till manuellt |
| `pyscript.grocery_manual_remove` | `item_id` | Ta bort via ID |
| `pyscript.grocery_set_expiry` | `item_id`, `expiry_date` | Uppdatera bäst-före-datum |
| `pyscript.grocery_refresh` | — | Ladda om lager från fil |

---

## ESP32-stationer (valfritt)

För dedikerade scannerenheter i köket och vid soporna — se [docs/esp32_hardware_sv.md](docs/esp32_hardware_sv.md).

---

## Ändringslogg

### v1.1 (2026-02-24)
- **Buggfix:** pyscript blockerar `open()` — fil-I/O använder nu `pathlib.Path.read_text/write_text` via `task.executor`
- **Buggfix:** iOS webhook-automation kraschade med `trigger.data.barcode` — nu säker `.get()`-åtkomst
- **Buggfix:** Open Food Facts-lookup använder nu `aiohttp` (async) istället för `requests` i executor
- **Förtydligat:** iPhone-kameraskanning stöds ej i HA Companion App — iOS Genvägar är primär metod

### v1.0 (2026-02-23)
- Första release

---

## Licens

MIT — se [LICENSE](LICENSE)
