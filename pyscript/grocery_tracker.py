"""
Grocery Tracker – Home Assistant Pyscript
=========================================
Services:
  pyscript.grocery_scan_add(barcode, quantity=1, expiry_date=None, source="mobile")
  pyscript.grocery_scan_remove(barcode, source="mobile")
  pyscript.grocery_manual_add(name, quantity=1, unit="st", expiry_date=None, category="", barcode="")
  pyscript.grocery_manual_remove(item_id)
  pyscript.grocery_set_expiry(item_id, expiry_date)
  pyscript.grocery_refresh()

NOTERING: pyscript blockerar open() som builtin (BUILTIN_EXCLUDE).
Fil-I/O sker via pathlib.Path.read_text/write_text via task.executor —
dessa är vanliga Python-metoder (inte pyscript EvalFuncVar) och accepteras av task.executor.
"""

import json
import pathlib

INVENTORY_FILE = "/config/grocery_inventory.json"
OFF_API = "https://world.openfoodfacts.org/api/v2/product/{barcode}.json"
OFF_HEADERS = {"User-Agent": "HomeAssistant-GroceryTracker/1.0 (homeassistant)"}

# ─── Fil-I/O via task.executor (pathlib.Path-metoder = vanlig Python, ej EvalFuncVar) ───

async def _load_inventory():
    try:
        text = await task.executor(
            pathlib.Path(INVENTORY_FILE).read_text, encoding="utf-8"
        )
        return json.loads(text)
    except Exception:
        return {"items": [], "waste_log": []}

async def _save_inventory(data):
    text = json.dumps(data, ensure_ascii=False, indent=2)
    await task.executor(
        pathlib.Path(INVENTORY_FILE).write_text, text, encoding="utf-8"
    )

# ─── HTTP-lookup via aiohttp (async, inget task.executor behövs) ─────────────

async def _fetch_off(barcode):
    """Slå upp produkt i Open Food Facts."""
    import aiohttp
    url = OFF_API.format(barcode=barcode)
    try:
        async with aiohttp.ClientSession(headers=OFF_HEADERS) as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status == 200:
                    return await resp.json(content_type=None)
    except Exception as e:
        log.warning(f"[GroceryTracker] OFF-lookup misslyckades för {barcode}: {e}")
    return {}

# ─── Synkrona hjälpfunktioner (ingen fil-I/O, anropas direkt) ────────────────

def _parse_off(data):
    if not data or data.get("status") != 1:
        return {}
    p = data.get("product", {})
    name = (
        p.get("product_name_sv")
        or p.get("product_name")
        or p.get("product_name_en")
        or ""
    )
    cats = p.get("categories_tags", [])
    category = cats[-1].replace("en:", "").replace("-", " ") if cats else ""
    return {
        "name": name.strip(),
        "category": category,
        "image_url": p.get("image_small_url", ""),
    }

def _make_item(barcode, name, quantity, unit, expiry_date, category, source, image_url):
    import uuid as _uuid
    from datetime import datetime
    return {
        "id": str(_uuid.uuid4()),
        "barcode": str(barcode) if barcode else "",
        "name": str(name),
        "category": str(category),
        "quantity": int(quantity),
        "unit": str(unit),
        "added_date": datetime.now().isoformat()[:10],
        "expiry_date": expiry_date or None,
        "source": str(source),
        "image_url": str(image_url) if image_url else "",
    }

def _compute_stats(inventory):
    from datetime import date, timedelta, datetime
    items = inventory.get("items", [])
    today = date.today()
    expiring_soon = []
    expired = []
    for item in items:
        ed = item.get("expiry_date")
        if ed:
            try:
                exp = datetime.fromisoformat(ed).date()
                if exp < today:
                    expired.append(item)
                elif exp <= today + timedelta(days=2):
                    expiring_soon.append(item)
            except (ValueError, TypeError):
                pass
    return {
        "total": len(items),
        "expiring_soon": expiring_soon,
        "expired": expired,
        "items": items,
    }

# ─── Sensoruppdatering ────────────────────────────────────────────────────────

async def _refresh_sensors(inventory):
    stats = _compute_stats(inventory)
    state.set(
        "sensor.grocery_total_items",
        stats["total"],
        {
            "friendly_name": "Matvaror i lager",
            "icon": "mdi:fridge",
            "unit_of_measurement": "st",
            "items": stats["items"],
        },
    )
    state.set(
        "sensor.grocery_expiring_soon",
        len(stats["expiring_soon"]),
        {
            "friendly_name": "Går ut inom 2 dagar",
            "icon": "mdi:clock-alert-outline",
            "unit_of_measurement": "st",
            "items": stats["expiring_soon"],
        },
    )
    state.set(
        "sensor.grocery_expired",
        len(stats["expired"]),
        {
            "friendly_name": "Utgångna varor",
            "icon": "mdi:alert-circle-outline",
            "unit_of_measurement": "st",
            "items": stats["expired"],
        },
    )

# ─── Services ────────────────────────────────────────────────────────────────

@service
async def grocery_scan_add(barcode=None, quantity=1, expiry_date=None, source="mobile"):
    """Scanna en vara för att lägga till i lagret."""
    if not barcode:
        log.warning("[GroceryTracker] grocery_scan_add anropad utan streckkod")
        return

    barcode = str(barcode).strip()
    log.info(f"[GroceryTracker] Lägger till: {barcode} (källa: {source})")

    off_data = await _fetch_off(barcode)
    product = _parse_off(off_data)
    name = product.get("name") or f"Okänd vara ({barcode})"
    category = product.get("category", "")
    image_url = product.get("image_url", "")

    inventory = await _load_inventory()

    found = False
    for item in inventory["items"]:
        if item["barcode"] == barcode and item.get("expiry_date") == expiry_date:
            item["quantity"] += int(quantity)
            found = True
            break

    if not found:
        new_item = _make_item(barcode, name, quantity, "st", expiry_date, category, source, image_url)
        inventory["items"].append(new_item)

    await _save_inventory(inventory)
    await _refresh_sensors(inventory)

    qty_txt = f" ×{quantity}" if int(quantity) > 1 else ""
    exp_txt = f" (bäst före {expiry_date})" if expiry_date else ""
    persistent_notification.create(
        title="✅ Tillagd i lager",
        message=f"{name}{qty_txt}{exp_txt}",
        notification_id="grocery_action",
    )


@service
async def grocery_scan_remove(barcode=None, source="mobile"):
    """Scanna en vara för att ta bort från lagret."""
    if not barcode:
        log.warning("[GroceryTracker] grocery_scan_remove anropad utan streckkod")
        return

    barcode = str(barcode).strip()
    log.info(f"[GroceryTracker] Tar bort: {barcode} (källa: {source})")

    inventory = await _load_inventory()

    found_item = None
    for item in inventory["items"]:
        if item["barcode"] == barcode:
            found_item = item
            break

    if not found_item:
        persistent_notification.create(
            title="⚠️ Vara ej i lager",
            message=f"Streckkod {barcode} finns inte i lagret.",
            notification_id="grocery_action",
        )
        return

    found_item["quantity"] -= 1

    from datetime import datetime
    inventory["waste_log"].append({
        "date": datetime.now().isoformat()[:10],
        "name": found_item["name"],
        "barcode": barcode,
        "source": source,
    })

    if found_item["quantity"] <= 0:
        inventory["items"].remove(found_item)

    await _save_inventory(inventory)
    await _refresh_sensors(inventory)

    remaining = max(0, found_item["quantity"] - 1)
    remain_txt = f" ({remaining} kvar)" if remaining > 0 else ""
    persistent_notification.create(
        title="🗑️ Borttagen",
        message=f"{found_item['name']}{remain_txt}",
        notification_id="grocery_action",
    )


@service
async def grocery_manual_add(
    name=None, quantity=1, unit="st", expiry_date=None, category="", barcode=""
):
    """Lägg till vara manuellt."""
    if not name:
        log.warning("[GroceryTracker] grocery_manual_add anropad utan namn")
        return

    inventory = await _load_inventory()
    new_item = _make_item(barcode or "", name, quantity, unit, expiry_date, category, "manual", "")
    inventory["items"].append(new_item)
    await _save_inventory(inventory)
    await _refresh_sensors(inventory)

    qty_txt = f"{quantity} {unit} " if unit != "st" else (f"×{quantity} " if int(quantity) > 1 else "")
    persistent_notification.create(
        title="✅ Manuellt tillagd",
        message=f"{qty_txt}{name}",
        notification_id="grocery_action",
    )


@service
async def grocery_manual_remove(item_id=None):
    """Ta bort en vara via ID."""
    if not item_id:
        return

    inventory = await _load_inventory()
    before = len(inventory["items"])
    inventory["items"] = [i for i in inventory["items"] if i["id"] != str(item_id)]

    if len(inventory["items"]) < before:
        await _save_inventory(inventory)
        await _refresh_sensors(inventory)


@service
async def grocery_set_expiry(item_id=None, expiry_date=None):
    """Uppdatera bäst-före-datum."""
    if not item_id:
        return

    inventory = await _load_inventory()
    for item in inventory["items"]:
        if item["id"] == str(item_id):
            item["expiry_date"] = expiry_date
            break

    await _save_inventory(inventory)
    await _refresh_sensors(inventory)


@service
async def grocery_refresh():
    """Ladda om lagret från fil och uppdatera sensorer."""
    inventory = await _load_inventory()
    await _refresh_sensors(inventory)
    log.info("[GroceryTracker] Lager omladdad.")


# ─── Daglig påminnelse kl 16:00 ─────────────────────────────────────────────

@time_trigger("cron(0 16 * * *)")
async def _daily_expiry_check():
    inventory = await _load_inventory()
    stats = _compute_stats(inventory)

    expiring = stats["expiring_soon"]
    expired = stats["expired"]

    if not expiring and not expired:
        return

    lines = []
    if expired:
        lines.append("🔴 Utgångna:")
        for i in expired:
            lines.append(f"  • {i['name']} ({i.get('expiry_date', '?')})")
    if expiring:
        lines.append("🟡 Går ut snart:")
        for i in expiring:
            lines.append(f"  • {i['name']} (bäst före {i.get('expiry_date', '?')})")

    all_items = stats["items"]
    ingredient_list = ", ".join(
        f"{i['name']}" + (f" ({i['quantity']} {i['unit']})" if i.get("unit") else "")
        for i in all_items[:20]
    )

    message = "\n".join(lines)
    if ingredient_list:
        message += f"\n\n📦 I lager: {ingredient_list}"

    notify.notify(title="🍽️ Kylskåpsrapporten", message=message)
    log.info(f"[GroceryTracker] Daglig koll: {len(expiring)} snart utgångna, {len(expired)} utgångna")


# ─── Startup ─────────────────────────────────────────────────────────────────

@time_trigger("startup")
async def _startup():
    inventory = await _load_inventory()
    await _refresh_sensors(inventory)
    log.info("[GroceryTracker] Grocery Tracker startad.")
