"""
Grocery Tracker – Home Assistant Pyscript v1.6
===============================================
Services:
  pyscript.grocery_scan_add(barcode, quantity=1, expiry_date=None, source="mobile")
  pyscript.grocery_scan_remove(barcode, source="mobile")
  pyscript.grocery_manual_add(name, quantity=1, unit="st", expiry_date=None, category="", barcode="")
  pyscript.grocery_manual_remove(item_id)
  pyscript.grocery_set_expiry(item_id, expiry_date)
  pyscript.grocery_refresh()
  pyscript.grocery_push_shopping_list()
  pyscript.grocery_generate_shopping_list()
  pyscript.grocery_suggest_recipes()     ← NY: receptförslag via LLM

Receptförslag – konfiguration i HA:
  input_select.grocery_recipe_provider: disabled | groq | gemini | anthropic | ha_ai_task
  input_text.grocery_recipe_api_key:    din API-nyckel (lämna tom för ha_ai_task)

NOTERING: pyscript blockerar open() (BUILTIN_EXCLUDE).
Fil-I/O sker via pathlib.Path.read_text/write_text via task.executor.
"""

import json
import pathlib

INVENTORY_FILE = "/config/grocery_inventory.json"
SHOPPING_LIST_ENTITY = "todo.shopping_list"
SHOPPING_LIST_FILE   = "/config/.shopping_list.json"
OFF_API = "https://world.openfoodfacts.org/api/v2/product/{barcode}.json"
OFF_HEADERS = {"User-Agent": "HomeAssistant-GroceryTracker/1.6 (homeassistant)"}

# ─── Fil-I/O via task.executor ────────────────────────────────────────────────

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

# ─── HTTP via aiohttp ─────────────────────────────────────────────────────────

async def _fetch_off(barcode):
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

async def _get_shopping_list_items():
    """Hämta aktiva varor från .shopping_list.json (ej slutförda)."""
    try:
        text = await task.executor(
            pathlib.Path(SHOPPING_LIST_FILE).read_text, encoding="utf-8"
        )
        items = json.loads(text)
        return [i for i in items if not i.get("complete", False)]
    except Exception as e:
        log.warning(f"[GroceryTracker] Kunde inte läsa inköpslista: {e}")
        return []

# ─── Inköpslista-hjälpare ─────────────────────────────────────────────────────

async def _add_to_shopping_list(name):
    """Lägg till en vara i HA:s inköpslista om den inte redan finns."""
    try:
        existing = await _get_shopping_list_items()
        existing_names = {i.get("name", "").lower() for i in existing}
        if name.lower() not in existing_names:
            todo.add_item(entity_id=SHOPPING_LIST_ENTITY, item=name)
            log.info(f"[GroceryTracker] '{name}' lagd till i inköpslistan")
        else:
            log.info(f"[GroceryTracker] '{name}' finns redan i inköpslistan, hoppar över")
    except Exception as e:
        log.warning(f"[GroceryTracker] Kunde inte lägga till i inköpslista: {e}")

# ─── Synkrona hjälpfunktioner ─────────────────────────────────────────────────

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

def _make_item(barcode, name, quantity, unit, expiry_date, category, source, image_url, min_quantity=0, location="kyl"):
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
        "shopping_list_suggested": False,
        "min_quantity": int(min_quantity) if min_quantity else 0,
        "location": str(location) if location else "kyl",
    }

def _compute_stats(inventory):
    from datetime import date, timedelta, datetime
    items = inventory.get("items", [])
    today = date.today()
    expiring_soon = []
    expired = []
    low_stock = []
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
        min_qty = item.get("min_quantity", 0)
        if min_qty > 0 and item.get("quantity", 0) <= min_qty:
            low_stock.append(item)
    return {
        "total": len(items),
        "expiring_soon": expiring_soon,
        "expired": expired,
        "low_stock": low_stock,
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
    state.set(
        "sensor.grocery_low_stock",
        len(stats["low_stock"]),
        {
            "friendly_name": "Lågt lager",
            "icon": "mdi:package-variant-minus",
            "unit_of_measurement": "st",
            "items": stats["low_stock"],
        },
    )
    state.set(
        "sensor.grocery_waste_log",
        len(inventory.get("waste_log", [])),
        {
            "friendly_name": "Matsvinn totalt",
            "icon": "mdi:trash-can-outline",
            "unit_of_measurement": "st",
            "log": inventory.get("waste_log", [])[-100:],
        },
    )

# ─── Services ────────────────────────────────────────────────────────────────

@service
async def grocery_scan_add(barcode=None, quantity=1, expiry_date=None, source="mobile", location="kyl", name_override=None):
    """Scanna en vara för att lägga till i lagret."""
    if not barcode:
        log.warning("[GroceryTracker] grocery_scan_add anropad utan streckkod")
        return

    barcode = str(barcode).strip()
    log.info(f"[GroceryTracker] Lägger till: {barcode} (källa: {source})")

    off_data = await _fetch_off(barcode)
    product = _parse_off(off_data)
    name = name_override or product.get("name") or f"Okänd vara ({barcode})"
    category = product.get("category", "")
    image_url = product.get("image_url", "")

    inventory = await _load_inventory()

    found = False
    for item in inventory["items"]:
        if item["barcode"] == barcode and item.get("expiry_date") == expiry_date:
            item["quantity"] += int(quantity)
            # Varan finns igen – återställ shopping-list-flaggan
            item["shopping_list_suggested"] = False
            found = True
            break

    if not found:
        new_item = _make_item(barcode, name, quantity, "st", expiry_date, category, source, image_url, location=location)
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
        # Varan finns inte i lager – logga ändå som svinn via OFF-lookup
        off_data = await _fetch_off(barcode)
        product = _parse_off(off_data)
        unknown_name = product.get("name") or f"Okänd vara ({barcode})"
        from datetime import datetime
        inventory["waste_log"].append({
            "date": datetime.now().isoformat()[:10],
            "name": unknown_name,
            "barcode": barcode,
            "source": source,
        })
        await _save_inventory(inventory)
        await _refresh_sensors(inventory)
        persistent_notification.create(
            title="🗑️ Svinn loggat",
            message=f"{unknown_name} (ej i lager – loggad i svinndagboken)",
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

    add_to_list = False
    low_stock_alert = False
    if found_item["quantity"] <= 0:
        inventory["items"].remove(found_item)
        add_to_list = True
    else:
        min_qty = found_item.get("min_quantity", 0)
        if min_qty > 0 and found_item["quantity"] <= min_qty:
            low_stock_alert = True

    await _save_inventory(inventory)
    await _refresh_sensors(inventory)

    # Lägg till i inköpslistan när sista exemplaret förbrukats eller vid lågt lager
    if add_to_list:
        await _add_to_shopping_list(found_item["name"])
    elif low_stock_alert:
        await _add_to_shopping_list(found_item["name"])

    if add_to_list:
        remain_txt = " – lagd till i inköpslistan 🛒"
    elif low_stock_alert:
        remain_txt = f" ({found_item['quantity']} kvar) ⚠️ Lågt lager – lagd till i inköpslistan"
    else:
        remain_txt = f" ({found_item['quantity']} kvar)"
    persistent_notification.create(
        title="🗑️ Borttagen",
        message=f"{found_item['name']}{remain_txt}",
        notification_id="grocery_action",
    )


@service
async def grocery_manual_add(
    name=None, quantity=1, unit="st", expiry_date=None, category="", barcode="", min_quantity=0, location="kyl"
):
    """Lägg till vara manuellt."""
    if not name:
        log.warning("[GroceryTracker] grocery_manual_add anropad utan namn")
        return

    inventory = await _load_inventory()
    new_item = _make_item(barcode or "", name, quantity, unit, expiry_date, category, "manual", "", min_quantity=min_quantity, location=location)
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
    """Ta bort en vara via ID – lägger automatiskt till i inköpslistan."""
    if not item_id:
        return

    inventory = await _load_inventory()
    removed = [i for i in inventory["items"] if i["id"] == str(item_id)]
    inventory["items"] = [i for i in inventory["items"] if i["id"] != str(item_id)]

    if removed:
        from datetime import datetime
        item = removed[0]
        inventory["waste_log"].append({
            "date": datetime.now().isoformat()[:10],
            "name": item["name"],
            "barcode": item.get("barcode", ""),
            "source": "manual_remove",
        })
        await _save_inventory(inventory)
        await _refresh_sensors(inventory)
        await _add_to_shopping_list(item["name"])


@service
async def grocery_set_expiry(item_id=None, expiry_date=None):
    """Uppdatera bäst-före-datum."""
    if not item_id:
        return

    inventory = await _load_inventory()
    for item in inventory["items"]:
        if item["id"] == str(item_id):
            item["expiry_date"] = expiry_date
            item["shopping_list_suggested"] = False  # Nytt datum → återställ flagga
            break

    await _save_inventory(inventory)
    await _refresh_sensors(inventory)


@service
async def grocery_refresh():
    """Ladda om lagret från fil och uppdatera sensorer."""
    inventory = await _load_inventory()
    await _refresh_sensors(inventory)
    log.info("[GroceryTracker] Lager omladdad.")


@service
async def grocery_push_shopping_list():
    """Hämta inköpslistan och skicka som push-notis till alla enheter."""
    items = await _get_shopping_list_items()

    if not items:
        notify.notify(
            title="🛒 Inköpslistan är tom",
            message="Inga varor på listan just nu.",
        )
        return

    lines = [f"• {i.get('name', '?')}" for i in items]
    message = "\n".join(lines)
    notify.notify(
        title=f"🛒 Inköpslistan – {len(items)} varor",
        message=message,
        data={"url": "/grocery-dashboard/inkopslista"},
    )
    log.info(f"[GroceryTracker] Inköpslista pushad: {len(items)} varor")


@service
async def grocery_generate_shopping_list():
    """Lägg manuellt till alla utgångna/snart utgångna varor i inköpslistan."""
    inventory = await _load_inventory()
    stats = _compute_stats(inventory)
    candidates = stats["expired"] + stats["expiring_soon"]

    if not candidates:
        persistent_notification.create(
            title="🛒 Inköpslista",
            message="Inga utgångna eller snart-utgångna varor att föreslå.",
            notification_id="grocery_shopping",
        )
        return

    added = []
    for item in candidates:
        await _add_to_shopping_list(item["name"])
        item["shopping_list_suggested"] = True
        added.append(item["name"])

    await _save_inventory(inventory)

    persistent_notification.create(
        title="🛒 Inköpslista uppdaterad",
        message=f"Lade till: {', '.join(added)}",
        notification_id="grocery_shopping",
    )
    log.info(f"[GroceryTracker] Genererade inköpslista: {added}")


# ─── Lågstocksvarning & Plats ────────────────────────────────────────────────

@service
async def grocery_set_min_quantity(item_id=None, min_quantity=0):
    """Sätt lågstocksvarningsgräns för en vara (0 = inaktiverad)."""
    if not item_id:
        return
    inventory = await _load_inventory()
    for item in inventory["items"]:
        if item["id"] == str(item_id):
            item["min_quantity"] = int(min_quantity) if min_quantity else 0
            break
    await _save_inventory(inventory)
    await _refresh_sensors(inventory)


@service
async def grocery_set_location(item_id=None, location="kyl"):
    """Sätt plats för en vara: kyl, frys eller skafferi."""
    if not item_id:
        return
    inventory = await _load_inventory()
    for item in inventory["items"]:
        if item["id"] == str(item_id):
            item["location"] = str(location) if location else "kyl"
            break
    await _save_inventory(inventory)
    await _refresh_sensors(inventory)


# ─── Daglig påminnelse kl 16:00 ─────────────────────────────────────────────

@time_trigger("cron(0 16 * * *)")
async def _daily_expiry_check():
    inventory = await _load_inventory()
    stats = _compute_stats(inventory)

    expiring = stats["expiring_soon"]
    expired = stats["expired"]

    if not expiring and not expired:
        return

    # Lägg till utgångna/snart utgångna i inköpslistan (en gång per vara)
    list_changed = False
    for item in expired + expiring:
        if not item.get("shopping_list_suggested"):
            await _add_to_shopping_list(item["name"])
            item["shopping_list_suggested"] = True
            list_changed = True

    if list_changed:
        await _save_inventory(inventory)

    # Skicka daglig notis
    lines = []
    if expired:
        lines.append("🔴 Utgångna:")
        for i in expired:
            lines.append(f"  • {i['name']} ({i.get('expiry_date', '?')})")
    if expiring:
        lines.append("🟡 Går ut snart:")
        for i in expiring:
            lines.append(f"  • {i['name']} (bäst före {i.get('expiry_date', '?')})")

    lines.append("\n🛒 Lagd till i inköpslistan automatiskt.")

    notify.notify(
        title="🍽️ Kylskåpsrapporten",
        message="\n".join(lines),
    )
    log.info(f"[GroceryTracker] Daglig koll: {len(expiring)} snart utgångna, {len(expired)} utgångna")

    # Trigga receptförslag om leverantör är konfigurerad
    provider = state.get("input_select.grocery_recipe_provider") or "disabled"
    if provider != "disabled":
        await _do_suggest_recipes(expired + expiring)


# ─── Receptförslag via LLM ───────────────────────────────────────────────────

async def _do_suggest_recipes(candidates):
    """Intern hjälpare: bygg prompt och skicka receptförslag."""
    if not candidates:
        return
    ingredients = list({item["name"] for item in candidates})
    prompt = (
        f"Jag har dessa matvaror som snart går ut eller redan har gått ut: "
        f"{', '.join(ingredients)}. "
        f"Föreslå 2-3 enkla och goda recept som använder dessa ingredienser. "
        f"Håll varje recept kort: namn, huvudingredienser och en mening om tillagning. "
        f"Svara på svenska."
    )
    result = await _call_recipe_llm(prompt)
    if result:
        notify.notify(
            title="👨‍🍳 Receptförslag – använd innan det går ut!",
            message=result,
        )
        log.info(f"[GroceryTracker] Receptförslag skickat för: {ingredients}")


async def _call_recipe_llm(prompt):
    """Anropa konfigurerad LLM-leverantör. Faller tillbaka på ha_ai_task om API-nyckel saknas."""
    provider = state.get("input_select.grocery_recipe_provider") or "disabled"
    api_key  = state.get("input_text.grocery_recipe_api_key") or ""

    # Auto-fallback: om nyckel saknas för en leverantör som kräver det → ha_ai_task
    needs_key = provider in ("groq", "gemini", "anthropic")
    if needs_key and not api_key:
        log.info(f"[GroceryTracker] API-nyckel saknas för {provider} – faller tillbaka på ha_ai_task")
        return await _call_ha_ai_task(prompt)

    if provider == "groq":
        return await _call_groq(prompt, api_key)
    elif provider == "gemini":
        return await _call_gemini(prompt, api_key)
    elif provider == "anthropic":
        return await _call_anthropic(prompt, api_key)
    elif provider == "ha_ai_task":
        return await _call_ha_ai_task(prompt)
    else:
        log.warning(f"[GroceryTracker] recipe_provider är '{provider}' – receptförslag inaktiverat")
        return None


async def _call_groq(prompt, api_key):
    import aiohttp
    if not api_key:
        log.warning("[GroceryTracker] Groq: API-nyckel saknas i input_text.grocery_recipe_api_key")
        return None
    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {
        "model": "llama-3.1-8b-instant",
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 500,
        "temperature": 0.7,
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, headers=headers,
                                    timeout=aiohttp.ClientTimeout(total=15)) as resp:
                if resp.status == 200:
                    data = await resp.json(content_type=None)
                    return data["choices"][0]["message"]["content"].strip()
                log.warning(f"[GroceryTracker] Groq API-fel: {resp.status}")
    except Exception as e:
        log.warning(f"[GroceryTracker] Groq-anrop misslyckades: {e}")
    return None


async def _call_gemini(prompt, api_key):
    import aiohttp
    if not api_key:
        log.warning("[GroceryTracker] Gemini: API-nyckel saknas i input_text.grocery_recipe_api_key")
        return None
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"gemini-2.0-flash:generateContent?key={api_key}"
    )
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"maxOutputTokens": 500, "temperature": 0.7},
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload,
                                    timeout=aiohttp.ClientTimeout(total=15)) as resp:
                if resp.status == 200:
                    data = await resp.json(content_type=None)
                    return data["candidates"][0]["content"]["parts"][0]["text"].strip()
                log.warning(f"[GroceryTracker] Gemini API-fel: {resp.status}")
    except Exception as e:
        log.warning(f"[GroceryTracker] Gemini-anrop misslyckades: {e}")
    return None


async def _call_anthropic(prompt, api_key):
    import aiohttp
    if not api_key:
        log.warning("[GroceryTracker] Anthropic: API-nyckel saknas i input_text.grocery_recipe_api_key")
        return None
    url = "https://api.anthropic.com/v1/messages"
    headers = {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }
    payload = {
        "model": "claude-haiku-4-5-20251001",
        "max_tokens": 500,
        "messages": [{"role": "user", "content": prompt}],
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, headers=headers,
                                    timeout=aiohttp.ClientTimeout(total=15)) as resp:
                if resp.status == 200:
                    data = await resp.json(content_type=None)
                    return data["content"][0]["text"].strip()
                log.warning(f"[GroceryTracker] Anthropic API-fel: {resp.status}")
    except Exception as e:
        log.warning(f"[GroceryTracker] Anthropic-anrop misslyckades: {e}")
    return None


async def _call_ha_ai_task(prompt):
    """Anropa HA:s inbyggda ai_task (kräver HA 2025.7+ med AI-integration konfigurerad)."""
    try:
        result = ai_task.generate_data(
            task_name="grocery_recipe_suggestions",
            instructions=prompt,
        )
        return (result or {}).get("data", {}).get("text", "").strip() or None
    except Exception as e:
        log.warning(f"[GroceryTracker] HA AI Task-anrop misslyckades: {e}")
    return None


@service
async def grocery_suggest_recipes():
    """Hämta varor som snart går ut och skicka receptförslag via konfigurerad LLM."""
    provider = state.get("input_select.grocery_recipe_provider") or "disabled"
    if provider == "disabled":
        persistent_notification.create(
            title="👨‍🍳 Receptförslag inaktiverat",
            message="Välj en leverantör i input_select.grocery_recipe_provider för att aktivera.",
            notification_id="grocery_recipes",
        )
        return

    inventory = await _load_inventory()
    stats = _compute_stats(inventory)
    candidates = stats["expired"] + stats["expiring_soon"]

    if not candidates:
        persistent_notification.create(
            title="👨‍🍳 Inga varor att föreslå recept för",
            message="Inga utgångna eller snart-utgångna varor i lagret just nu.",
            notification_id="grocery_recipes",
        )
        return

    await _do_suggest_recipes(candidates)


# ─── Startup ─────────────────────────────────────────────────────────────────

@time_trigger("startup")
async def _startup():
    inventory = await _load_inventory()
    await _refresh_sensors(inventory)
    log.info("[GroceryTracker] Grocery Tracker v1.6 startad.")
