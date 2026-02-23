# iOS Genvägar — Installationsguide

## Varför Genvägar?

iPhones inbyggda streckkodsscanner (via Genvägar) är snabbare och mer pålitlig än webbläsarbaserad skanning. Den fungerar även när HA Companion App har begränsad kameraåtkomst.

## Krav

- iPhone med iOS 13+
- Home Assistant nåbart från telefonen (lokal eller extern URL)
- Grocery Tracker installerat och igång

## Steg 1 — Hitta din webhook-URL

Dina webhook-URL:er är:
```
https://DIN-HA-URL/api/webhook/grocery_add
https://DIN-HA-URL/api/webhook/grocery_remove
```

Hitta din HA-URL i: **HA-appen → Inställningar → Companion App → Serveradress**

## Steg 2 — Skapa genvägen "Lägg till vara"

1. Öppna **Genvägar**-appen
2. Tryck **+** för att skapa ny genväg
3. Lägg till dessa åtgärder i ordning:

**Åtgärd 1: Skanna streckkod**
- Sök efter: `Skanna QR-kod`
- Öppnar native kamerascanner
- Spara resultat som variabel: `Streckkod`

**Åtgärd 2: Hämta URL-innehåll**
- URL: `https://DIN-HA-URL/api/webhook/grocery_add`
- Metod: **POST**
- Rubriker:
  - `Content-Type` = `application/json`
- Begärandetext: **JSON**
  - `barcode` = välj variabeln `Streckkod`

JSON-kroppen ser ut så här:
```json
{
  "barcode": "[variabel: Streckkod]"
}
```

4. Namnge genvägen: **"Lägg till vara"** (måste matcha `ios_shortcut_add` i kortkonfigurationen)
5. Välj ikon: 🛒 eller 📷

## Steg 3 — Skapa genvägen "Ta bort vara"

Upprepa Steg 2 men:
- Ändra URL till `.../api/webhook/grocery_remove`
- Namnge den: **"Ta bort vara"**
- Ikon: 🗑️

## Steg 4 — Lägg till på hemskärmen

1. Håll på genvägen
2. Tryck **Lägg till på hemskärm**
3. Placera den lättillgängligt

## Användning

1. Tryck på genvägsikonen på hemskärmen
2. Kameran öppnas automatiskt
3. Rikta mot streckkoden → skannas direkt
4. HA tar emot streckkoden och slår upp produkten
5. Du får en bekräftelsenotis

## Felsökning

**"Kunde inte ansluta"**
- Kontrollera att HA-URL:en är korrekt och nåbar
- Prova att öppna URL:en i Safari först

**Inget händer i HA**
- Kontrollera HA-loggen efter `grocery_webhook_add`
- Verifiera att webhook-ID:t stämmer: `grocery_add` / `grocery_remove`
