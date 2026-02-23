# iOS Shortcuts Setup

This guide explains how to set up iPhone barcode scanning via iOS Shortcuts.

## Why Shortcuts?

The iPhone's native barcode scanner (used by Shortcuts) is faster and more reliable than browser-based scanning. It works even when the HA Companion App camera is restricted.

## Prerequisites

- iPhone with iOS 13+
- Home Assistant accessible from your phone (local or remote URL)
- Grocery Tracker installed and running

## Step 1 — Find your HA webhook URL

Your webhook URLs are:
```
https://YOUR-HA-URL/api/webhook/grocery_add
https://YOUR-HA-URL/api/webhook/grocery_remove
```

Find your HA URL in: **HA App → Settings → Companion App → Server address**

For remote access, use your external URL (Nabu Casa, reverse proxy, etc.).

## Step 2 — Create "Add item" shortcut

1. Open the **Shortcuts** app
2. Tap **+** to create a new shortcut
3. Add these actions in order:

**Action 1: Scan Barcode**
- Search for: `Scan QR Code`
- This opens the native camera scanner
- Save result as variable: `Barcode`

**Action 2: Get contents of URL**
- URL: `https://YOUR-HA-URL/api/webhook/grocery_add`
- Method: **POST**
- Headers:
  - `Content-Type` = `application/json`
- Request body: **JSON**
  - `barcode` = `Shortcut Input` → select variable `Barcode`

The JSON body should look like:
```json
{
  "barcode": "[Barcode variable]"
}
```

4. Name the shortcut: **"Add item"** (must match `ios_shortcut_add` in card config)
5. Choose an icon: 🛒 or 📷

## Step 3 — Create "Remove item" shortcut

Repeat Step 2 but:
- Change the URL to `.../api/webhook/grocery_remove`
- Name it: **"Remove item"**
- Icon: 🗑️

## Step 4 — Add to Home Screen

1. Long-press the shortcut
2. Tap **Add to Home Screen**
3. Place it somewhere easily accessible

## Usage

1. Tap the shortcut icon on your home screen
2. Camera opens automatically
3. Point at barcode → scanned instantly
4. HA receives the barcode and looks up the product
5. You get a notification confirming the action

## Troubleshooting

**Shortcut says "Could not connect"**
- Check your HA URL is correct and reachable
- Try opening the URL in Safari first

**Card shows iOS Shortcuts buttons but nothing happens**
- Make sure the shortcut name in the card config exactly matches your shortcut name
- The URL scheme `shortcuts://run-shortcut?name=...` opens the Shortcuts app

**Notification not received in HA**
- Check HA logs for `grocery_webhook_add` automation
- Verify the webhook ID matches: `grocery_add` / `grocery_remove`
