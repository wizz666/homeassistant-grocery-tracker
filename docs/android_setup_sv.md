# Android-setup

Den här guiden beskriver streckkodsscanning på Android-telefoner. Det finns två metoder — prova Metod 1 först, den kan fungera direkt utan extra inställningar.

---

## Metod 1 — Lovelace-kortet (kamera i webbläsaren)

Till skillnad från iPhone tillåter Android kameraåtkomst i HA Companion App och Chrome. Grocery Scanner-kortet använder Androids inbyggda `BarcodeDetector`-API (med jsQR som reserv), vilket innebär att det kan fungera direkt utan extra inställningar.

### Steg

1. Öppna **Home Assistant** i HA Companion App eller Chrome på din Android-telefon
2. Gå till dashboarden med Grocery Scanner-kortet
3. Tryck på **kamera-fliken** (📷)
4. Tryck **Tillåt** när appen ber om kameraåtkomst
5. Rikta mot en streckkod — den skannas automatiskt

Om kortet skannar och du får en bekräftelsenotis i HA är du klar. Ingen ytterligare konfiguration behövs.

---

## Metod 2 — HTTP Shortcuts-appen (hemskärmsknapp)

Om kamerakortet inte fungerar, eller om du föredrar en dedikerad hemskärmsknapp (liknande iOS Genvägar), använd den gratis appen **HTTP Shortcuts**.

**HTTP Shortcuts** av Roland Lötscher — [Google Play](https://play.google.com/store/apps/details?id=ch.rmy.android.http_shortcuts)

Med appen skapar du hemskärmsknappar som öppnar kameran, skannar en streckkod och skickar automatiskt resultatet till din HA-webhook — ingen teknisk kunskap krävs.

### Förutsättningar

- Android-telefon med Google Play
- Home Assistant nåbart från telefonen (lokalt eller externt)
- Grocery Tracker installerat och igång

### Steg 1 — Hitta dina webhook-URL:er

```
https://DIN-HA-URL/api/webhook/grocery_add
https://DIN-HA-URL/api/webhook/grocery_remove
```

Hitta din HA-URL under: **HA-appen → Inställningar → Companion App → Serveradress**

För extern åtkomst, använd din externa URL (Nabu Casa, reverse proxy, etc.).

### Steg 2 — Installera HTTP Shortcuts

Installera **HTTP Shortcuts** från Google Play (gratis, inga annonser).

### Steg 3 — Skapa genvägen "Lägg till vara"

1. Öppna HTTP Shortcuts
2. Tryck **+** → **Regular Shortcut**
3. Fyll i:
   - **Namn:** `Lägg till vara`
   - **Metod:** `POST`
   - **URL:** `https://DIN-HA-URL/api/webhook/grocery_add`
4. Gå till fliken **Request Body**:
   - Typ: **Custom text / JSON**
   - Content type: `application/json`
   - Body:
     ```json
     {"barcode": "{{barcode}}"}
     ```
5. Gå till fliken **Variables**:
   - Tryck **+** → **Barcode Scanner**
   - Namn: `barcode`
6. Tryck **Spara**

### Steg 4 — Skapa genvägen "Ta bort vara"

Upprepa Steg 3 men:
- **Namn:** `Ta bort vara`
- **URL:** `https://DIN-HA-URL/api/webhook/grocery_remove`
- Body och variabel är identiska

### Steg 5 — Lägg till på hemskärmen

1. Håll fingret på genvägen i HTTP Shortcuts
2. Tryck **Place on Home Screen**
3. Upprepa för ta bort-genvägen

### Användning

1. Tryck på **Lägg till vara** på hemskärmen
2. Kameran öppnas automatiskt
3. Rikta mot streckkoden → skannas
4. HA tar emot streckkoden och slår upp produkten i Open Food Facts
5. En notis bekräftar att varan lagts till

---

## Jämförelse

| Metod | Installation | Hemskärmsknapp |
|-------|-------------|----------------|
| Lovelace-kort | Ingen | Nej (kräver HA-appen) |
| HTTP Shortcuts | ~5 min | Ja |

---

## Felsökning

**Kameran i kortet öppnas inte**
- Kontrollera att du använder Chrome eller HA Companion App (inte Firefox)
- Kontrollera att kameraåtkomst är beviljad för appen i Android-inställningarna

**HTTP Shortcuts: "Connection refused" eller inget svar**
- Verifiera att din HA-URL är nåbar från telefonen
- Prova att öppna URL:en i Chrome först
- Använder du HTTP (inte HTTPS), aktivera "Allow cleartext traffic" i HTTP Shortcuts-inställningarna

**Vara läggs inte till / sensorn stannar på 0**
- Kolla HA-loggar: **Inställningar → System → Loggar** → sök `grocery`
- Kontrollera att webhook-automationen är aktiv: **Inställningar → Automationer** → sök `grocery`
