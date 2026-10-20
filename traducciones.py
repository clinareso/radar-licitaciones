"""Traducciones al español para el dashboard.

Los textos se traducen una sola vez y quedan guardados en translations.json (clave = hash del texto original),
así cada día solo hay que traducir lo que aparece nuevo.

  python traducciones.py pendientes [N]   -> escribe pendientes_XX.json con hasta N textos cada uno (por defecto 60)
  python traducciones.py aplicar a.json…  -> agrega las traducciones {hash: texto_es} y actualiza data.json
"""
import glob
import hashlib
import json
import os
import re
import sys
import unicodedata

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data.json")
TRANS = os.path.join(HERE, "translations.json")
SUMMARY_LEN = 700

LANG_NAMES = {"es": "Español", "en": "Inglés", "fr": "Francés", "pt": "Portugués", "de": "Alemán", "it": "Italiano",
              "nl": "Neerlandés", "sv": "Sueco", "da": "Danés", "no": "Noruego", "fi": "Finés", "pl": "Polaco",
              "et": "Estonio", "lt": "Lituano", "lv": "Letón", "cs": "Checo", "sk": "Eslovaco", "hu": "Húngaro",
              "ro": "Rumano", "bg": "Búlgaro", "el": "Griego", "hr": "Croata", "sl": "Esloveno", "ga": "Irlandés",
              "mt": "Maltés", "ar": "Árabe", "ru": "Ruso", "vi": "Vietnamita", "az": "Azerí", "kk": "Kazajo"}
# TED usa códigos ISO 639-2
ISO3 = {"spa": "es", "eng": "en", "fra": "fr", "por": "pt", "deu": "de", "ita": "it", "nld": "nl", "swe": "sv",
        "dan": "da", "nor": "no", "fin": "fi", "pol": "pl", "est": "et", "lit": "lt", "lav": "lv", "ces": "cs",
        "slk": "sk", "hun": "hu", "ron": "ro", "bul": "bg", "ell": "el", "hrv": "hr", "slv": "sl", "gle": "ga", "mlt": "mt"}
STOP = {
    "es": "de la el en y los las del para con por una servicio servicios capacitacion curso contratacion",
    "en": "the and of for to in with services training provision on by development consultant",
    "fr": "de la le et des les pour du en recrutement formation services une un dans",
    "pt": "de da do e para os das dos em servicos contratacao formacao capacitacao uma",
    "de": "und der die das fur von mit zur zum im bei schulung dienstleistungen",
    "it": "di e la il per dei delle servizi servizio formazione della del",
    "nl": "en van de het voor een met opleiding diensten",
    "sv": "och av for till med utbildning tjanster",
}


def norm(s):
    s = unicodedata.normalize("NFD", s or "")
    return "".join(c for c in s if unicodedata.category(c) != "Mn").lower()


def detect(text):
    words = re.findall(r"[a-z]+", norm(text))
    if not words:
        return ""
    best, score = "", 0
    for lg, sw in STOP.items():
        s = set(sw.split())
        n = sum(1 for w in words if w in s)
        if n > score:
            best, score = lg, n
    return best if score >= 2 or (score == 1 and len(words) <= 6) else ""


def key(text):
    return hashlib.sha1(text.strip().encode("utf-8")).hexdigest()[:16]


def load_json(path, default):
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return default


def lang_of(it):
    hint = (it.get("lang_hint") or it.get("lang") or "").lower()
    if hint in ISO3:
        return ISO3[hint]
    if hint[:2] in LANG_NAMES and len(hint) <= 3:
        return hint[:2]
    if it.get("source") in ("Mercado Público", "Compra Ágil"):
        return "es"
    return detect((it.get("title_orig") or it.get("title", "")) + " " + (it.get("summary") or "")[:300])


def summary_text(it):
    return ((it.get("details") or {}).get("description") or it.get("summary") or "")[:SUMMARY_LEN].strip()


def annotate(data, trans):
    """Fills lang_src, title_es and summary_es. Returns the texts still missing a translation."""
    pending = {}
    for it in data["items"]:
        lg = lang_of(it)
        it["lang_src"] = lg
        it["lang_name"] = LANG_NAMES.get(lg, "Sin identificar") if lg else "Sin identificar"
        title = it.get("title_orig") or it.get("title", "")
        summ = summary_text(it)
        desc_lg = ISO3.get((it.get("desc_lang") or "").lower(), lg)
        it.pop("title_es", None), it.pop("summary_es", None)
        if lg and lg != "es":
            k = key(title)
            if it.get("title_es_given"):
                it["title_es"] = it["title_es_given"]
            elif k in trans:
                it["title_es"] = trans[k]
            elif title:
                pending[k] = {"lang": lg, "text": title}
        if summ and desc_lg != "es":
            k = key(summ)
            if k in trans:
                it["summary_es"] = trans[k]
            else:
                pending[k] = {"lang": desc_lg or lg or "auto", "text": summ}
    data["translation_pending"] = len(pending)
    return pending


def save_data(data):
    with open(DATA, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    data, trans = load_json(DATA, {"items": []}), load_json(TRANS, {})
    if cmd == "pendientes":
        size = int(sys.argv[2]) if len(sys.argv) > 2 else 60
        pending = annotate(data, trans)
        save_data(data)
        for old in glob.glob(os.path.join(HERE, "pendientes_*.json")):
            os.remove(old)
        items = list(pending.items())
        for n in range(0, len(items), size):
            with open(os.path.join(HERE, f"pendientes_{n // size + 1:02d}.json"), "w", encoding="utf-8") as f:
                json.dump(dict(items[n:n + size]), f, ensure_ascii=False, indent=1)
        print(f"{len(items)} textos por traducir en {(len(items) + size - 1) // size} archivos pendientes_XX.json")
    elif cmd == "aplicar":
        added = 0
        for path in sys.argv[2:]:
            got = load_json(path, {})
            for k, v in got.items():
                if isinstance(v, str) and v.strip():
                    trans[k] = v.strip()
                    added += 1
        with open(TRANS, "w", encoding="utf-8") as f:
            json.dump(trans, f, ensure_ascii=False)
        pending = annotate(data, trans)
        save_data(data)
        print(f"{added} traducciones agregadas; quedan {len(pending)} por traducir")
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
