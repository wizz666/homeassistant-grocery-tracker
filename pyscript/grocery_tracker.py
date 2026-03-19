"""
Grocery Tracker – Home Assistant Pyscript v1.9
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
SPOONACULAR_BASE = "https://api.spoonacular.com"

TIBBER_PULSE_CONSUMPTION = "sensor.tibber_pulse_dammtorpsgatan_22_accumulated_consumption"
TIBBER_PULSE_POWER = "sensor.tibber_pulse_dammtorpsgatan_22_power"

# ─── Säker state-hämtning ─────────────────────────────────────────────────────
# state.get() kastar NameError i pyscript om entity inte existerar ännu.
# Använd _sget() överallt för HA-helpers och sensorer som kan saknas.

def _sget(entity_id, default=None):
    try:
        val = state.get(entity_id)
        return val if val is not None else default
    except Exception:
        return default

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
        data={"url": "/grocery-dashboard/inkopslista"},
    )
    log.info(f"[GroceryTracker] Daglig koll: {len(expiring)} snart utgångna, {len(expired)} utgångna")

    # Trigga receptförslag om leverantör är konfigurerad
    provider = _sget("input_select.grocery_recipe_provider", "disabled")
    if provider != "disabled":
        await _do_suggest_recipes(expired + expiring)


# ─── Spoonacular API ─────────────────────────────────────────────────────────

async def _call_spoonacular(ingredients, api_key):
    """Hämta 3 receptförslag från Spoonacular baserat på ingredienslista."""
    import aiohttp
    import re as _re

    ingredients_str = ",+".join([i.replace(" ", "+") for i in ingredients[:10]])
    find_params = {
        "ingredients": ingredients_str,
        "number": 3,
        "ranking": 1,
        "ignorePantry": "true",
        "apiKey": api_key,
    }

    recipes = []
    try:
        async with aiohttp.ClientSession() as session:
            # Steg 1: findByIngredients
            async with session.get(
                f"{SPOONACULAR_BASE}/recipes/findByIngredients",
                params=find_params,
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                if resp.status == 402:
                    log.warning("[GroceryTracker] Spoonacular: daglig kvot förbrukad (402)")
                    return None
                if resp.status != 200:
                    log.warning(f"[GroceryTracker] Spoonacular findByIngredients: {resp.status}")
                    return None
                results = await resp.json(content_type=None)

            if not results:
                return None

            # Steg 2: hämta detaljer per recept
            for recipe in results[:3]:
                recipe_id = recipe.get("id")
                if not recipe_id:
                    continue
                async with session.get(
                    f"{SPOONACULAR_BASE}/recipes/{recipe_id}/information",
                    params={"apiKey": api_key, "includeNutrition": "false"},
                    timeout=aiohttp.ClientTimeout(total=15),
                ) as resp:
                    if resp.status == 200:
                        info = await resp.json(content_type=None)
                        recipes.append({
                            "title": recipe.get("title", ""),
                            "used": [i.get("name", "") for i in recipe.get("usedIngredients", [])],
                            "missed": [i.get("name", "") for i in recipe.get("missedIngredients", [])],
                            "ready_in": info.get("readyInMinutes", "?"),
                            "servings": info.get("servings", "?"),
                            "instructions": info.get("instructions", "") or "",
                            "source_url": info.get("sourceUrl", ""),
                        })
    except Exception as e:
        log.warning(f"[GroceryTracker] Spoonacular-anrop misslyckades: {e}")
        return None

    if not recipes:
        return None

    # Formatera som markdown (samma format som LLM-svar)
    lines = []
    for i, r in enumerate(recipes, 1):
        lines.append(f"### {i}. {r['title']}")
        lines.append(f"⏱️ {r['ready_in']} min · 🍽️ {r['servings']} portioner")
        if r["used"]:
            lines.append(f"✅ Ingredienser du har: {', '.join(r['used'])}")
        if r["missed"]:
            lines.append(f"🛒 Köp också: {', '.join(r['missed'])}")
        # Rensa HTML-taggar ur instruktioner
        instructions = _re.sub(r'<[^>]+>', '', r["instructions"]).strip()
        if instructions:
            instructions = instructions[:600] + ("..." if len(instructions) > 600 else "")
            lines.append(f"\n{instructions}")
        if r["source_url"]:
            lines.append(f"\n🔗 [Fullständigt recept]({r['source_url']})")
        lines.append("")

    return "\n".join(lines).strip()


async def _translate_to_swedish(text):
    """Översätt recepttext till svenska. Försöker Groq först, faller tillbaka på ha_ai_task."""
    prompt = (
        "Översätt följande recepttext till svenska. "
        "Behåll exakt samma markdown-formatering (###, emojis, radbrytningar, fetstil). "
        "Översätt INTE URL:er. Länktexten 'Fullständigt recept' behålls på svenska. "
        "Svara BARA med den översatta texten — inget annat.\n\n"
        f"{text}"
    )

    # Försök Groq (gratis, snabb)
    api_key = _sget("input_text.ai_hub_groq_key", "").strip()
    if not api_key:
        api_key = _sget("input_text.grocery_api_key_groq", "").strip()
    if api_key:
        translated = await _call_openai_compatible(
            prompt, api_key,
            url="https://api.groq.com/openai/v1/chat/completions",
            model="llama-3.3-70b-versatile",
            provider_name="Groq (översättning)",
        )
        if translated:
            return translated.strip()

    # Fallback: ha_ai_task (Google AI — kräver ingen nyckel)
    log.info("[GroceryTracker] Groq-nyckel saknas — översätter via ha_ai_task")
    translated = await _call_ha_ai_task(prompt)
    return translated.strip() if translated else text


# ─── Receptförslag via LLM / Spoonacular ─────────────────────────────────────

async def _do_suggest_recipes(candidates, provider_override=None):
    """Intern hjälpare: hämta receptförslag via Spoonacular eller LLM."""
    if not candidates:
        return
    ingredients = list({item["name"] for item in candidates})

    provider = provider_override or _sget("input_select.grocery_recipe_provider", "disabled")

    if provider == "spoonacular":
        api_key = _sget("input_text.grocery_api_key_spoonacular", "").strip()
        if not api_key:
            persistent_notification.create(
                title="🍴 Spoonacular – nyckel saknas",
                message="Ange din Spoonacular API-nyckel i Inställningar-fliken.",
                notification_id="grocery_recipes",
            )
            return
        result = await _call_spoonacular(ingredients, api_key)
        if result:
            result = await _translate_to_swedish(result)
    else:
        prompt = (
            f"Jag har dessa matvaror som snart går ut eller redan har gått ut: "
            f"{', '.join(ingredients)}. "
            f"Föreslå 2-3 enkla och goda recept som använder dessa ingredienser. "
            f"Håll varje recept kort: namn, huvudingredienser och en mening om tillagning. "
            f"Svara på svenska. "
            f"Lägg till allra sist, på en ensam rad (inga radbrytningar efter): "
            f"ENERGI: Xmin REDSKAP: spis (eller ugn eller mikro) "
            f"där X är uppskattad total tillagningstid i minuter. "
            f"Exempel: ENERGI: 25min REDSKAP: spis"
        )
        result = await _call_recipe_llm(prompt, provider_override=provider_override)
    if result:
        import re as _re
        import datetime as _dt

        # ── Parsa och ta bort ENERGI-raden ────────────────────────────────────
        try:
            _WATT = {
                "spis": int(float(_sget("input_number.grocery_power_spis", 2000))),
                "ugn":  int(float(_sget("input_number.grocery_power_ugn",  2500))),
                "mikro": int(float(_sget("input_number.grocery_power_mikro", 800))),
            }
        except (ValueError, TypeError):
            _WATT = {"spis": 2000, "ugn": 2500, "mikro": 800}
        cooking_minutes = None
        cooking_appliance = None
        cooking_kwh = None
        cooking_cost_kr = None
        electricity_price = None

        energy_match = _re.search(
            r'ENERGI:\s*(\d+)\s*min\s+REDSKAP:\s*(spis|ugn|mikro)',
            result, _re.IGNORECASE
        )
        if energy_match:
            cooking_minutes = int(energy_match.group(1))
            cooking_appliance = energy_match.group(2).lower()
            _watt = _WATT.get(cooking_appliance, 2000)
            cooking_kwh = round(_watt / 1000 * cooking_minutes / 60, 2)
            try:
                _price = float(_sget("sensor.dammtorpsgatan_22_current_electricity_price", 0))
                electricity_price = round(_price, 2)
                cooking_cost_kr = round(cooking_kwh * _price, 2)
            except (ValueError, TypeError):
                pass
            # Rensa ENERGI-raden ur recepttexten
            result = _re.sub(
                r'\n?ENERGI:\s*\d+\s*min\s+REDSKAP:\s*\w+[^\n]*', '', result
            ).strip()
            log.info(
                f"[GroceryTracker] Energi: {cooking_appliance} {cooking_minutes}min "
                f"= {cooking_kwh} kWh = {cooking_cost_kr} kr "
                f"(elpris {electricity_price} kr/kWh)"
            )
        else:
            log.info("[GroceryTracker] AI returnerade ingen ENERGI-rad – hoppar över energiberäkning")

        updated = _dt.datetime.now().strftime("%d %b %Y, %H:%M")

        # Nollställ Tibber Pulse-session när nytt recept genereras
        try:
            input_number.set_value(entity_id="input_number.grocery_actual_cooking_kwh", value=0)
            input_number.set_value(entity_id="input_number.grocery_actual_cooking_cost", value=0)
            input_boolean.turn_off(entity_id="input_boolean.grocery_cooking_active")
        except Exception:
            pass

        # Spara i sensor med energiattribut
        state.set("sensor.grocery_last_recipe", updated, {
            "recipe": result,
            "ingredients": ", ".join(ingredients),
            "cooking_minutes": cooking_minutes,
            "cooking_appliance": cooking_appliance,
            "cooking_kwh": cooking_kwh,
            "cooking_cost_kr": cooking_cost_kr,
            "electricity_price": electricity_price,
            "friendly_name": "Senaste receptförslag",
        })

        # Bygg notis (med energiinfo om tillgänglig)
        energy_txt = ""
        if cooking_kwh and cooking_cost_kr is not None:
            energy_txt = f"\n⚡ {cooking_appliance} {cooking_minutes} min · {cooking_kwh} kWh · ca {cooking_cost_kr} kr"

        persistent_notification.create(
            title="👨‍🍳 Receptförslag – använd innan det går ut!",
            message=result + energy_txt,
            notification_id="grocery_recipes",
        )

        notify.notify(
            title="👨‍🍳 Receptförslag – använd innan det går ut!",
            message=f"Tryck för att se recept på: {', '.join(ingredients)}",
            data={"url": "/grocery-dashboard/recept"},
        )
        log.info(f"[GroceryTracker] Receptförslag sparat och skickat för: {ingredients}")


# Leverantör → input_text-entity för API-nyckel (per leverantör, egna Grocery-nycklar)
_PROVIDER_KEY_ENTITY = {
    "groq":         "input_text.grocery_api_key_groq",
    "gemini":       "input_text.grocery_api_key_gemini",
    "openrouter":   "input_text.grocery_api_key_openrouter",
    "mistral":      "input_text.grocery_api_key_mistral",
    "openai":       "input_text.grocery_api_key_openai",
    "anthropic":    "input_text.grocery_api_key_anthropic",
    "spoonacular":  "input_text.grocery_api_key_spoonacular",
}

# AI Hub-nycklar (prioriteras framför egna Grocery-nycklar)
_AI_HUB_KEY_ENTITY = {
    "groq":      "input_text.ai_hub_groq_key",
    "anthropic": "input_text.ai_hub_anthropic_key",
    "openai":    "input_text.ai_hub_openai_key",
}


def _resolve_grocery_key(provider):
    """
    Hämtar API-nyckel för provider.
    Prioritet: AI Hub → egna Grocery-nycklar
    """
    hub_entity = _AI_HUB_KEY_ENTITY.get(provider)
    if hub_entity:
        hub_key = _sget(hub_entity, "")
        if hub_key and hub_key not in ("", "unknown", "none", "unavailable"):
            return hub_key
    own_entity = _PROVIDER_KEY_ENTITY.get(provider)
    return _sget(own_entity, "") if own_entity else ""


async def _call_recipe_llm(prompt, provider_override=None):
    """Anropa konfigurerad LLM-leverantör. Faller tillbaka på ha_ai_task om API-nyckel saknas."""
    provider = provider_override or _sget("input_select.grocery_recipe_provider", "disabled")

    # Läs nyckel – AI Hub har prioritet, sedan egna Grocery-nycklar
    key_entity = _PROVIDER_KEY_ENTITY.get(provider)
    api_key = _resolve_grocery_key(provider) if key_entity else ""

    # Auto-fallback: om nyckel saknas för en leverantör som kräver det → ha_ai_task
    if key_entity and not api_key:
        log.info(f"[GroceryTracker] API-nyckel saknas för {provider} – faller tillbaka på ha_ai_task")
        return await _call_ha_ai_task(prompt)

    if provider == "groq":
        return await _call_openai_compatible(
            prompt, api_key,
            url="https://api.groq.com/openai/v1/chat/completions",
            model="llama-3.3-70b-versatile",
            provider_name="Groq",
        )
    elif provider == "gemini":
        return await _call_gemini(prompt, api_key)
    elif provider == "openrouter":
        return await _call_openrouter(prompt, api_key)
    elif provider == "mistral":
        return await _call_openai_compatible(
            prompt, api_key,
            url="https://api.mistral.ai/v1/chat/completions",
            model="mistral-small-latest",
            provider_name="Mistral",
        )
    elif provider == "openai":
        return await _call_openai_compatible(
            prompt, api_key,
            url="https://api.openai.com/v1/chat/completions",
            model="gpt-4o-mini",
            provider_name="OpenAI",
        )
    elif provider == "anthropic":
        return await _call_anthropic(prompt, api_key)
    elif provider == "ha_ai_task":
        return await _call_ha_ai_task(prompt)
    else:
        log.warning(f"[GroceryTracker] recipe_provider är '{provider}' – receptförslag inaktiverat")
        return None


# Gratis-modeller på OpenRouter – provas i tur och ordning vid rate-limit (429)
_OPENROUTER_FREE_MODELS = [
    "meta-llama/llama-3.3-70b-instruct:free",
    "mistralai/mistral-small-3.1-24b-instruct:free",
    "google/gemma-3-27b-it:free",
    "meta-llama/llama-3.2-3b-instruct:free",
]

async def _call_openrouter(prompt, api_key):
    """Anropa OpenRouter med automatisk fallback till nästa modell vid rate-limit (429)."""
    import aiohttp
    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://www.home-assistant.io",
        "X-Title": "HA Grocery Tracker",
    }
    for model in _OPENROUTER_FREE_MODELS:
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 700,
            "temperature": 0.7,
        }
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload, headers=headers,
                                        timeout=aiohttp.ClientTimeout(total=30)) as resp:
                    if resp.status == 200:
                        data = await resp.json(content_type=None)
                        choices = data.get("choices") or []
                        content = choices[0].get("message", {}).get("content") if choices else None
                        if content:
                            log.info(f"[GroceryTracker] OpenRouter: svar från {model}")
                            return content.strip()
                        log.warning(f"[GroceryTracker] OpenRouter: tomt svar från {model}")
                    elif resp.status == 429:
                        log.info(f"[GroceryTracker] OpenRouter: {model} rate-limitad, provar nästa modell...")
                        continue
                    else:
                        body = await resp.text()
                        log.warning(f"[GroceryTracker] OpenRouter HTTP {resp.status} ({model}): {body[:200]}")
        except aiohttp.ServerTimeoutError:
            log.warning(f"[GroceryTracker] OpenRouter: timeout för {model}, provar nästa...")
            continue
        except Exception as e:
            log.warning(f"[GroceryTracker] OpenRouter-anrop misslyckades ({model}): {e}")
    log.warning("[GroceryTracker] OpenRouter: alla modeller rate-limitade eller misslyckades")
    return None


async def _call_openai_compatible(prompt, api_key, url, model, provider_name="LLM", extra_headers=None, timeout=20):
    """Anropa OpenAI-kompatibelt API (Groq, OpenRouter, Mistral, OpenAI m.fl.)."""
    import aiohttp
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    if extra_headers:
        headers.update(extra_headers)
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 700,
        "temperature": 0.7,
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, headers=headers,
                                    timeout=aiohttp.ClientTimeout(total=timeout)) as resp:
                if resp.status == 200:
                    data = await resp.json(content_type=None)
                    choices = data.get("choices") or []
                    content = choices[0].get("message", {}).get("content") if choices else None
                    if not content:
                        log.warning(f"[GroceryTracker] {provider_name}: tomt svar (content=null). Modell: {model}")
                        return None
                    return content.strip()
                body = await resp.text()
                log.warning(f"[GroceryTracker] {provider_name} HTTP {resp.status}: {body[:300]}")
    except aiohttp.ServerTimeoutError:
        log.warning(f"[GroceryTracker] {provider_name}: timeout efter {timeout}s (modell {model} kanske långsam)")
    except Exception as e:
        log.warning(f"[GroceryTracker] {provider_name}-anrop misslyckades: {e}")
    return None


# Gemini-modeller på v1beta – provas i tur och ordning vid rate-limit
# (rate-limit på 15 req/min är bara ett problem vid intensiv testning,
#  inte vid normal daglig användning på 1 receptförslag/dag)
_GEMINI_MODELS = [
    "gemini-2.0-flash",
    "gemini-2.0-flash-lite",
    "gemini-2.0-flash-001",
]

async def _call_gemini(prompt, api_key):
    import aiohttp
    if not api_key:
        log.warning("[GroceryTracker] Gemini: API-nyckel saknas")
        return None
    base = "https://generativelanguage.googleapis.com/v1beta/models"
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"maxOutputTokens": 700, "temperature": 0.7},
    }
    for model in _GEMINI_MODELS:
        url = f"{base}/{model}:generateContent?key={api_key}"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload,
                                        timeout=aiohttp.ClientTimeout(total=20)) as resp:
                    if resp.status == 200:
                        data = await resp.json(content_type=None)
                        candidates = data.get("candidates") or []
                        if candidates:
                            parts = candidates[0].get("content", {}).get("parts") or []
                            text = parts[0].get("text", "").strip() if parts else ""
                            if text:
                                log.info(f"[GroceryTracker] Gemini: svar från {model}")
                                return text
                        log.warning(f"[GroceryTracker] Gemini: tomt svar från {model}")
                    elif resp.status == 429:
                        body = await resp.text()
                        if "quota" in body.lower():
                            log.warning(f"[GroceryTracker] Gemini: dagkvoten slut för {model} (återställs vid midnatt). Provar nästa modell...")
                        else:
                            log.warning(f"[GroceryTracker] Gemini: rate-limit för {model}, provar nästa...")
                        continue
                    else:
                        body = await resp.text()
                        log.warning(f"[GroceryTracker] Gemini HTTP {resp.status} ({model}): {body[:200]}")
        except Exception as e:
            log.warning(f"[GroceryTracker] Gemini-anrop misslyckades ({model}): {e}")
    log.warning("[GroceryTracker] Gemini: alla modeller misslyckades – troligen dagkvot slut (återställs imorgon ~09:00 svensk tid) eller för snabb testning")
    return None


async def _call_anthropic(prompt, api_key):
    import aiohttp
    if not api_key:
        log.warning("[GroceryTracker] Anthropic: API-nyckel saknas")
        return None
    url = "https://api.anthropic.com/v1/messages"
    headers = {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }
    payload = {
        "model": "claude-haiku-4-5-20251001",
        "max_tokens": 700,
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
async def grocery_suggest_recipes(provider_override=None):
    """Hämta varor som snart går ut och skicka receptförslag via konfigurerad (eller angiven) LLM."""
    # Om provider_override är satt (från leverantörsknapp i dashboard) används den direkt
    # utan att kontrollera den konfigurerade providern
    effective_provider = provider_override or _sget("input_select.grocery_recipe_provider", "disabled")
    if not provider_override and effective_provider == "disabled":
        persistent_notification.create(
            title="👨‍🍳 Receptförslag inaktiverat",
            message="Välj en leverantör i Inställningar-fliken eller klicka en leverantörsknapp direkt.",
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

    await _do_suggest_recipes(candidates, provider_override=provider_override)


@service
async def grocery_clear_completed_shopping_list():
    """Ta bort alla inhandlade (bockade) varor från inköpslistan. Obockade varor behålls."""
    try:
        text = await task.executor(
            pathlib.Path(SHOPPING_LIST_FILE).read_text, encoding="utf-8"
        )
        raw = json.loads(text)
        completed = [i for i in raw if i.get("complete", False)]
    except Exception as e:
        log.warning(f"[GroceryTracker] Kunde inte läsa inköpslista: {e}")
        return

    if not completed:
        persistent_notification.create(
            title="🛒 Inköpslistan",
            message="Inga inhandlade varor att ta bort.",
            notification_id="grocery_shopping_done",
        )
        return

    for item in completed:
        name = item.get("name", "")
        if name:
            todo.remove_item(entity_id=SHOPPING_LIST_ENTITY, item=name)

    persistent_notification.create(
        title="🛒 Handlingen klar!",
        message=f"Tog bort {len(completed)} inhandlade varor. Kvarvarande obockade varor finns kvar.",
        notification_id="grocery_shopping_done",
    )
    log.info(f"[GroceryTracker] Rensade {len(completed)} inhandlade varor från inköpslistan")


# ─── Tibber Pulse – Matlagningssession ───────────────────────────────────────

@service
async def grocery_start_cooking():
    """Starta matlagningssession – läs av Tibber Pulse accumulated_consumption som startpunkt."""
    try:
        pulse_val = float(_sget(TIBBER_PULSE_CONSUMPTION, 0))
    except (ValueError, TypeError):
        pulse_val = 0

    input_number.set_value(entity_id="input_number.grocery_cooking_kwh_start", value=pulse_val)
    input_number.set_value(entity_id="input_number.grocery_actual_cooking_kwh", value=0)
    input_number.set_value(entity_id="input_number.grocery_actual_cooking_cost", value=0)
    input_boolean.turn_on(entity_id="input_boolean.grocery_cooking_active")

    persistent_notification.create(
        title="🍳 Matlagningssession startad",
        message=(
            f"Tibber Pulse-mätning startad (start: {pulse_val:.3f} kWh). "
            f"Tryck 'Klar' när du är färdig med matlagningen."
        ),
        notification_id="grocery_cooking_session",
    )
    log.info(f"[GroceryTracker] Matlagningssession startad. Tibber Pulse start: {pulse_val:.3f} kWh")


@service
async def grocery_stop_cooking():
    """Avsluta matlagningssession – beräkna faktisk förbrukning via Tibber Pulse."""
    input_boolean.turn_off(entity_id="input_boolean.grocery_cooking_active")

    try:
        kwh_end   = float(_sget(TIBBER_PULSE_CONSUMPTION, 0))
        kwh_start = float(_sget("input_number.grocery_cooking_kwh_start", 0))
    except (ValueError, TypeError):
        kwh_end = kwh_start = 0

    delta = round(kwh_end - kwh_start, 3)

    # Hantera midnatt-återstart (accumulated_consumption nollställs vid 00:00)
    if delta < 0:
        persistent_notification.create(
            title="⚠️ Matlagning – midnatt passerades",
            message=(
                "Sessionen passerade midnatt och Tibber Pulse nollställdes. "
                "Förbrukningen kan inte beräknas exakt för denna session."
            ),
            notification_id="grocery_cooking_session",
        )
        log.warning("[GroceryTracker] Matlagningssession: delta < 0 (midnatt), avbryter mätning")
        return

    try:
        _price = float(_sget("sensor.dammtorpsgatan_22_current_electricity_price", 0))
    except (ValueError, TypeError):
        _price = 0

    actual_cost = round(delta * _price, 2)
    input_number.set_value(entity_id="input_number.grocery_actual_cooking_kwh", value=delta)
    input_number.set_value(entity_id="input_number.grocery_actual_cooking_cost", value=actual_cost)

    persistent_notification.create(
        title="✅ Matlagning klar!",
        message=(
            f"Förbrukning: {delta} kWh · Kostnad: {actual_cost} kr "
            f"(elpris {_price:.2f} kr/kWh)\n"
            f"Obs: inkluderar ALL förbrukning i hemmet under matlagningen."
        ),
        notification_id="grocery_cooking_session",
    )
    log.info(
        f"[GroceryTracker] Matlagningssession klar. "
        f"Delta: {delta} kWh, Kostnad: {actual_cost} kr (elpris {_price:.2f} kr/kWh)"
    )


# ─── Startup ─────────────────────────────────────────────────────────────────

@time_trigger("startup")
async def _startup():
    inventory = await _load_inventory()
    await _refresh_sensors(inventory)
    # Initiera recept-sensor (pyscript-states är transient – finns aldrig vid omstart)
    state.set("sensor.grocery_last_recipe", "Inget receptförslag ännu", {
        "recipe": "",
        "ingredients": "",
        "cooking_minutes": None,
        "cooking_appliance": None,
        "cooking_kwh": None,
        "cooking_cost_kr": None,
        "electricity_price": None,
        "friendly_name": "Senaste receptförslag",
    })
    log.info("[GroceryTracker] Grocery Tracker v1.9 startad.")
