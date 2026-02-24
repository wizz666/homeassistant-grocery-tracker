# Android Setup

This guide covers barcode scanning on Android phones. There are two methods — try Method 1 first, it may work straight away.

---

## Method 1 — Lovelace card (camera in browser)

Unlike iPhone, Android allows camera access inside the HA Companion App and Chrome. The Grocery Scanner card uses the native `BarcodeDetector` API on Android (with jsQR as fallback), so it may work out of the box with no extra setup.

### Steps

1. Open **Home Assistant** in the HA Companion App or Chrome on your Android phone
2. Navigate to the dashboard with the Grocery Scanner card
3. Tap the **camera tab** (📷)
4. When prompted, tap **Allow** for camera access
5. Point at a barcode — it should scan automatically

If the card scans successfully and you see a confirmation notification in HA, you're done. No further setup needed.

---

## Method 2 — HTTP Shortcuts app (home screen button)

If the camera card doesn't work, or if you prefer a dedicated home screen button (similar to the iOS Shortcuts approach), use the free **HTTP Shortcuts** app.

**HTTP Shortcuts** by Roland Lötscher — [Google Play](https://play.google.com/store/apps/details?id=ch.rmy.android.http_shortcuts)

This app lets you create home screen buttons that open the camera, scan a barcode, and automatically POST the result to your HA webhook — no technical knowledge required.

### Prerequisites

- Android phone with Google Play
- Home Assistant accessible from your phone (local or remote URL)
- Grocery Tracker installed and running

### Step 1 — Find your webhook URLs

```
https://YOUR-HA-URL/api/webhook/grocery_add
https://YOUR-HA-URL/api/webhook/grocery_remove
```

Find your HA URL in: **HA App → Settings → Companion App → Server address**

For remote access, use your external URL (Nabu Casa, reverse proxy, etc.).

### Step 2 — Install HTTP Shortcuts

Install **HTTP Shortcuts** from Google Play (free, no ads).

### Step 3 — Create "Add item" shortcut

1. Open HTTP Shortcuts
2. Tap **+** → **Regular Shortcut**
3. Fill in:
   - **Name:** `Add item`
   - **Method:** `POST`
   - **URL:** `https://YOUR-HA-URL/api/webhook/grocery_add`
4. Go to the **Request Body** tab:
   - Type: **Custom text / JSON**
   - Content type: `application/json`
   - Body:
     ```json
     {"barcode": "{{barcode}}"}
     ```
5. Go to the **Variables** tab:
   - Tap **+** → **Barcode Scanner**
   - Name: `barcode`
6. Tap **Save**

### Step 4 — Create "Remove item" shortcut

Repeat Step 3 but:
- **Name:** `Remove item`
- **URL:** `https://YOUR-HA-URL/api/webhook/grocery_remove`
- Body and variable identical

### Step 5 — Add to home screen

1. Long-press the shortcut in HTTP Shortcuts
2. Tap **Place on Home Screen**
3. Repeat for the remove shortcut

### Usage

1. Tap **Add item** on your home screen
2. Camera opens automatically
3. Point at barcode → scanned
4. HA receives the barcode, looks up the product in Open Food Facts
5. A notification confirms the item was added

---

## Comparison

| Method | Setup | Works offline | Home screen button |
|--------|-------|--------------|-------------------|
| Lovelace card | None | No | No (open HA app) |
| HTTP Shortcuts | ~5 min | No | Yes |

---

## Troubleshooting

**Card camera doesn't open**
- Make sure you're using Chrome or the HA Companion App (not Firefox)
- Check that camera permission is granted for the app in Android Settings

**HTTP Shortcuts: "Connection refused" or no response**
- Verify your HA URL is reachable from the phone
- Try opening the URL in Chrome first
- If using HTTP (not HTTPS), enable "Allow cleartext traffic" in HTTP Shortcuts settings

**Item not added / sensor stays at 0**
- Check HA logs: **Settings → System → Logs** → search `grocery`
- Verify the webhook automation is enabled: **Settings → Automations** → search `grocery`
