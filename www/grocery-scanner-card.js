/**
 * Grocery Scanner Card – Home Assistant Custom Lovelace Card
 * Kameraskanning (BarcodeDetector + jsQR fallback) + manuell inmatning
 *
 * Plattformsstöd:
 *   Android (HA Companion / Chrome): BarcodeDetector native → jsQR fallback
 *   iPhone (HA Companion / Safari):  jsQR via getUserMedia (iOS 14.5+)
 *                                    → iOS Genvägar-knapp om kamera nekas
 *   Desktop:                         jsQR via getUserMedia → manuell inmatning
 *
 * Kortinställningar (card config):
 *   type: custom:grocery-scanner-card
 *   title: Matscanner                        # valfritt
 *   ios_shortcut_add: "Lägg till vara"       # namn på din iOS Genväg (add)
 *   ios_shortcut_remove: "Ta bort vara"      # namn på din iOS Genväg (remove)
 *
 * Resurser: /local/grocery-scanner-card.js  (typ: JavaScript-modul)
 */

const OFF_API = "https://world.openfoodfacts.org/api/v2/product/{barcode}.json";
const OFF_HEADERS = { "User-Agent": "HomeAssistant-GroceryTracker/1.0" };

// Plattformsdetektering
const IS_IOS = /iPad|iPhone|iPod/.test(navigator.userAgent) && !window.MSStream;
const HAS_BARCODE_DETECTOR = "BarcodeDetector" in window;

// jsQR laddas lazily (fallback om BarcodeDetector saknas)
let _jsQR = null;
async function loadJsQR() {
  if (_jsQR) return _jsQR;
  return new Promise((resolve, reject) => {
    const s = document.createElement("script");
    s.src = "https://cdn.jsdelivr.net/npm/jsqr@1.4.0/dist/jsQR.min.js";
    s.onload = () => { _jsQR = window.jsQR; resolve(_jsQR); };
    s.onerror = reject;
    document.head.appendChild(s);
  });
}

// Kontrollera om kamera är tillgänglig utan att faktiskt be om tillstånd
async function cameraAvailable() {
  if (!navigator.mediaDevices?.getUserMedia) return false;
  try {
    const devices = await navigator.mediaDevices.enumerateDevices();
    return devices.some(d => d.kind === "videoinput");
  } catch {
    return false;
  }
}

const STYLES = `
  :host { display: block; }
  ha-card { padding: 16px; font-family: var(--primary-font-family, sans-serif); }

  .btn {
    display: inline-flex; align-items: center; gap: 8px;
    padding: 10px 18px; border-radius: 8px; border: none;
    cursor: pointer; font-size: 0.95em; font-weight: 500;
    transition: opacity .15s;
  }
  .btn:active { opacity: .7; }
  .btn-primary { background: var(--primary-color); color: white; }
  .btn-danger  { background: #e53935; color: white; }
  .btn-outline { background: transparent; border: 1px solid var(--divider-color); color: var(--primary-text-color); }
  .btn-ios     { background: #000; color: #fff; }
  .btn-full    { width: 100%; justify-content: center; margin-bottom: 8px; }
  .row { display: flex; gap: 8px; margin-bottom: 8px; }
  .row .btn { flex: 1; justify-content: center; }

  /* Kamera */
  .camera-wrap { position: relative; width: 100%; border-radius: 8px; overflow: hidden; background: #000; }
  video { width: 100%; display: block; max-height: 280px; object-fit: cover; }
  canvas { display: none; }
  .scan-overlay {
    position: absolute; inset: 0; display: flex; align-items: center; justify-content: center;
  }
  .scan-box {
    width: 60%; aspect-ratio: 1; border: 2px solid rgba(var(--rgb-primary-color,33,150,243),.8);
    border-radius: 8px; box-shadow: 0 0 0 4000px rgba(0,0,0,.35);
  }
  .scan-hint { text-align: center; color: #aaa; font-size: .85em; margin: 8px 0 12px; }

  /* Produktkort */
  .product-card {
    display: flex; gap: 12px; padding: 12px; border-radius: 8px;
    background: var(--secondary-background-color); margin-bottom: 16px;
  }
  .product-img { width: 64px; height: 64px; border-radius: 6px; object-fit: contain; background: #fff; }
  .product-img-placeholder {
    width: 64px; height: 64px; border-radius: 6px;
    background: #e0e0e0; display: flex; align-items: center; justify-content: center; font-size: 1.8em;
  }
  .product-info { flex: 1; }
  .product-name { font-weight: 600; margin-bottom: 4px; color: var(--primary-text-color); }
  .product-meta { font-size: .8em; color: var(--secondary-text-color); }

  /* Formulär */
  .form-group { margin-bottom: 12px; }
  label { display: block; font-size: .85em; color: var(--secondary-text-color); margin-bottom: 4px; }
  input, select {
    width: 100%; padding: 8px 10px; border-radius: 6px;
    border: 1px solid var(--divider-color); background: var(--card-background-color);
    color: var(--primary-text-color); font-size: .95em; box-sizing: border-box;
  }
  input:focus, select:focus { outline: 2px solid var(--primary-color); border-color: transparent; }
  .qty-row { display: flex; gap: 8px; }
  .qty-row input { flex: 2; }
  .qty-row select { flex: 1; }

  /* Plattforms-info */
  .platform-info {
    background: var(--secondary-background-color); border-radius: 8px;
    padding: 12px; margin-bottom: 12px; font-size: .85em; color: var(--secondary-text-color);
  }
  .platform-info strong { display: block; color: var(--primary-text-color); margin-bottom: 4px; }
  .divider { display: flex; align-items: center; gap: 8px; margin: 12px 0; color: var(--secondary-text-color); font-size: .8em; }
  .divider::before, .divider::after { content: ""; flex: 1; border-top: 1px solid var(--divider-color); }

  /* Lagerlistvy */
  .inventory-item {
    display: flex; align-items: center; gap: 10px; padding: 8px 0;
    border-bottom: 1px solid var(--divider-color);
  }
  .inventory-item:last-child { border-bottom: none; }
  .item-emoji { font-size: 1.4em; width: 28px; text-align: center; flex-shrink: 0; }
  .item-details { flex: 1; min-width: 0; }
  .item-name { font-weight: 500; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .item-meta { font-size: .78em; color: var(--secondary-text-color); }
  .item-expiry-warn { color: #e65100; }
  .item-expiry-expired { color: #e53935; }
  .item-actions { display: flex; gap: 4px; flex-shrink: 0; }
  .icon-btn { background: none; border: none; cursor: pointer; font-size: 1.2em; padding: 4px; border-radius: 4px; }
  .icon-btn:hover { background: var(--secondary-background-color); }

  /* Tabs */
  .tabs { display: flex; gap: 4px; margin-bottom: 16px; border-bottom: 2px solid var(--divider-color); }
  .tab {
    padding: 8px 14px; border: none; background: none; cursor: pointer;
    font-size: .9em; color: var(--secondary-text-color);
    border-bottom: 2px solid transparent; margin-bottom: -2px;
  }
  .tab.active { color: var(--primary-color); border-bottom-color: var(--primary-color); font-weight: 600; }

  .empty { text-align: center; color: var(--secondary-text-color); padding: 24px 0; }
  .badge {
    display: inline-block; background: #e53935; color: #fff;
    border-radius: 10px; padding: 1px 7px; font-size: .75em;
    margin-left: 4px; vertical-align: middle;
  }
  .spinner { text-align: center; padding: 20px; color: var(--secondary-text-color); }

  /* Bäst-före inline-edit */
  .expiry-edit-row {
    display: flex; align-items: center; gap: 6px;
    padding: 8px 0 8px 38px;
    border-bottom: 1px solid var(--divider-color);
  }
  .expiry-date-input {
    flex: 1; padding: 8px 10px; border-radius: 6px;
    border: 2px solid var(--primary-color);
    background: var(--card-background-color);
    color: var(--primary-text-color); font-size: 1em;
  }

  /* Platsfilter */
  .loc-filter { display: flex; gap: 6px; margin-bottom: 12px; flex-wrap: wrap; }
  .loc-btn {
    padding: 4px 12px; border-radius: 16px; border: 1px solid var(--divider-color);
    background: transparent; cursor: pointer; font-size: .82em;
    color: var(--secondary-text-color); white-space: nowrap;
  }
  .loc-btn.active { background: var(--primary-color); color: white; border-color: transparent; }

  /* Lågstock */
  .item-low-stock { color: #e65100; }
  .loc-tag { font-size: .72em; color: var(--secondary-text-color); margin-left: 4px; opacity: .8; }
`;

class GroceryScannerCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._hass = null;
    this._stream = null;
    this._animFrame = null;
    this._tab = "scan";
    this._scanState = "idle";  // idle | checking | scanning | confirm | ios_fallback
    this._scannedBarcode = null;
    this._product = null;
    this._config = {};
    this._initialized = false;
    this._cameraWorks = null;  // null=okänt, true/false efter test
    this._locationFilter = "all";
    this._editingExpiryId = null;
  }

  static getConfigElement() { return document.createElement("div"); }
  static getStubConfig() {
    return {
      title: "Matscanner",
      ios_shortcut_add: "Lägg till vara",
      ios_shortcut_remove: "Ta bort vara",
    };
  }

  setConfig(config) {
    this._config = config || {};
    if (!this._initialized) {
      this._initialized = true;
      this._build();
    }
  }

  set hass(hass) {
    this._hass = hass;
    if (this._tab === "inventory") this._renderInventory();
  }

  // ── Bygg shadow DOM ────────────────────────────────────────────────────────
  _build() {
    const style = document.createElement("style");
    style.textContent = STYLES;
    this.shadowRoot.appendChild(style);
    const card = document.createElement("ha-card");
    this.shadowRoot.appendChild(card);
    this._card = card;
    this._drawMain();
  }

  _drawMain() {
    const badge = this._getExpiringSoonCount() + this._getExpiredCount() + this._getLowStockCount();
    const invBadge = badge > 0 ? `<span class="badge">${badge}</span>` : "";

    this._card.innerHTML = `
      <div class="tabs">
        <button class="tab ${this._tab === "scan"      ? "active" : ""}" data-tab="scan">📷 Skanna</button>
        <button class="tab ${this._tab === "manual"    ? "active" : ""}" data-tab="manual">✏️ Manuellt</button>
        <button class="tab ${this._tab === "inventory" ? "active" : ""}" data-tab="inventory">📦 Lager${invBadge}</button>
      </div>
      <div id="tab-content"></div>
    `;
    this._card.querySelectorAll(".tab").forEach(btn => {
      btn.addEventListener("click", () => {
        this._stopCamera();
        this._tab = btn.dataset.tab;
        this._scanState = "idle";
        this._drawMain();
      });
    });

    const content = this._card.querySelector("#tab-content");
    if (this._tab === "scan")           this._renderScanTab(content);
    else if (this._tab === "manual")    this._renderManualTab(content);
    else if (this._tab === "inventory") this._renderInventoryTab(content);
  }

  // ── SCAN-fliken ────────────────────────────────────────────────────────────
  _renderScanTab(container) {
    if (this._scanState === "idle") {
      // iPhone: visa guide istället för knappar som inte fungerar i WKWebView
      if (IS_IOS) {
        container.innerHTML = `
          <div class="platform-info">
            <strong>📱 iPhone – Så här scannar du</strong>
            HA-appen på iPhone kan inte öppna kameran eller Genvägar-appen direkt.
            Scanning görs via en iOS Genväg på hemskärmen.
          </div>

          <div style="background:var(--secondary-background-color);border-radius:8px;padding:14px;margin-bottom:12px">
            <div style="font-weight:600;margin-bottom:10px">Steg 1 – Skapa genvägar (en gång)</div>
            <div style="font-size:.85em;line-height:1.7;color:var(--primary-text-color)">
              1. Öppna <strong>Genvägar</strong>-appen → <strong>+</strong><br>
              2. Lägg till: <strong>Skanna QR-kod</strong><br>
              3. Lägg till: <strong>Hämta URL-innehåll</strong><br>
              &nbsp;&nbsp;&nbsp;• URL: <code style="font-size:.8em;background:#0002;padding:1px 4px;border-radius:3px">DIN-HA-URL/api/webhook/grocery_add</code><br>
              &nbsp;&nbsp;&nbsp;• Metod: <strong>POST</strong><br>
              &nbsp;&nbsp;&nbsp;• Rubrik: <code style="font-size:.8em;background:#0002;padding:1px 4px;border-radius:3px">Content-Type: application/json</code><br>
              &nbsp;&nbsp;&nbsp;• JSON-nyckel: <strong>barcode</strong> → värde: variabeln <strong>QR-kod</strong><br>
              4. Namnge: <strong>Lägg till vara</strong><br>
              5. Lägg till på hemskärmen<br>
              6. Upprepa med <code style="font-size:.8em;background:#0002;padding:1px 4px;border-radius:3px">/grocery_remove</code> → <strong>Ta bort vara</strong>
            </div>
          </div>

          <div style="background:var(--secondary-background-color);border-radius:8px;padding:14px;margin-bottom:12px">
            <div style="font-weight:600;margin-bottom:6px">Steg 2 – Scanna</div>
            <div style="font-size:.85em;line-height:1.7;color:var(--primary-text-color)">
              Tryck på genvägsikonen på <strong>hemskärmen</strong> (utanför HA-appen).<br>
              Kameran öppnas → scanna → klart. HA uppdateras automatiskt.
            </div>
          </div>

          <div class="divider">eller lägg till manuellt</div>
          <button class="btn btn-primary btn-full" id="manual-btn">✏️ Manuell inmatning</button>
        `;
        container.querySelector("#manual-btn").addEventListener("click", () => {
          this._tab = "manual"; this._drawMain();
        });
        return;
      }

      // Android / Desktop: visa kameraknapp
      container.innerHTML = `
        <div style="text-align:center; padding: 8px 0 16px;">
          <div style="font-size:4em; margin-bottom:12px;">🔍</div>
          <p style="color:var(--secondary-text-color); margin: 0 0 20px;">
            Håll streckkoden framför kameran.
          </p>
        </div>
        <button class="btn btn-primary btn-full" id="start-btn">📷 Starta kamera</button>
      `;
      container.querySelector("#start-btn").addEventListener("click", () => this._initCamera(container));

    } else if (this._scanState === "checking") {
      container.innerHTML = `<div class="spinner">⏳ Kontrollerar kamera…</div>`;

    } else if (this._scanState === "scanning") {
      container.innerHTML = `
        <div class="camera-wrap">
          <video id="cam-video" autoplay playsinline muted></video>
          <canvas id="cam-canvas"></canvas>
          <div class="scan-overlay"><div class="scan-box"></div></div>
        </div>
        <p class="scan-hint">Rikta kameran mot streckkoden</p>
        <button class="btn btn-outline btn-full" id="stop-btn">✕ Avbryt</button>
      `;
      container.querySelector("#stop-btn").addEventListener("click", () => {
        this._stopCamera(); this._scanState = "idle"; this._drawMain();
      });
      this._attachCamera(container);

    } else if (this._scanState === "confirm") {
      this._renderConfirm(container);

    } else if (this._scanState === "ios_fallback") {
      this._renderIOSFallback(container);
    }
  }

  async _initCamera(container) {
    this._scanState = "checking";
    this._renderScanTab(container);

    // Testa kameratillgång
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: "environment" }
      });
      stream.getTracks().forEach(t => t.stop());
      this._cameraWorks = true;
      this._scanState = "scanning";
    } catch (err) {
      this._cameraWorks = false;
      if (IS_IOS) {
        this._scanState = "ios_fallback";
      } else {
        container.innerHTML = `
          <div style="text-align:center; padding:20px;">
            <p>⚠️ Kameraåtkomst nekad</p>
            <p style="font-size:.85em;color:var(--secondary-text-color)">${err.message}</p>
            <button class="btn btn-outline" id="back-btn">← Tillbaka</button>
          </div>`;
        container.querySelector("#back-btn").addEventListener("click", () => {
          this._scanState = "idle"; this._drawMain();
        });
        return;
      }
    }
    this._renderScanTab(container);
  }

  async _attachCamera(container) {
    const video = container.querySelector("#cam-video");
    const canvas = container.querySelector("#cam-canvas");
    try {
      this._stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: "environment", width: { ideal: 1280 } }
      });
      video.srcObject = this._stream;
      await video.play();
    } catch (err) {
      container.innerHTML = `
        <p style="color:var(--error-color,red)">Kamerafel: ${err.message}</p>
        <button class="btn btn-outline btn-full" id="back-btn">← Tillbaka</button>`;
      container.querySelector("#back-btn").addEventListener("click", () => {
        this._scanState = "idle"; this._drawMain();
      });
      return;
    }

    if (HAS_BARCODE_DETECTOR) {
      // Native (Android Chrome, snabbt)
      const detector = new BarcodeDetector({
        formats: ["ean_8", "ean_13", "upc_a", "upc_e", "code_128", "code_39"]
      });
      this._scanLoopNative(detector, video);
    } else {
      // jsQR fallback (alla plattformar inkl iOS)
      try {
        const qr = await loadJsQR();
        this._scanLoopJsQR(qr, video, canvas);
      } catch {
        container.innerHTML = `
          <p>Kunde inte ladda skannerbibliotek. Kontrollera internetanslutning.</p>
          <button class="btn btn-outline btn-full" id="back-btn">← Tillbaka</button>`;
        container.querySelector("#back-btn").addEventListener("click", () => {
          this._scanState = "idle"; this._drawMain();
        });
      }
    }
  }

  _scanLoopNative(detector, video) {
    const tick = async () => {
      if (!this._stream) return;
      try {
        const codes = await detector.detect(video);
        if (codes.length > 0) { this._onBarcode(codes[0].rawValue); return; }
      } catch {}
      this._animFrame = requestAnimationFrame(tick);
    };
    this._animFrame = requestAnimationFrame(tick);
  }

  _scanLoopJsQR(jsQRFn, video, canvas) {
    const ctx = canvas.getContext("2d");
    const tick = () => {
      if (!this._stream) return;
      if (video.readyState === video.HAVE_ENOUGH_DATA) {
        canvas.width = video.videoWidth;
        canvas.height = video.videoHeight;
        ctx.drawImage(video, 0, 0);
        const img = ctx.getImageData(0, 0, canvas.width, canvas.height);
        const code = jsQRFn(img.data, canvas.width, canvas.height);
        if (code) { this._onBarcode(code.data); return; }
      }
      this._animFrame = requestAnimationFrame(tick);
    };
    this._animFrame = requestAnimationFrame(tick);
  }

  async _onBarcode(barcode) {
    this._stopCamera();
    this._scannedBarcode = barcode;
    this._product = null;
    this._scanState = "confirm";

    // Produktlookup mot Open Food Facts
    try {
      const resp = await fetch(OFF_API.replace("{barcode}", barcode), { headers: OFF_HEADERS });
      if (resp.ok) {
        const data = await resp.json();
        if (data.status === 1) {
          const p = data.product;
          this._product = {
            name: p.product_name_sv || p.product_name || p.product_name_en || "",
            brands: p.brands || "",
            category: (p.categories_tags || []).slice(-1)[0]?.replace(/^en:/, "").replace(/-/g, " ") || "",
            image_url: p.image_small_url || "",
          };
        }
      }
    } catch {}

    const content = this._card.querySelector("#tab-content");
    if (content) this._renderConfirm(content);
  }

  _renderConfirm(container) {
    const p = this._product;
    const name = p?.name || "";
    const imgHtml = p?.image_url
      ? `<img class="product-img" src="${p.image_url}" alt="">`
      : `<div class="product-img-placeholder">🛒</div>`;

    container.innerHTML = `
      <div class="product-card">
        ${imgHtml}
        <div class="product-info">
          <div class="product-name">${name || `Streckkod: ${this._scannedBarcode}`}</div>
          <div class="product-meta">${[p?.brands, p?.category].filter(Boolean).join(" · ")}</div>
          <div class="product-meta" style="font-family:monospace;font-size:.75em">${this._scannedBarcode}</div>
        </div>
      </div>

      ${!name ? `<div class="form-group">
        <label>Produktnamn (ej funnet i Open Food Facts)</label>
        <input type="text" id="prod-name" placeholder="t.ex. Arla Mellanmjölk">
      </div>` : ""}

      <div class="form-group">
        <label>Antal &amp; enhet</label>
        <div class="qty-row">
          <input type="number" id="qty" value="1" min="1" max="99">
          <select id="unit">
            <option>st</option><option>förpackning</option>
            <option>g</option><option>kg</option><option>dl</option><option>l</option>
          </select>
        </div>
      </div>
      <div class="form-group">
        <label>Bäst före (valfritt)</label>
        <input type="date" id="expiry">
      </div>
      <div class="form-group">
        <label>Plats</label>
        <select id="location">
          <option value="kyl">🧊 Kyl</option>
          <option value="frys">❄️ Frys</option>
          <option value="skafferi">🏠 Skafferi</option>
        </select>
      </div>
      <div class="row" style="margin-top:16px">
        <button class="btn btn-primary" id="add-btn">✅ Lägg till</button>
        <button class="btn btn-danger"  id="remove-btn">🗑️ Ta bort</button>
      </div>
      <button class="btn btn-outline btn-full" style="margin-top:4px" id="rescan-btn">← Skanna igen</button>
    `;

    container.querySelector("#add-btn").addEventListener("click", async () => {
      const finalName = container.querySelector("#prod-name")?.value || name || `Vara ${this._scannedBarcode}`;
      await this._callService("grocery_scan_add", {
        barcode: this._scannedBarcode,
        quantity: parseInt(container.querySelector("#qty").value) || 1,
        expiry_date: container.querySelector("#expiry").value || null,
        source: "mobile",
        name_override: finalName,
        location: container.querySelector("#location").value,
      });
      this._scanState = "idle"; this._drawMain();
    });

    container.querySelector("#remove-btn").addEventListener("click", async () => {
      await this._callService("grocery_scan_remove", {
        barcode: this._scannedBarcode, source: "mobile"
      });
      this._scanState = "idle"; this._drawMain();
    });

    container.querySelector("#rescan-btn").addEventListener("click", () => {
      this._scanState = "idle"; this._drawMain();
    });
  }

  // ── iOS Genvägar-fallback ─────────────────────────────────────────────────
  _renderIOSFallback(container) {
    // Samma som idle-läget för iOS — visa guiden
    this._scanState = "idle";
    this._renderScanTab(container);
  }

  // ── MANUELL-fliken ────────────────────────────────────────────────────────
  _renderManualTab(container) {
    container.innerHTML = `
      <div class="form-group">
        <label>Produktnamn *</label>
        <input type="text" id="m-name" placeholder="t.ex. Ägg, Havregryn, Smör">
      </div>
      <div class="form-group">
        <label>Antal &amp; enhet</label>
        <div class="qty-row">
          <input type="number" id="m-qty" value="1" min="1" max="999">
          <select id="m-unit">
            <option>st</option><option>förpackning</option>
            <option>g</option><option>kg</option><option>dl</option><option>l</option>
            <option>påse</option><option>burk</option>
          </select>
        </div>
      </div>
      <div class="form-group">
        <label>Kategori (valfritt)</label>
        <select id="m-cat">
          <option value="">– välj –</option>
          <option>mejeri</option><option>kött &amp; fisk</option><option>grönsaker</option>
          <option>frukt</option><option>bröd &amp; spannmål</option><option>konserver</option>
          <option>frys</option><option>dryck</option><option>kryddor &amp; såser</option><option>övrigt</option>
        </select>
      </div>
      <div class="form-group">
        <label>Bäst före (valfritt)</label>
        <input type="date" id="m-expiry">
      </div>
      <div class="form-group">
        <label>Plats</label>
        <select id="m-location">
          <option value="kyl">🧊 Kyl</option>
          <option value="frys">❄️ Frys</option>
          <option value="skafferi">🏠 Skafferi</option>
        </select>
      </div>
      <div class="form-group">
        <label>Lågstocksvarning vid (st, 0 = av)</label>
        <input type="number" id="m-minqty" value="0" min="0" max="99">
      </div>
      <div class="form-group">
        <label>Streckkod (valfritt)</label>
        <input type="text" id="m-barcode" placeholder="7310500143006" inputmode="numeric">
      </div>
      <button class="btn btn-primary btn-full" id="m-add-btn">✅ Lägg till i lager</button>
    `;

    container.querySelector("#m-add-btn").addEventListener("click", async () => {
      const name = container.querySelector("#m-name").value.trim();
      if (!name) { alert("Ange ett produktnamn!"); return; }
      await this._callService("grocery_manual_add", {
        name,
        quantity: parseInt(container.querySelector("#m-qty").value) || 1,
        unit: container.querySelector("#m-unit").value,
        category: container.querySelector("#m-cat").value,
        expiry_date: container.querySelector("#m-expiry").value || null,
        barcode: container.querySelector("#m-barcode").value.trim(),
        location: container.querySelector("#m-location").value,
        min_quantity: parseInt(container.querySelector("#m-minqty").value) || 0,
      });
      container.querySelector("#m-name").value = "";
      container.querySelector("#m-qty").value = "1";
      container.querySelector("#m-expiry").value = "";
      container.querySelector("#m-barcode").value = "";
      container.querySelector("#m-minqty").value = "0";
    });
  }

  // ── LAGER-fliken ──────────────────────────────────────────────────────────
  _renderInventoryTab(container) { this._renderInventory(container); }

  _renderInventory(container) {
    const c = container || this._card.querySelector("#tab-content");
    if (!c || this._tab !== "inventory") return;
    const allItems = this._getItems();
    const today = new Date(); today.setHours(0, 0, 0, 0);
    const soon  = new Date(today); soon.setDate(soon.getDate() + 2);

    if (!allItems.length) {
      c.innerHTML = `
        <div class="loc-filter">
          ${["all","kyl","frys","skafferi"].map(l => `<button class="loc-btn${this._locationFilter===l?" active":""}" data-loc="${l}">${this._locationLabel(l)}</button>`).join("")}
        </div>
        <div class="empty">📭 Lagret är tomt<br><small>Skanna eller lägg till manuellt</small></div>`;
      c.querySelectorAll(".loc-btn").forEach(btn => btn.addEventListener("click", () => {
        this._locationFilter = btn.dataset.loc; this._renderInventory();
      }));
      return;
    }

    // Filtrera på plats
    const items = this._locationFilter === "all"
      ? allItems
      : allItems.filter(i => (i.location || "kyl") === this._locationFilter);

    // Sortera: utgångna → snart utgångna → lågt lager → normalt
    const sorted = [...items].sort((a, b) => {
      const rank = item => {
        const exp = item.expiry_date ? new Date(item.expiry_date) : null;
        if (exp) exp.setHours(0,0,0,0);
        if (exp && exp < today) return 0;
        if (exp && exp <= soon) return 1;
        const minQ = item.min_quantity || 0;
        if (minQ > 0 && item.quantity <= minQ) return 2;
        return 3;
      };
      const ra = rank(a), rb = rank(b);
      if (ra !== rb) return ra - rb;
      const ea = a.expiry_date ? new Date(a.expiry_date) : null;
      const eb = b.expiry_date ? new Date(b.expiry_date) : null;
      if (ea && eb) return ea - eb;
      if (ea) return -1; if (eb) return 1;
      return (a.name || "").localeCompare(b.name || "", "sv");
    });

    // Räkna per plats för filterknappar
    const counts = { all: allItems.length };
    for (const loc of ["kyl","frys","skafferi"]) {
      counts[loc] = allItems.filter(i => (i.location || "kyl") === loc).length;
    }

    c.innerHTML = `
      <div class="loc-filter">
        ${["all","kyl","frys","skafferi"].map(l => `
          <button class="loc-btn${this._locationFilter===l?" active":""}" data-loc="${l}">
            ${this._locationLabel(l)}${counts[l] > 0 ? ` <small>(${counts[l]})</small>` : ""}
          </button>`).join("")}
      </div>
      <div style="font-size:.85em;color:var(--secondary-text-color);margin-bottom:8px">
        ${items.length} varor${this._locationFilter !== "all" ? " i " + this._locationLabel(this._locationFilter) : " i lager"}
      </div>
      ${sorted.length === 0
        ? `<div class="empty">Inga varor här ännu</div>`
        : sorted.map(item => {
          const exp = item.expiry_date ? new Date(item.expiry_date) : null;
          if (exp) exp.setHours(0, 0, 0, 0);
          let cls = "", expTxt = "";
          if (exp) {
            if (exp < today)      { cls = "item-expiry-expired"; expTxt = `🔴 Utgången ${item.expiry_date}`; }
            else if (exp <= soon) { cls = "item-expiry-warn";    expTxt = `🟡 Bäst före ${item.expiry_date}`; }
            else                  {                              expTxt = `Bäst före ${item.expiry_date}`; }
          }
          const minQ = item.min_quantity || 0;
          const isLow = minQ > 0 && item.quantity <= minQ;
          const emoji = this._categoryEmoji(item.category);
          const locEmoji = this._locationEmoji(item.location);
          const isEditing = this._editingExpiryId === item.id;
          return `
            <div class="inventory-item">
              <span class="item-emoji">${emoji}</span>
              <div class="item-details expiry-btn" data-id="${item.id}" style="cursor:pointer">
                <div class="item-name">${item.name}
                  <span style="color:var(--secondary-text-color);font-weight:normal">
                    ×${item.quantity} ${item.unit}
                  </span>
                  ${locEmoji ? `<span class="loc-tag">${locEmoji}</span>` : ""}
                </div>
                ${expTxt
                  ? `<div class="item-meta ${cls}">${expTxt} ✏️</div>`
                  : `<div class="item-meta" style="color:var(--primary-color);font-size:.78em">📅 Lägg till bäst före-datum</div>`}
                ${isLow ? `<div class="item-meta item-low-stock">🟠 Lågt lager (min ${minQ} ${item.unit})</div>` : ""}
              </div>
              <div class="item-actions">
                <button class="icon-btn remove-btn" data-id="${item.id}" title="Ta bort">🗑️</button>
              </div>
            </div>
            ${isEditing ? `
            <div class="expiry-edit-row">
              <input type="date" class="expiry-date-input" data-id="${item.id}"
                value="${item.expiry_date || ''}">
              <button class="icon-btn save-expiry-btn" data-id="${item.id}" title="Spara">✅</button>
              <button class="icon-btn cancel-expiry-btn" title="Avbryt">✕</button>
            </div>` : ""}`;
        }).join("")}
    `;

    c.querySelectorAll(".loc-btn").forEach(btn => {
      btn.addEventListener("click", () => {
        this._locationFilter = btn.dataset.loc; this._renderInventory();
      });
    });
    c.querySelectorAll(".expiry-btn").forEach(btn => {
      btn.addEventListener("click", () => {
        this._editingExpiryId = btn.dataset.id;
        this._renderInventory();
      });
    });

    c.querySelectorAll(".save-expiry-btn").forEach(btn => {
      btn.addEventListener("click", async () => {
        const input = btn.parentElement.querySelector(".expiry-date-input");
        await this._callService("grocery_set_expiry", {
          item_id: btn.dataset.id,
          expiry_date: input.value || null,
        });
        this._editingExpiryId = null;
        setTimeout(() => this._renderInventory(), 600);
      });
    });

    c.querySelectorAll(".cancel-expiry-btn").forEach(btn => {
      btn.addEventListener("click", () => {
        this._editingExpiryId = null;
        this._renderInventory();
      });
    });

    c.querySelectorAll(".remove-btn").forEach(btn => {
      btn.addEventListener("click", async () => {
        if (confirm("Ta bort från lagret?")) {
          await this._callService("grocery_manual_remove", { item_id: btn.dataset.id });
          setTimeout(() => this._renderInventory(), 600);
        }
      });
    });
  }

  // ── Hjälpfunktioner ───────────────────────────────────────────────────────
  async _callService(service, data) {
    if (!this._hass) return;
    try { await this._hass.callService("pyscript", service, data); }
    catch (e) { console.error(`[GroceryCard] pyscript.${service}:`, e); }
  }

  _getItems()             { return this._hass?.states?.["sensor.grocery_total_items"]?.attributes?.items || []; }
  _getExpiringSoonCount() { return parseInt(this._hass?.states?.["sensor.grocery_expiring_soon"]?.state || "0"); }
  _getExpiredCount()      { return parseInt(this._hass?.states?.["sensor.grocery_expired"]?.state || "0"); }
  _getLowStockCount()     { return parseInt(this._hass?.states?.["sensor.grocery_low_stock"]?.state || "0"); }

  _locationEmoji(loc) {
    if (loc === "frys")     return "❄️";
    if (loc === "skafferi") return "🏠";
    if (loc === "kyl")      return "🧊";
    return "";
  }

  _locationLabel(loc) {
    if (loc === "kyl")      return "🧊 Kyl";
    if (loc === "frys")     return "❄️ Frys";
    if (loc === "skafferi") return "🏠 Skafferi";
    return "🛒 Alla";
  }

  _categoryEmoji(cat) {
    const c = (cat || "").toLowerCase();
    const map = [
      [["mejeri","dairy","milk","mjölk"], "🥛"],
      [["kött","meat","fisk","fish","seafood"], "🥩"],
      [["grönsak","vegetable"], "🥦"],
      [["frukt","fruit"], "🍎"],
      [["bröd","bread","cereal","spannmål","grain"], "🍞"],
      [["konserv","canned"], "🥫"],
      [["frys","frozen"], "❄️"],
      [["dryck","beverage","drink"], "🥤"],
      [["krydda","spice","sauce","sås"], "🧂"],
      [["ägg","egg"], "🥚"],
      [["godis","candy","snack","chocolate","choklad"], "🍫"],
    ];
    for (const [keys, emoji] of map) {
      if (keys.some(k => c.includes(k))) return emoji;
    }
    return "🛒";
  }

  _stopCamera() {
    if (this._animFrame) { cancelAnimationFrame(this._animFrame); this._animFrame = null; }
    if (this._stream)    { this._stream.getTracks().forEach(t => t.stop()); this._stream = null; }
  }
  disconnectedCallback() { this._stopCamera(); }
}

customElements.define("grocery-scanner-card", GroceryScannerCard);
window.customCards = window.customCards || [];
window.customCards.push({
  type: "grocery-scanner-card",
  name: "Grocery Scanner",
  description: "Streckkodsskanning (Android/iOS/Desktop) + manuell inmatning för matlagret",
  preview: false,
});
