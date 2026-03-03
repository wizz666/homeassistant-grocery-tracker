"""
Grocery Offers – Matpriskollen butiksintegration  v1.0
======================================================
Hämtar veckans erbjudanden från matpriskollen.se för konfigurerade butiker
och matchar dem mot din inköpslista.

Services:
  pyscript.grocery_refresh_offers()              – Uppdatera erbjudanden manuellt
  pyscript.grocery_find_stores(lat, lon, radius) – Hitta butiker nära en plats
  pyscript.grocery_find_stores(search="willys")  – Sök butiker på namn

Konfiguration:
  input_text.grocery_store_uuids    – UUIDs för valda butiker (kommaseparerade)
  input_boolean.grocery_offers_enabled – Aktivera/inaktivera modulen

Hur du hittar en butiks UUID:
  1. Gå till matpriskollen.se och välj din butik
  2. UUID är den sista delen av URL:en, t.ex.:
     /butiker/willys-alingsas--866b8a99-00fe-4157-9f4c-9128a652ddbe
     → UUID = 866b8a99-00fe-4157-9f4c-9128a652ddbe
  3. Eller anropa grocery_find_stores(search="willys") och kopiera UUID ur notisen
"""

import json
import pathlib

OFFERS_API = "https://matpriskollen.se/api/v1/stores"
SHOPPING_LIST_FILE = "/config/.shopping_list.json"

# Modul-nivå cache: uuid → {name, chain, offers: [...], fetched_at}
_offers_cache = {}

# ─── Helpers ──────────────────────────────────────────────────────────────────

def _sget(entity_id, default=None):
    try:
        val = state.get(entity_id)
        return val if val is not None else default
    except Exception:
        return default

def _sbool(entity_id):
    return _sget(entity_id, "off").lower() in ("on", "true", "1", "yes")

def _get_configured_uuids():
    """Returnerar lista med konfigurerade butiks-UUIDs."""
    raw = _sget("input_text.grocery_store_uuids", "").strip()
    if not raw or raw in ("unknown", "unavailable", "none"):
        return []
    return [u.strip() for u in raw.split(",") if u.strip() and len(u.strip()) > 10]

# ─── API-anrop ────────────────────────────────────────────────────────────────

async def _fetch_store_info(uuid):
    """Hämta butiksinformation från Matpriskollen JSON API."""
    import aiohttp
    try:
        headers = {
            "Accept": "application/json",
            "User-Agent": "Mozilla/5.0 (compatible; HomeAssistant)",
        }
        async with aiohttp.ClientSession() as sess:
            async with sess.get(
                f"{OFFERS_API}/{uuid}",
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status == 200:
                    return await resp.json(content_type=None)
                log.warning(f"[GroceryOffers] Butiksinfo HTTP {resp.status} för {uuid[:8]}...")
    except Exception as e:
        log.warning(f"[GroceryOffers] Butiksinfo-fel {uuid[:8]}...: {e}")
    return None


async def _fetch_store_offers(uuid):
    """Hämta erbjudanden för en butik."""
    import aiohttp
    try:
        headers = {
            "Accept": "application/json",
            "User-Agent": "Mozilla/5.0 (compatible; HomeAssistant)",
        }
        async with aiohttp.ClientSession() as sess:
            async with sess.get(
                f"{OFFERS_API}/{uuid}/offers",
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                if resp.status == 200:
                    data = await resp.json(content_type=None)
                    return data.get("offers", [])
                log.warning(f"[GroceryOffers] Offers HTTP {resp.status} för {uuid[:8]}...")
    except Exception as e:
        log.warning(f"[GroceryOffers] Offers-fel {uuid[:8]}...: {e}")
    return []

# ─── Matchning mot inköpslista ────────────────────────────────────────────────

def _normalize(text):
    """Normalisera text för jämförelse – lowercase, inga diakritiska tecken."""
    if not text:
        return ""
    import unicodedata
    text = str(text).lower().strip()
    text = unicodedata.normalize("NFD", text)
    return "".join([c for c in text if unicodedata.category(c) != "Mn"])


async def _get_shopping_list_items():
    """Läs aktiva items från inköpslistan (samma mönster som grocery_tracker.py)."""
    try:
        text = await task.executor(
            pathlib.Path(SHOPPING_LIST_FILE).read_text, encoding="utf-8"
        )
        items = json.loads(text)
        result = [i for i in items if not i.get("complete", False)]
        log.debug(f"[GroceryOffers] Inköpslista: {len(result)} aktiva items")
        return result
    except Exception as e:
        log.warning(f"[GroceryOffers] Kunde inte läsa inköpslista: {e}")
        return []


def _extract_keywords(text):
    """Extrahera sökbara nyckelord ur ett varunamn (min 3 tecken, ej siffror)."""
    norm = _normalize(text)
    words = []
    current = ""
    for c in norm:
        if c.isalnum():
            current += c
        else:
            if current and len(current) >= 3 and not current.isdigit():
                words.append(current)
            current = ""
    if current and len(current) >= 3 and not current.isdigit():
        words.append(current)
    return words


# Generiska svenska adjektiv/deskriptorer — filtreras bort, de är för otydliga
_SKIP_WORDS = {
    "farsk", "fryst", "torkat", "rokt", "grillad", "kokt", "stekt", "malet",
    "skivat", "hel", "halv", "krossad", "passerad", "eko", "krav", "svensk",
    "god", "stor", "liten", "smak",
}

# Prefix i sammansatta ord som fundamentalt ändrar produkttypen — suffix-match
# avvisas om produktordet börjar med något av dessa:
#   Djurfoder:          kattmjolk ≠ mjolk,  hundfoder ≠ foder
#   Växtbaserat:        kokosmjolk ≠ mjolk, havremjolk ≠ mjolk
_COMPOUND_TYPE_PREFIXES = {
    # Djur
    "katt", "hund", "kanin", "hamster", "fagel", "papegoj", "marsvin",
    # Växtbaserade mjölkalternativ
    "kokos", "mandel", "havre", "soja", "ris", "cashew",
}

# Fristående ord som fundamentalt ändrar produkttypen:
# om dessa finns i produktnamnet men EJ bland inköpslistans nyckelord → avvisa.
# Exempel: "Mjölk" på listan ska EJ matcha "Kondenserad Mjölk" (konserv, ej dryck).
_STANDALONE_DISQUALIFIERS = {
    "kondenserad", "evaporerad",
}


def _match_item_to_offers(item_name, all_offers):
    """Hitta erbjudanden som matchar ett inköpslista-item.

    - Filtrerar generiska deskriptorer (farsk, fryst, eko…) ur nyckelorden
    - Krav: ALLA återstående nyckelord måste matchas (AND-logik)
    - Varje nyckelord matchas som exakt ord, prefix ELLER suffix i ett sökt ord
      (hanterar svenska sammansatta ord: babyspenat↔spenat, hönsägg↔ägg)
    """
    all_kw = _extract_keywords(item_name)
    if not all_kw:
        return []
    # Ta bort generiska deskriptorer om det finns mer specifika kvar
    filtered = [kw for kw in all_kw if kw not in _SKIP_WORDS]
    keywords = filtered if filtered else all_kw

    matches = []
    for offer in all_offers:
        prod       = offer.get("product", {})
        prod_name  = _normalize(prod.get("name", ""))
        brand      = _normalize(prod.get("brand", ""))
        # Extrahera ord ur produktnamn + varumärke (hanterar sammansatta ord)
        search_words = _extract_keywords(prod_name + " " + brand)

        # AND-logik: alla nyckelord måste hittas som exakt/prefix/suffix
        all_match = True
        for kw in keywords:
            found = False
            for sw in search_words:
                if sw == kw or sw.startswith(kw):
                    found = True
                    break
                # Suffix-match: babyspenat↔spenat — men EJ om prefixet ändrar typ
                # (kattmjolk→"katt", kokosmjolk→"kokos" ∈ _COMPOUND_TYPE_PREFIXES → avvisa)
                if sw.endswith(kw) and len(sw) > len(kw):
                    prefix = sw[:-len(kw)]
                    if prefix not in _COMPOUND_TYPE_PREFIXES:
                        found = True
                        break
            if not found:
                all_match = False
                break

        # Extra: fristående typändrande ord i produktnamnet men EJ i listans nyckelord
        # "Mjölk" → keywords={"mjolk"} — produkt "Kondenserad Mjölk" har "kondenserad"
        # som inte finns bland keywords → avvisa (det är konserv, inte dryck)
        if all_match:
            kw_set = set(keywords)
            for dq in _STANDALONE_DISQUALIFIERS:
                if dq in search_words and dq not in kw_set:
                    all_match = False
                    break

        if all_match:
            cats = prod.get("categories", [])
            cat  = cats[0].get("name", "") if cats else ""
            matches.append({
                "product":    prod.get("name", ""),
                "brand":      prod.get("brand", ""),
                "price":      offer.get("price", ""),
                "comprice":   offer.get("comprice", ""),
                "volume":     offer.get("volume", ""),
                "store_name": offer.get("_store_name", ""),
                "category":   cat,
                "image":      (offer.get("produkt_bild_urls") or {}).get("thumbnailUrl", ""),
            })
    return matches


def _build_per_store_data():
    """Bygg per-butik offerdata för butiksvy i dashboarden."""
    result = {}
    for uuid, cache_entry in _offers_cache.items():
        store_name = cache_entry.get("name", uuid[:8])
        offers_data = []
        for o in cache_entry.get("offers", []):
            prod = o.get("product", {})
            cats = prod.get("categories", [])
            if cats:
                parent = cats[0].get("parent_category") or {}
                cat_name = parent.get("name") or cats[0].get("name") or "Övrigt"
            else:
                cat_name = "Övrigt"
            offers_data.append({
                "n": prod.get("name", ""),
                "b": prod.get("brand", ""),
                "p": o.get("price", ""),
                "c": cat_name,
            })
        result[store_name] = offers_data
    return result


def _build_category_data():
    """Bygg kategoriserad offerdata från cache (för sensor-attribut)."""
    cat_map = {}
    for uuid, cache_entry in _offers_cache.items():
        store_name = cache_entry.get("name", "?")
        for offer in cache_entry.get("offers", []):
            prod = offer.get("product", {})
            cats = prod.get("categories", [])
            if cats:
                parent = cats[0].get("parent_category") or {}
                cat_name = parent.get("name") or cats[0].get("name") or "Övrigt"
            else:
                cat_name = "Övrigt"
            if cat_name not in cat_map:
                cat_map[cat_name] = []
            cat_map[cat_name].append({
                "n": prod.get("name", ""),
                "b": prod.get("brand", ""),
                "p": offer.get("price", ""),
                "s": store_name,
            })
    result = []
    for name, offers in sorted(cat_map.items(), key=lambda x: -len(x[1])):
        result.append({"name": name, "count": len(offers), "offers": offers[:5]})
    return result[:12]

# ─── Uppdatera sensorer ───────────────────────────────────────────────────────

def _update_count_sensor():
    """Uppdatera sensor.grocery_offers_count och grocery_configured_picker."""
    from datetime import datetime
    total = sum([len(v.get("offers", [])) for v in _offers_cache.values()])
    stores_summary = [
        {
            "uuid":        uuid,
            "name":        v.get("name", uuid[:8]),
            "chain":       v.get("chain", ""),
            "offer_count": len(v.get("offers", [])),
            "fetched_at":  v.get("fetched_at", ""),
        }
        for uuid, v in _offers_cache.items()
    ]
    # namn → uuid-mapping för remove-service
    name_to_uuid = {v.get("name", uuid[:8]): uuid for uuid, v in _offers_cache.items()}

    state.set("sensor.grocery_offers_count", total, {
        "friendly_name": "Grocery – Erbjudanden totalt",
        "icon":          "mdi:tag-multiple",
        "stores":        stores_summary,
        "store_count":   len(stores_summary),
        "last_update":   datetime.now().strftime("%Y-%m-%d %H:%M"),
        "name_to_uuid":  name_to_uuid,
    })
    # Stora data i eget sensor för att hålla grocery_offers_count under 16KB
    state.set("sensor.grocery_offers_detail", total, {
        "friendly_name": "Grocery – Erbjudandedetaljer",
        "icon":          "mdi:tag-multiple",
        "categories":        _build_category_data(),
        "per_store_offers":  _build_per_store_data(),
    })

    # Uppdatera dropdown för remove
    # Notera: placeholder ingår alltid i options-listan för att undvika "no longer valid"-varningar.
    if stores_summary:
        store_options = [f"{s['name']} ({s['offer_count']} reas)" for s in stores_summary]
        all_options = ["– Inga butiker konfigurerade –"] + store_options
        input_select.set_options(
            entity_id="input_select.grocery_configured_picker",
            options=all_options,
        )
        input_select.select_option(
            entity_id="input_select.grocery_configured_picker",
            option=store_options[0],
        )
    else:
        input_select.set_options(
            entity_id="input_select.grocery_configured_picker",
            options=["– Inga butiker konfigurerade –"],
        )


async def _update_match_sensor():
    """Matcha inköpslistan mot erbjudanden och uppdatera sensor."""
    shopping_items = await _get_shopping_list_items()

    # Samla alla erbjudanden med butiksnamn injekterat
    all_offers = []
    for uuid, cache_entry in _offers_cache.items():
        for offer in cache_entry.get("offers", []):
            offer["_store_name"] = cache_entry.get("name", uuid[:8])
            all_offers.append(offer)

    matched = []
    for item in shopping_items:
        item_name = item.get("summary", item.get("name", ""))
        if not item_name:
            continue
        offers_for_item = _match_item_to_offers(item_name, all_offers)
        if offers_for_item:
            matched.append({
                "item":   item_name,
                "offers": offers_for_item,
            })

    state.set("sensor.grocery_offers_matches", len(matched), {
        "friendly_name":          "Grocery – Reas som matchar inköpslistan",
        "icon":                   "mdi:tag-check",
        "matched_items":          matched,
        "shopping_items_checked": len(shopping_items),
    })
    return matched

# ─── Refresh-logik ────────────────────────────────────────────────────────────

async def _do_refresh():
    """Hämta erbjudanden för alla konfigurerade butiker och uppdatera sensorer."""
    uuids = _get_configured_uuids()

    if not uuids:
        log.info("[GroceryOffers] Inga butiker konfigurerade. Lägg UUID i input_text.grocery_store_uuids")
        state.set("sensor.grocery_offers_count", 0, {
            "friendly_name": "Grocery – Erbjudanden totalt",
            "icon":          "mdi:tag-multiple",
            "stores":        [],
            "store_count":   0,
            "last_update":   "–",
            "hint":          "Konfigurera butiker under Erbjudanden → Inställningar",
        })
        return

    from datetime import datetime
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")

    log.info(f"[GroceryOffers] Hämtar erbjudanden för {len(uuids)} butik(er)...")

    for uuid in uuids:
        try:
            info = await _fetch_store_info(uuid)
            if not info:
                log.warning(f"[GroceryOffers] Hittade inte butik: {uuid[:8]}...")
                continue

            store_name = info.get("name", uuid[:8])
            chain_name = info.get("chainName", "")
            offers     = await _fetch_store_offers(uuid)

            _offers_cache[uuid] = {
                "name":       store_name,
                "chain":      chain_name,
                "offers":     offers,
                "fetched_at": ts,
            }
            log.info(f"[GroceryOffers] {store_name}: {len(offers)} erbjudanden")

        except Exception as e:
            log.error(f"[GroceryOffers] Fel vid hämtning för {uuid[:8]}...: {e}")

    _update_count_sensor()
    matched = await _update_match_sensor()

    # Notis om inköpslista-träffar
    if matched:
        lines = []
        for m in matched[:6]:
            best = m["offers"][0]
            lines.append(f"• **{m['item']}** – {best['product']} {best['price']} ({best['store_name']})")
        suffix = f"\n_...och {len(matched) - 6} till_" if len(matched) > 6 else ""
        persistent_notification.create(
            title=f"🏷️ {len(matched)} varor på rea!",
            message="\n".join(lines) + suffix,
            notification_id="grocery_offers_match",
        )

    total = sum([len(v.get("offers", [])) for v in _offers_cache.values()])
    log.info(f"[GroceryOffers] Klar. {total} erbjudanden totalt, {len(matched)} matchar inköpslistan.")

# ─── Services ─────────────────────────────────────────────────────────────────

@service
async def grocery_refresh_offers():
    """Uppdatera erbjudanden manuellt från matpriskollen.se."""
    if not _sbool("input_boolean.grocery_offers_enabled"):
        persistent_notification.create(
            title="Grocery Offers",
            message="Modulen är inaktiverad. Aktivera under Erbjudanden → Inställningar.",
            notification_id="grocery_offers_disabled",
        )
        return
    await _do_refresh()


@service
async def grocery_find_stores(lat=None, lon=None, radius=25, search=None):
    """
    Hitta butiker på matpriskollen.se nära en koordinat eller sök på namn.

    Parametrar:
      search    – Sök på butiksnamn, t.ex. "willys" eller "ica maxi"
      lat, lon  – Koordinater (används om search saknas)
      radius    – Sökradius i km (standard 25 km)

    Resultatet visas som push-notis och sparas i sensor.grocery_found_stores.
    UUID:n i notisen klistrar du in i input_text.grocery_store_uuids.
    """
    import aiohttp
    try:
        headers = {
            "Accept":     "application/json",
            "User-Agent": "Mozilla/5.0 (compatible; HomeAssistant)",
        }
        if search:
            url = f"{OFFERS_API}/search?q={search}"
        elif lat and lon:
            url = f"{OFFERS_API}?lat={lat}&lon={lon}&radius={radius}"
        else:
            persistent_notification.create(
                title="Grocery Butikssök",
                message="Ange antingen search='butiknamn' eller lat+lon som parametrar.",
                notification_id="grocery_find_stores",
            )
            return

        async with aiohttp.ClientSession() as sess:
            async with sess.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status != 200:
                    log.warning(f"[GroceryOffers] find_stores HTTP {resp.status}")
                    return
                stores_raw = await resp.json(content_type=None)

        stores_raw = stores_raw if isinstance(stores_raw, list) else []
        result = [
            {
                "uuid":       s.get("key", ""),
                "name":       s.get("name", ""),
                "chain":      s.get("chainName", s.get("chain", "")),
                "city":       s.get("city", ""),
                "address":    s.get("address", ""),
                "offer_count": s.get("offerCount", 0),
                "distance_m": s.get("dist", ""),
            }
            for s in stores_raw
        ]

        # namn → uuid-mapping för add-service
        name_to_uuid = {s["name"]: s["uuid"] for s in result if s["uuid"]}

        state.set("sensor.grocery_found_stores", len(result), {
            "friendly_name": "Grocery – Hittade butiker",
            "icon":          "mdi:store-search",
            "stores":        result,
            "search_query":  search or f"{lat},{lon} r={radius}km",
            "name_to_uuid":  name_to_uuid,
        })

        # Populera dropdown-väljaren med sökresultaten
        if result:
            already = _get_configured_uuids()
            options = []
            for s in result[:15]:
                dist   = f" · {float(s['distance_m']):.1f} km" if s["distance_m"] else ""
                added  = " ✓" if s["uuid"] in already else ""
                options.append(f"{s['name']} ({s['offer_count']} reas{dist}){added}")
            # Behåll placeholder som option 0 — undviker "no longer valid"-varningar
            all_picker_options = ["– Sök butiker ovan –"] + options
            input_select.set_options(
                entity_id="input_select.grocery_store_picker",
                options=all_picker_options,
            )
            input_select.select_option(
                entity_id="input_select.grocery_store_picker",
                option=options[0],
            )
            log.info(f"[GroceryOffers] Hittade {len(result)} butiker för '{search or f'{lat},{lon}'}'")
        else:
            input_select.set_options(
                entity_id="input_select.grocery_store_picker",
                options=["– Inga butiker hittades –"],
            )
            log.info("[GroceryOffers] Inga butiker hittades")

    except Exception as e:
        log.error(f"[GroceryOffers] find_stores-fel: {e}")

@service
async def grocery_search_stores():
    """Sök butiker baserat på input_text.grocery_store_search_query."""
    query = _sget("input_text.grocery_store_search_query", "").strip()
    if not query:
        # Fallback: sök nära hemmet
        lat = state.get("zone.home.latitude")
        lon = state.get("zone.home.longitude")
        if lat and lon:
            await grocery_find_stores(lat=float(lat), lon=float(lon), radius=25)
        return
    await grocery_find_stores(search=query)


@service
async def grocery_add_selected_store():
    """Lägg till vald butik från input_select.grocery_store_picker i konfigurerade butiker."""
    selected = _sget("input_select.grocery_store_picker", "").strip()
    if not selected or selected.startswith("–"):
        log.warning("[GroceryOffers] Ingen butik vald i picker")
        return

    # Extrahera butiksnamn (allt före " (")
    store_name = selected.split(" (")[0].strip().rstrip(" ✓")

    # Slå upp UUID från sensor-attribut
    name_to_uuid = state.get("sensor.grocery_found_stores") and \
                   (state.getattr("sensor.grocery_found_stores") or {}).get("name_to_uuid", {})
    uuid = (name_to_uuid or {}).get(store_name, "")

    if not uuid:
        log.warning(f"[GroceryOffers] Kunde inte hitta UUID för '{store_name}' – sök igen")
        return

    # Lägg till om den inte redan finns
    current = _sget("input_text.grocery_store_uuids", "").strip()
    existing = [u.strip() for u in current.split(",") if u.strip()]
    already_configured = uuid in existing

    if not already_configured:
        existing.append(uuid)
        new_val = ",".join(existing)
        input_text.set_value(entity_id="input_text.grocery_store_uuids", value=new_val)
        log.info(f"[GroceryOffers] Lade till: {store_name} ({uuid[:8]}...)")

    # Hämta erbjudanden (alltid — säkerställer att cachen är uppdaterad)
    if _sbool("input_boolean.grocery_offers_enabled"):
        try:
            info   = await _fetch_store_info(uuid)
            offers = await _fetch_store_offers(uuid)
            from datetime import datetime
            _offers_cache[uuid] = {
                "name":       info.get("name", store_name) if info else store_name,
                "chain":      info.get("chainName", "") if info else "",
                "offers":     offers,
                "fetched_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
            }
            _update_count_sensor()
            await _update_match_sensor()
            if already_configured:
                msg = f"{store_name} var redan tillagd — erbjudanden uppdaterade ({len(offers)} reas)."
            else:
                msg = f"{store_name} tillagd med {len(offers)} erbjudanden! 🏷️"
            persistent_notification.create(
                title="Grocery – Butik tillagd",
                message=msg,
                notification_id="grocery_store_added",
            )
            log.info(f"[GroceryOffers] {store_name}: {len(offers)} erbjudanden")
        except Exception as e:
            log.error(f"[GroceryOffers] Fel vid hämtning för {store_name}: {e}")
            persistent_notification.create(
                title="Grocery – Fel vid tillägg",
                message=f"Kunde inte hämta erbjudanden för {store_name}. Försök med Uppdatera-knappen.",
                notification_id="grocery_store_added",
            )
    else:
        if not already_configured:
            persistent_notification.create(
                title="Grocery – Butik tillagd",
                message=f"{store_name} tillagd. Aktivera erbjudanden och klicka Uppdatera för att se reas.",
                notification_id="grocery_store_added",
            )


@service
async def grocery_add_store_by_index(store_index=0):
    """Lägg till hittad butik via index – tap-to-add utan dropdown."""
    stores = (state.getattr("sensor.grocery_found_stores") or {}).get("stores", [])
    try:
        idx = int(store_index)
    except (ValueError, TypeError):
        idx = -1
    if not (0 <= idx < len(stores)):
        log.warning(f"[GroceryOffers] Ogiltigt hittad-butiksindex: {idx}")
        return
    store = stores[idx]
    uuid = store.get("uuid", "")
    store_name = store.get("name", f"Butik {idx}")
    if not uuid:
        log.warning(f"[GroceryOffers] Inget UUID för hittad butik index {idx}")
        return

    existing = _get_configured_uuids()
    already_configured = uuid in existing
    if not already_configured:
        existing.append(uuid)
        input_text.set_value(
            entity_id="input_text.grocery_store_uuids",
            value=",".join(existing),
        )
        log.info(f"[GroceryOffers] Lade till: {store_name} ({uuid[:8]}...)")

    if _sbool("input_boolean.grocery_offers_enabled"):
        try:
            info   = await _fetch_store_info(uuid)
            offers = await _fetch_store_offers(uuid)
            from datetime import datetime
            _offers_cache[uuid] = {
                "name":       info.get("name", store_name) if info else store_name,
                "chain":      info.get("chainName", "") if info else "",
                "offers":     offers,
                "fetched_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
            }
            _update_count_sensor()
            await _update_match_sensor()
            if already_configured:
                msg = f"{store_name} var redan tillagd — erbjudanden uppdaterade ({len(offers)} reas)."
            else:
                msg = f"{store_name} tillagd med {len(offers)} erbjudanden! 🏷️"
            persistent_notification.create(
                title="Grocery – Butik tillagd",
                message=msg,
                notification_id="grocery_store_added",
            )
        except Exception as e:
            log.error(f"[GroceryOffers] Fel vid hämtning för {store_name}: {e}")
            persistent_notification.create(
                title="Grocery – Fel vid tillägg",
                message=f"Kunde inte hämta erbjudanden för {store_name}.",
                notification_id="grocery_store_added",
            )
    else:
        if not already_configured:
            persistent_notification.create(
                title="Grocery – Butik tillagd",
                message=f"{store_name} tillagd. Aktivera erbjudanden och klicka Uppdatera.",
                notification_id="grocery_store_added",
            )


@service
async def grocery_remove_store_by_index(store_index=0):
    """Ta bort konfigurerad butik via index – direkt från butiksrad i dashboarden."""
    attrs = state.getattr("sensor.grocery_offers_count") or {}
    stores = attrs.get("stores", [])
    try:
        idx = int(store_index)
    except (ValueError, TypeError):
        idx = -1
    if not (0 <= idx < len(stores)):
        log.warning(f"[GroceryOffers] Ogiltigt konfig-butiksindex: {idx}")
        return

    uuid = stores[idx].get("uuid", "")
    store_name = stores[idx].get("name", f"Butik {idx}")
    if not uuid:
        log.warning(f"[GroceryOffers] Inget UUID för konfig-butik index {idx}")
        return

    # Ta bort från konfigurerade listan
    current = _sget("input_text.grocery_store_uuids", "").strip()
    existing = [u.strip() for u in current.split(",") if u.strip() and u.strip() != uuid]
    input_text.set_value(entity_id="input_text.grocery_store_uuids", value=",".join(existing))

    # Ta bort från cache och uppdatera sensorer
    if uuid in _offers_cache:
        del _offers_cache[uuid]
    _update_count_sensor()
    await _update_match_sensor()
    log.info(f"[GroceryOffers] Tog bort: {store_name}")


async def grocery_remove_selected_store():
    """Ta bort vald butik från input_select.grocery_configured_picker."""
    selected = _sget("input_select.grocery_configured_picker", "").strip()
    if not selected or selected.startswith("–"):
        log.warning("[GroceryOffers] Ingen butik vald för borttagning")
        return

    # Extrahera butiksnamn (allt före " (")
    store_name = selected.split(" (")[0].strip()

    # Slå upp UUID direkt från in-memory cache (undviker 16KB-gränsen på sensor-attribut)
    # OBS: generator expression stöds ej i pyscript → använd loop
    uuid = ""
    for uid, v in _offers_cache.items():
        if v.get("name", uid[:8]) == store_name:
            uuid = uid
            break
    if not uuid:
        # Fallback: leta i input_text.grocery_store_uuids via name_to_uuid i sensorattribut
        attrs = state.getattr("sensor.grocery_offers_count") or {}
        uuid = (attrs.get("name_to_uuid") or {}).get(store_name, "")

    if not uuid:
        log.warning(f"[GroceryOffers] Kunde inte hitta UUID för '{store_name}' (cache: {list(_offers_cache.keys())})")
        return

    # Ta bort från konfigurerade listan
    current  = _sget("input_text.grocery_store_uuids", "").strip()
    existing = [u.strip() for u in current.split(",") if u.strip() and u.strip() != uuid]
    input_text.set_value(entity_id="input_text.grocery_store_uuids", value=",".join(existing))

    # Ta bort från cache och uppdatera sensorer
    if uuid in _offers_cache:
        del _offers_cache[uuid]
    _update_count_sensor()
    await _update_match_sensor()
    log.info(f"[GroceryOffers] Tog bort: {store_name}")


# ─── Schemalagd refresh ───────────────────────────────────────────────────────

@time_trigger("cron(0 6 * * *)")
async def _refresh_morning():
    """Uppdatera erbjudanden kl 06:00 (nya veckans erbjudanden måndag)."""
    if _sbool("input_boolean.grocery_offers_enabled") and _get_configured_uuids():
        await _do_refresh()

@time_trigger("cron(0 12 * * *)")
async def _refresh_noon():
    """Uppdatera erbjudanden kl 12:00 (mellanskift)."""
    if _sbool("input_boolean.grocery_offers_enabled") and _get_configured_uuids():
        await _do_refresh()

# ─── Startup ──────────────────────────────────────────────────────────────────

@time_trigger("startup")
async def _startup():
    """Initiera sensorer och hämta erbjudanden direkt om aktiverat."""
    state.set("sensor.grocery_offers_count", 0, {
        "friendly_name": "Grocery – Erbjudanden totalt",
        "icon":          "mdi:tag-multiple",
        "stores":        [],
        "store_count":   0,
        "last_update":   "–",
        "name_to_uuid":  {},
    })
    state.set("sensor.grocery_offers_detail", 0, {
        "friendly_name":    "Grocery – Erbjudandedetaljer",
        "icon":             "mdi:tag-multiple",
        "categories":       [],
        "per_store_offers": {},
    })
    state.set("sensor.grocery_offers_matches", 0, {
        "friendly_name":          "Grocery – Reas som matchar inköpslistan",
        "icon":                   "mdi:tag-check",
        "matched_items":          [],
        "shopping_items_checked": 0,
    })
    state.set("sensor.grocery_found_stores", 0, {
        "friendly_name": "Grocery – Hittade butiker",
        "icon":          "mdi:store-search",
        "stores":        [],
        "search_query":  "",
        "name_to_uuid":  {},
    })

    # Initiera pickers vid start
    try:
        input_select.set_options(
            entity_id="input_select.grocery_store_picker",
            options=["– Sök butiker ovan –"],
        )
        input_select.set_options(
            entity_id="input_select.grocery_configured_picker",
            options=["– Inga butiker konfigurerade –"],
        )
    except Exception as e:
        log.warning(f"[GroceryOffers] Kunde inte initiera pickers: {e}")

    log.info("[GroceryOffers] v1.0 startad.")

    if _sbool("input_boolean.grocery_offers_enabled") and _get_configured_uuids():
        await _do_refresh()


# ─── Butiksvy – sätts från dashboard ─────────────────────────────────────────

@service
async def grocery_view_store(store_index=0):
    """Aktivera butiksvy för vald butik i Erbjudanden-dashboarden.

    Args:
        store_index: Index i listan (0 = första butiken, -1 = rensa vyn)
    """
    stores = list(_offers_cache.items())
    try:
        idx = int(store_index)
    except (ValueError, TypeError):
        idx = -1

    if 0 <= idx < len(stores):
        uuid, cache_entry = stores[idx]
        store_name = cache_entry.get("name", uuid[:8])
        input_text.set_value(
            entity_id="input_text.grocery_view_store",
            value=store_name,
        )
        log.debug(f"[GroceryOffers] Butiksvy: {store_name}")
    else:
        input_text.set_value(
            entity_id="input_text.grocery_view_store",
            value="",
        )
