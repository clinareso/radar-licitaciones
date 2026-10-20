"""Recolector diario de licitaciones de educación, capacitación y e-learning.

Fuentes: Mercado Público (Chile), TED (Unión Europea), Banco Mundial, PNUD y UNGM (ONU),
más los avisos curados a mano en seed.json (BID, ADB, AfDB y otros sin API pública).
Escribe data.json, que el dashboard publica tal cual.

Uso:  python collector.py
Solo usa la biblioteca estándar de Python 3.9+.
"""
import concurrent.futures as cf
import datetime as dt
import html
import http.cookiejar
import json
import os
import re
import sys
import unicodedata
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "data.json")
STATE = os.path.join(HERE, "state.json")
SEED = os.path.join(HERE, "seed.json")
TODAY = dt.date.today()
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) radar-licitaciones/1.0"}


def log(*a):
    print(*a, file=sys.stderr, flush=True)


def norm(s):
    s = unicodedata.normalize("NFD", s or "")
    return "".join(c for c in s if unicodedata.category(c) != "Mn").lower()


def clean(s):
    s = re.sub(r"<[^>]+>", " ", s or "")
    return re.sub(r"\s+", " ", html.unescape(s)).strip()


def make_opener():
    return urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))


def fetch(url, data=None, headers=None, opener=None, timeout=60, encoding=None):
    h = dict(UA)
    h.update(headers or {})
    if isinstance(data, (dict, list)):
        data = json.dumps(data).encode()
        h.setdefault("Content-Type", "application/json")
    req = urllib.request.Request(url, data=data, headers=h)
    with (opener or urllib.request.build_opener()).open(req, timeout=timeout) as r:
        raw = r.read()
        cs = encoding or r.headers.get_content_charset() or "utf-8"
    try:
        return raw.decode(cs)
    except UnicodeDecodeError:
        return raw.decode("cp1252", errors="replace")


# ---------------------------------------------------------------- relevance rules
TRAINING = re.compile(
    r"capacitac|\bcursos?\b|diplomad|relator|e-?learning|b-?learning|m-?learning|acciones formativas"
    r"|formacion (de|en|para|y|continua|profesional|docente|tecnica)|perfeccionamiento|seminario|coaching"
    r"|plataforma (de aprendizaje|e-learning|lms|educativa|de capacitacion|integral de capacitacion)"
    r"|\blms\b|moodle|talleres? (para|de) (docentes|funcionari|formacion|oficio|capacitacion)|talleres de oficio"
    r"|educacion continua|virtualizacion|bootcamp|otec\b"
    r"|training|capacity.?building|e-?learning|learning (management|platform)|teacher|tvet|vocational|upskilling|reskilling"
    r"|skills (development|training)|digital skills|coding|curriculum|course|workshop"
    r"|formation|renforcement des capacites|formateurs|apprentissage"
    r"|capacitacao|treinamento|formacao|curso|ead\b|ensino a distancia"
    r"|schulung|weiterbildung|fortbildung|qualifizierung|lernplattform|opleiding|leeromgeving|utbildning|larplattform|formazione"
)
EXCLUDE = re.compile(
    r"suministro de (materiales|insumos|repuestos|bajadas)|adquisicion de (materiales|insumos|equipos|mobiliario|repuestos|fierros|tablets|pantallas|tarima|espejos|cinturon)"
    r"|repuestos|farmacos|construccion|mantencion|reparacion|arriendo|fachada|vestuario|carpas|oxigeno|alimento|servidores"
    r"|licenciamiento|web hosting|reloj control|call center|fotovoltaic|estudio de terreno|celebracion|coctel"
    r"|furniture|vehicle|construction of|rehabilitation of|supply and installation|printing|catering|fuel|medical equipment"
    r"|venue|accommodation|hotel|conference package|hebergement|restauration|alojamiento|coffee"
)
DIGITAL = re.compile(
    r"e-?learning|b-?learning|m-?learning|plataforma|virtual|online|en linea|digital|inteligencia artificial|\bia\b|\bai\b"
    r"|programacion|coding|excel|office 365|microsoft|\blms\b|moodle|software|ciberseguridad|cyber|datos|data science|power bi"
    r"|python|informatica|computacion|robotica|asincronic|bootcamp|lernplattform|leeromgeving|larplattform|ead\b|numerique"
)


def relevant(title, desc=""):
    t, d = norm(title), norm(desc)[:300]
    if EXCLUDE.search(t):
        return False
    return bool(TRAINING.search(t) or TRAINING.search(d))


def is_digital(*texts):
    return bool(DIGITAL.search(norm(" ".join(t or "" for t in texts))))


# ---------------------------------------------------------------- region helpers
REGIONS = {
    "Latinoamérica": "argentina bolivia brasil brazil chile colombia costa rica cuba ecuador el salvador guatemala haiti honduras mexico nicaragua panama paraguay peru republica dominicana dominican uruguay venezuela jamaica bahamas barbados belize guyana suriname trinidad caribbean lac latin",
    "Norteamérica": "united states canada usa",
    "Europa": "albania armenia austria azerbaijan belarus belgium bosnia bulgaria croatia cyprus czech denmark estonia finland france georgia germany greece hungary iceland ireland italy kosovo latvia lithuania luxembourg malta moldova montenegro netherlands north macedonia norway poland portugal romania serbia slovakia slovenia spain sweden switzerland turkiye turkey ukraine united kingdom",
    "Medio Oriente": "bahrain egypt iran iraq israel jordan kuwait lebanon libya oman palestine qatar saudi syria united arab emirates yemen mena arab",
    "África": "algeria angola benin botswana burkina burundi cabo verde cape verde cameroon central african chad comoros congo cote d'ivoire djibouti eritrea eswatini ethiopia gabon gambia ghana guinea kenya lesotho liberia madagascar malawi mali mauritania mauritius morocco mozambique namibia niger nigeria rwanda sao tome senegal seychelles sierra leone somalia south africa south sudan sudan tanzania togo tunisia uganda zambia zimbabwe africa",
    "Asia-Pacífico": "afghanistan australia bangladesh bhutan cambodia china fiji india indonesia japan kazakhstan kiribati korea kyrgyz lao malaysia maldives marshall micronesia mongolia myanmar nauru nepal new zealand pakistan palau papua philippines samoa singapore solomon sri lanka tajikistan thailand timor tonga turkmenistan tuvalu uzbekistan vanuatu viet nam vietnam pacific asia",
}


MULTIWORD = ["costa rica", "el salvador", "republica dominicana", "dominican republic", "united states", "united kingdom",
             "north macedonia", "united arab emirates", "saudi arabia", "burkina faso", "cabo verde", "cape verde",
             "central african", "cote d'ivoire", "sao tome", "sierra leone", "south africa", "south sudan", "new zealand",
             "papua new guinea", "sri lanka", "viet nam", "marshall islands", "solomon islands", "trinidad"]


def region_of(country):
    c = norm(country)
    for mw in MULTIWORD:
        if mw in c:
            for reg, names in REGIONS.items():
                if mw in names:
                    return reg
    for reg, names in REGIONS.items():
        for n in names.split(" "):
            if n not in ("united", "south", "north", "new", "central", "republic", "republica", "states") and re.search(r"\b" + re.escape(n) + r"\b", c):
                return reg
    return "Global"


def iso(d):
    return d.isoformat() if d else ""


def parse_date(s, fmts):
    s = (s or "").strip()
    for f in fmts:
        try:
            return dt.datetime.strptime(s, f).date()
        except ValueError:
            continue
    return None


# ---------------------------------------------------------------- Mercado Público
MP_SEARCH = "https://www.mercadopublico.cl/BuscarLicitacion/Home/Buscar"
MP_FICHA = "https://www.mercadopublico.cl/Procurement/Modules/RFB/DetailsAcquisition.aspx?idlicitacion="
MP_KEYWORDS = ["capacitacion", "curso", "formacion", "diplomado", "e-learning", "b-learning", "m-learning", "relatoria",
               "talleres", "entrenamiento", "perfeccionamiento", "otec", "educacion continua", "programacion",
               "competencias", "inteligencia artificial", "seminario", "coaching", "ingles", "docentes", "virtualizacion",
               "plataforma educativa", "lms", "bootcamp", "capacitaciones"]


def mp_search(text, page):
    body = {"textoBusqueda": text, "idEstado": "5", "codigoRegion": "-1", "idTipoLicitacion": "-1",
            "fechaInicio": None, "fechaFin": None, "registrosPorPagina": "10", "idTipoFecha": [], "idOrden": "1",
            "compradores": [], "garantias": None, "rubros": [], "proveedores": [], "montoEstimadoTipo": [0],
            "esPublicoMontoEstimado": None, "pagina": page}
    return fetch(MP_SEARCH, data=body, headers={"Content-Type": "application/json; charset=utf-8"})


def mp_parse_list(h):
    out = []
    for blk in re.split(r'<div class="lic-bloq-wrap', h)[1:]:
        g = lambda pat: clean((re.search(pat, blk, re.S) or [None, ""])[1])
        lid = g(r'id-licitacion">.*?clearfix">\s*([^<]+)<')
        if not lid:
            continue
        cols = re.findall(r'<div class="[^"]*col-md-4[^"]*">(.*?)</div>', blk, re.S)
        out.append({
            "id": lid, "tipo": g(r'estado-lic">\s*<strong><span>([^<]+)</span>'),
            "title": g(r"<h2[^>]*>(.*?)</h2>"), "desc": g(r'<p class="text-weight-light">(.*?)</p>'),
            "monto": clean(cols[0]).replace("Monto", "").strip() if cols else "",
            "org": g(r'rot-resultado">\s*<div class="col-md-4"><strong>(.*?)</strong>'),
        })
    return out


def mp_label(t, name):
    full = name if name.startswith("grv") else "lbl" + name
    m = re.search(r'id="' + full + r'"[^>]*>(.*?)</span>', t, re.S)
    v = clean(m.group(1)) if m else ""
    return "" if v in ("No hay información", "") else v


def mp_ficha(lid):
    t = fetch(MP_FICHA + urllib.parse.quote(lid), opener=make_opener())
    L = lambda n: mp_label(t, n)
    crit = []
    for m in re.finditer(r'grvCriterios_ctl\d+_lblNombreCriterio"[^>]*>(.*?)</span>(.*?)</tr>', t, re.S):
        tail = clean(m.group(2))
        pct = re.search(r"(\d+(?:[.,]\d+)?)\s*%", tail)
        crit.append({"name": clean(m.group(1)), "weight": float(pct.group(1).replace(",", ".")) if pct else None,
                     "note": re.sub(r"\d+(?:[.,]\d+)?\s*%\s*$", "", tail).strip()[:160]})
    guar = []
    for n in sorted(set(re.findall(r'grvGarantias_ctl(\d+)_lblFicha8TituloTipoGarantia', t))):
        g = lambda f: mp_label(t, "grvGarantias_ctl" + n + "_lblFicha8" + f)
        guar.append({"type": g("TituloTipoGarantia"), "amount": g("Monto"), "currency": g("TipoMoneda"),
                     "expiry": g("FechaVencimiento"), "note": g("Descripcion")[:220]})
    items = []
    for n in sorted(set(re.findall(r'grvProducto_ctl(\d+)_lblProducto', t)))[:10]:
        p = mp_label(t, "grvProducto_ctl" + n + "_lblProducto")
        d = mp_label(t, "grvProducto_ctl" + n + "_lblDescripcion")
        q = mp_label(t, "grvProducto_ctl" + n + "_lblCantidad")
        items.append(" · ".join(x for x in [p, d[:200], (q + " " + mp_label(t, "grvProducto_ctl" + n + "_lblUnidad")).strip()] if x))
    fdt = lambda s: parse_date(s[:10], ["%d-%m-%Y"]) if s else None
    monto = L("Ficha7MontoEstimado")
    return {
        "description": L("Ficha1Descripcion"),
        "type": L("Ficha1Tipo"), "currency": L("Ficha1Moneda"), "stages": L("Ficha1Etapas"),
        "unit": L("Ficha2Unidad"), "region": L("Ficha2Region"), "comuna": L("Ficha2Comuna"),
        "dates": {k: iso(fdt(L(v))) for k, v in {
            "published": "Ficha3Publicacion", "questions_end": "Ficha3Fin", "answers": "Ficha3PublicacionRespuestas",
            "close": "Ficha3Cierre", "opening": "Ficha3ActoAperturaTecnica", "award": "Ficha3Adjudicacion"}.items()},
        "close_time": L("Ficha3Cierre")[11:16],
        "amount": int(monto) if monto.isdigit() else None, "amount_basis": L("Ficha7Estimacion"),
        "duration": L("Ficha7TiempoContrato"), "payment": L("Ficha7Plazos"), "renewal": L("Ficha7ContratoRenovacion"),
        "subcontracting": L("Ficha7Subcontratacion"), "criteria": crit, "guarantees": [g for g in guar if g["type"]],
        "items": items,
    }


FICHA_CACHE = {}  # id -> {"fetched": iso, "data": {...}}; lo carga y guarda main()


def mp_keyword(kw):
    rows_all, prev = [], None
    for page in range(1, 31):
        rows = mp_parse_list(mp_search(kw, page))
        sig = ",".join(r["id"] for r in rows)
        if not rows or sig == prev:
            break
        prev = sig
        rows_all += rows
        # las búsquedas de varias palabras traen mucho ruido al final; se corta cuando una página no aporta nada útil
        if len(rows) < 10 or not any(relevant(r["title"], r["desc"]) for r in rows):
            break
    return rows_all


def collect_mercado_publico():
    found = {}
    with cf.ThreadPoolExecutor(5) as ex:
        for rows in ex.map(mp_keyword, MP_KEYWORDS):
            for r in rows:
                found.setdefault(r["id"], r)
    cand = [r for r in found.values() if relevant(r["title"], r["desc"])]
    log(f"Mercado Público: {len(found)} resultados, {len(cand)} relevantes; leyendo fichas")
    items = []

    def build(r):
        c = FICHA_CACHE.get(r["id"])
        fresh = c and (TODAY - dt.date.fromisoformat(c["fetched"])).days < 3
        try:
            f = c["data"] if fresh else mp_ficha(r["id"])
            if not fresh:
                FICHA_CACHE[r["id"]] = {"fetched": iso(TODAY), "data": f}
        except Exception as e:  # ficha caída: se usa la copia anterior o lo del listado
            log("  ficha", r["id"], e)
            f = c["data"] if c else {"dates": {}}
        close = f["dates"].get("close", "")
        if close and close < iso(TODAY):
            return None
        amount = f.get("amount")
        return {
            "id": "MP-" + r["id"], "source": "Mercado Público", "multilateral": False, "region": "Latinoamérica",
            "country": "Chile", "title": r["title"], "buyer": r["org"].title(), "ref": r["id"],
            "kind": r["tipo"], "published": f["dates"].get("published", ""), "deadline": close,
            "value": amount, "currency": "CLP" if amount else "", "value_text": "" if amount else r["monto"],
            "lang": "ES", "url": MP_FICHA + r["id"], "digital": is_digital(r["title"], r["desc"], f.get("description", "")),
            "summary": f.get("description") or r["desc"], "details": f,
        }

    with cf.ThreadPoolExecutor(6) as ex:
        for it in ex.map(build, cand):
            if it:
                items.append(it)
    return items


# ---------------------------------------------------------------- Compra Ágil (Mercado Público, < 100 UTM)
CA_API = "https://api.buscador.mercadopublico.cl/compra-agil"
# Clave pública de cliente que el propio buscador web de Compra Ágil envía en cada consulta (no es una credencial personal).
CA_KEY = "e93089e4-437c-4723-b343-4fa20045e3bc"
CA_KEYWORDS = ["CAPACITACION", "CURSO", "TALLER", "DIPLOMADO", "RELATORIA", "E-LEARNING", "FORMACION", "SEMINARIO",
               "CHARLA", "ENTRENAMIENTO", "COACHING", "CERTIFICACION", "INGLES", "EXCEL"]


def ca_get(params):
    url = CA_API + "?" + urllib.parse.urlencode(params)
    last = None
    for _ in range(3):
        try:
            return json.loads(fetch(url, headers={"x-api-key": CA_KEY, "Origin": "https://buscador.mercadopublico.cl",
                                                  "Referer": "https://buscador.mercadopublico.cl/"}, timeout=70))
        except Exception as e:
            last = e
    raise last


def collect_compra_agil():
    found = {}
    base = {"date_from": iso(TODAY - dt.timedelta(days=30)), "date_to": iso(TODAY), "order_by": "recent", "status": 2}
    for kw in CA_KEYWORDS:
        page, pages = 1, 1
        while page <= min(pages, 10):
            p = ca_get(dict(base, keywords=kw, page_number=page)).get("payload") or {}
            pages = p.get("pageCount") or 1
            for r in p.get("resultados") or []:
                found.setdefault(r.get("codigo"), r)
            page += 1
    items = []
    for code, r in found.items():
        title = r.get("nombre", "")
        close = (r.get("fecha_cierre") or "")[:10]
        if not code or not relevant(title) or (close and close < iso(TODAY)):
            continue
        amount = r.get("monto_disponible_CLP")
        items.append({
            "id": "CA-" + code, "source": "Compra Ágil", "multilateral": False, "region": "Latinoamérica", "country": "Chile",
            "title": title, "buyer": (r.get("organismo") or "").title(), "ref": code, "kind": "Compra Ágil",
            "published": (r.get("fecha_publicacion") or "")[:10], "deadline": close,
            "value": float(amount) if amount else None, "currency": "CLP" if amount else "", "value_text": "",
            "lang": "ES", "url": "https://buscador.mercadopublico.cl/compra-agil?code=" + urllib.parse.quote(code),
            "digital": is_digital(title), "summary": r.get("descripcion", "") or "",
            "details": {"unit": r.get("unidad", ""), "currency": r.get("moneda", ""), "close_time": (r.get("fecha_cierre") or "")[11:16],
                        "dates": {"published": (r.get("fecha_publicacion") or "")[:10], "close": close},
                        "suppliers": r.get("cantidad_proveedores_cotizando")},
        })
    return items


# ---------------------------------------------------------------- TED (UE)
TED_URL = "https://api.ted.europa.eu/v3/notices/search"
TED_CPV = "80000000 80100000 80200000 80300000 80400000 80410000 80420000 80430000 80500000 80510000 80520000 80530000 80531000 80532000 80533000 80533100 80540000 80550000 80560000 80570000 80580000 80590000 80600000 48190000 72212190"
TED_FIELDS = ["publication-number", "notice-title", "buyer-name", "buyer-country", "deadline-receipt-tender-date-lot",
              "estimated-value-lot", "estimated-value-cur-lot", "description-lot", "publication-date",
              "classification-cpv", "notice-type", "procedure-type", "contract-duration-period-lot",
              "award-criterion-name-lot", "award-criterion-number-weight-lot", "buyer-email", "organisation-city-buyer"]
LANG_PREF = ["spa", "eng", "fra", "por", "deu", "ita", "nld", "swe"]


def ml(v):
    """Picks the best language from TED's multilingual fields."""
    if isinstance(v, dict):
        for lg in LANG_PREF:
            if v.get(lg):
                x = v[lg]
                return (x[0] if isinstance(x, list) else x), lg
        for lg, x in v.items():
            return (x[0] if isinstance(x, list) else x), lg
    if isinstance(v, list):
        return (v[0] if v else ""), ""
    return v or "", ""


def collect_ted():
    q = (f"classification-cpv IN ({TED_CPV}) AND deadline-receipt-tender-date-lot >= {TODAY:%Y%m%d} "
         "AND notice-type IN (cn-standard cn-social cn-desg pin-cfc-standard pin-cfc-social)")
    items, page = [], 1
    while page <= 12:
        res = json.loads(fetch(TED_URL, data={"query": q, "fields": TED_FIELDS, "limit": 100, "page": page,
                                              "paginationMode": "PAGE_NUMBER"}))
        notices = res.get("notices", [])
        for n in notices:
            desc, lg = ml(n.get("description-lot"))
            titles = n.get("notice-title") or {}
            pick = lambda v: (v[0] if isinstance(v, list) else v) if v else ""
            strip = lambda s: s.split(" – ")[-1].strip() if s.count(" – ") >= 2 else s
            title = strip(pick(titles.get(lg)) if isinstance(titles, dict) and titles.get(lg) else ml(titles)[0])
            title_es = strip(pick(titles.get("spa"))) if isinstance(titles, dict) else ""
            cpvs = n.get("classification-cpv") or []
            # el CPV principal (el primero) define el objeto; un 80xxxxx secundario no basta
            main_cpv = str(cpvs[0]) if cpvs else ""
            if not (main_cpv.startswith("80") or relevant(title, desc)) or EXCLUDE.search(norm(title)):
                continue
            dl = sorted(d[:10] for d in (n.get("deadline-receipt-tender-date-lot") or []) if d)
            vals = [float(v) for v in (n.get("estimated-value-lot") or []) if str(v).replace(".", "", 1).isdigit()]
            cur = (n.get("estimated-value-cur-lot") or [""])[0]
            countries = n.get("buyer-country") or []
            buyer, _ = ml(n.get("buyer-name"))
            crit_names = n.get("award-criterion-name-lot") or {}
            names, _ = (crit_names, "") if isinstance(crit_names, list) else (next(iter(crit_names.values()), []), "")
            weights = n.get("award-criterion-number-weight-lot") or []
            crit = [{"name": str(a), "weight": float(b) if str(b).replace(".", "", 1).isdigit() else None, "note": ""}
                    for a, b in zip(names, weights)][:8]
            pub = n.get("publication-number", "")
            items.append({
                "id": "TED-" + pub, "source": "TED (UE)", "multilateral": False,
                "region": "Europa", "country": ", ".join(sorted(set(countries))) or "UE",
                "title": title, "buyer": buyer, "ref": pub, "kind": (n.get("notice-type") or ""),
                "published": (n.get("publication-date") or "")[:10], "deadline": dl[0] if dl else "",
                "value": sum(vals) or None, "currency": cur, "value_text": "", "lang": lg, "lang_hint": lg,
                # el título "spa" de TED suele traer el título original sin traducir, así que se traduce aparte
                "url": f"https://ted.europa.eu/en/notice/-/detail/{pub}",
                "digital": is_digital(title, desc), "summary": desc[:900],
                "details": {"description": desc[:2500], "criteria": crit, "procedure": n.get("procedure-type", ""),
                            "cpv": (n.get("classification-cpv") or [])[:6], "dates": {"close": dl[0] if dl else ""},
                            "city": ml(n.get("organisation-city-buyer"))[0]},
            })
        if len(notices) < 100:
            break
        page += 1
    return items


# ---------------------------------------------------------------- Banco Mundial
WB_URL = "https://search.worldbank.org/api/v2/procnotices"
WB_TERMS = ["training", "capacity building", "e-learning", "teacher", "TVET", "vocational", "skills", "formation",
            "capacitación", "formação", "learning management", "curriculum"]


def collect_world_bank():
    seen, items = set(), []
    for term in WB_TERMS:
        q = urllib.parse.urlencode({"format": "json", "rows": 200, "qterm": term, "srt": "noticedate", "order": "desc"})
        try:
            res = json.loads(fetch(f"{WB_URL}?{q}"))
        except Exception as e:
            log("  WB", term, e)
            continue
        for n in res.get("procnotices", []):
            if n["id"] in seen or n.get("notice_type") == "Contract Award":
                continue
            seen.add(n["id"])
            dl = (n.get("submission_deadline_date") or n.get("submission_date") or "")[:10]
            if not dl or dl < iso(TODAY):
                continue
            title = n.get("bid_description") or n.get("project_name", "")
            if not relevant(title, clean(n.get("notice_text", ""))[:400]):
                continue
            text = clean(n.get("notice_text", ""))
            items.append({
                "id": "WB-" + n["id"], "source": "Banco Mundial", "multilateral": True,
                "region": region_of(n.get("project_ctry_name", "")), "country": n.get("project_ctry_name", ""),
                "title": title, "buyer": n.get("contact_organization") or n.get("project_name", ""),
                "ref": n.get("bid_reference_no", ""), "kind": n.get("notice_type", ""),
                "published": iso(parse_date(n.get("noticedate", ""), ["%d-%b-%Y"])), "deadline": dl,
                "value": None, "currency": "", "value_text": "",
                "lang": {"English": "en", "French": "fr", "Spanish": "es", "Portuguese": "pt", "Arabic": "ar",
                         "Russian": "ru"}.get(n.get("notice_lang_name"), ""),
                "url": f"https://projects.worldbank.org/en/projects-operations/procurement-detail/{n['id']}",
                "digital": is_digital(title, text), "summary": text[:900],
                "details": {"description": text[:2500], "project": f"{n.get('project_id', '')} · {n.get('project_name', '')}",
                            "method": n.get("procurement_method_name", ""), "group": n.get("procurement_group", ""),
                            "dates": {"close": dl}},
            })
    return items


# ---------------------------------------------------------------- PNUD
UNDP_URL = "https://procurement-notices.undp.org/"
UNDP_REG = {"RAF": "África", "RAS": "Asia-Pacífico", "RBAP": "Asia-Pacífico", "REC": "Europa", "RBEC": "Europa",
            "RLA": "Latinoamérica", "RBLAC": "Latinoamérica", "RAB": "Medio Oriente", "RBAS": "Medio Oriente"}


def collect_undp():
    t = fetch(UNDP_URL, encoding="utf-8")
    items = []
    for m in re.finditer(r'<a href="view_negotiation\.cfm\?nego_id=(\d+)"[^>]*data-region="region_([A-Z]+)"(.*?)</a>', t, re.S):
        nid, reg, blk = m.groups()
        cells = {clean(k): clean(v) for k, v in re.findall(
            r'cell__label">(.*?)</div>\s*<span>(.*?)</span>', blk, re.S)}
        title = cells.get("Title", "")
        dl = parse_date(cells.get("Deadline", "")[:9], ["%d-%b-%y"])
        if not dl or dl < TODAY or not relevant(title):
            continue
        office = cells.get("UNDP Office/Country", "")
        country = office.split("/")[-1].strip().title() if "/" in office else office
        items.append({
            "id": "UNDP-" + nid, "source": "PNUD", "multilateral": True,
            "region": UNDP_REG.get(reg, region_of(country)), "country": country, "title": title,
            "buyer": "PNUD " + country, "ref": cells.get("Ref No", ""), "kind": cells.get("Process", ""),
            "published": iso(parse_date(cells.get("Posted", ""), ["%d-%b-%y"])), "deadline": iso(dl),
            "value": None, "currency": "", "value_text": "", "lang": "", "digital": is_digital(title),
            "url": UNDP_URL + "view_negotiation.cfm?nego_id=" + nid, "summary": "",
            "details": {"method": cells.get("Process", ""), "deadline_text": cells.get("Deadline", ""), "dates": {"close": iso(dl)}},
        })
    return items


# ---------------------------------------------------------------- UNGM
UNGM = "https://www.ungm.org"
UNGM_TERMS = ["training", "learning", "capacity building", "formation", "capacitación", "course", "teacher",
              "TVET", "vocational", "skills", "workshop", "curriculum", "bootcamp", "formação", "educational"]


def collect_ungm():
    op = make_opener()
    page = fetch(UNGM + "/Public/Notice", opener=op)
    tok = re.search(r'name="__RequestVerificationToken"[^>]*value="([^"]+)"', page).group(1)
    seen, items = set(), []
    for term in UNGM_TERMS:
        for pi in range(0, 6):
            body = {"PageIndex": pi, "PageSize": 15, "Title": term, "Description": "", "Reference": "",
                    "PublishedFrom": "", "PublishedTo": "", "DeadlineFrom": TODAY.strftime("%d-%b-%Y"), "DeadlineTo": "",
                    "Countries": [], "Agencies": [], "UNSPSCs": [], "NoticeTypes": [], "SortField": "Deadline",
                    "SortAscending": True, "isPicker": False, "IsSustainable": False, "IsActive": True,
                    "NoticeDisplayType": None, "NoticeSearchTotalLabelId": "noticeSearchTotal", "TypeOfCompetitions": []}
            h = fetch(UNGM + "/Public/Notice/Search", data=body, opener=op, headers={"RequestVerificationToken": tok})
            rows = re.split(r'<div role="row"[^>]*data-noticeid="', h)[1:]
            for row in rows:
                nid = row.split('"', 1)[0]
                if nid in seen:
                    continue
                seen.add(nid)
                title = clean((re.search(r'ungm-title--small">(.*?)</span>', row, re.S) or [None, ""])[1])
                cells = [clean(c) for c in re.findall(r'role="cell" class="tableCell[^"]*"[^>]*>\s*<span>(.*?)</span>', row, re.S)]
                if len(cells) < 6 or not relevant(title):
                    continue
                dl = parse_date(cells[0][:11], ["%d-%b-%Y"])
                if not dl or dl < TODAY:
                    continue
                country = cells[5]
                items.append({
                    "id": "UNGM-" + nid, "source": "UNGM (ONU)", "multilateral": True,
                    "region": region_of(country), "country": country, "title": title, "buyer": cells[2],
                    "ref": cells[4], "kind": cells[3], "published": iso(parse_date(cells[1], ["%d-%b-%Y"])),
                    "deadline": iso(dl), "value": None, "currency": "", "value_text": "", "lang": "",
                    "url": f"{UNGM}/Public/Notice/{nid}", "digital": is_digital(title), "summary": "",
                    "details": {"method": cells[3], "deadline_text": cells[0], "dates": {"close": iso(dl)}},
                })
            if len(rows) < 15:
                break
    return items


# ---------------------------------------------------------------- seed (curado a mano)
def collect_seed():
    if not os.path.exists(SEED):
        return []
    with open(SEED, encoding="utf-8") as f:
        rows = json.load(f)
    return [r for r in rows if not r.get("deadline") or r["deadline"] >= iso(TODAY)]


# ---------------------------------------------------------------- main
SOURCES = [("Mercado Público", collect_mercado_publico), ("Compra Ágil", collect_compra_agil), ("TED (UE)", collect_ted), ("Banco Mundial", collect_world_bank),
           ("PNUD", collect_undp), ("UNGM (ONU)", collect_ungm), ("Curadas a mano", collect_seed)]


def main():
    state = {}
    if os.path.exists(STATE):
        with open(STATE, encoding="utf-8") as f:
            state = json.load(f)
    first_seen = state.get("first_seen", {})
    FICHA_CACHE.update(state.get("fichas", {}))
    previous = []
    if os.path.exists(OUT):
        with open(OUT, encoding="utf-8") as f:
            previous = json.load(f).get("items", [])
    items, status = {}, []
    for name, fn in SOURCES:
        try:
            got = fn()
            status.append({"name": name, "ok": True, "count": len(got)})
            log(f"{name}: {len(got)}")
        except Exception as e:
            # si la fuente no responde se conservan sus avisos de la última vuelta que siguen abiertos
            got = [dict(p, stale=True) for p in previous
                   if p.get("source") == name and (not p.get("deadline") or p["deadline"] >= iso(TODAY))]
            status.append({"name": name, "ok": False, "count": len(got), "error": str(e)[:200]})
            log(f"{name}: ERROR {e} (se conservan {len(got)} de la vuelta anterior)")
        for it in got:
            items.setdefault(it["id"], it)
    now = iso(TODAY)
    for it in items.values():
        it["first_seen"] = first_seen.setdefault(it["id"], now)
        it["new"] = it["first_seen"] == now and bool(state)
    # se olvidan las que ya no están para que no crezca sin límite
    state["first_seen"] = {k: v for k, v in first_seen.items() if k in items}
    state["fichas"] = {k: v for k, v in FICHA_CACHE.items() if "MP-" + k in items}
    data = {"generated": dt.datetime.now().isoformat(timespec="minutes"), "today": now, "sources": status,
            "items": sorted(items.values(), key=lambda x: (x["deadline"] or "9999", x["title"]))}
    import traducciones  # agrega lang_src, title_es y summary_es con las traducciones ya guardadas
    pending = traducciones.annotate(data, traducciones.load_json(traducciones.TRANS, {}))
    log(f"Traducciones pendientes: {len(pending)} (correr: python traducciones.py pendientes)")
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
    with open(STATE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False)
    log(f"Total: {len(items)} licitaciones -> {OUT}")


if __name__ == "__main__":
    main()
