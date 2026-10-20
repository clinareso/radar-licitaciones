# Radar de licitaciones de formación

Dashboard diario de licitaciones de educación, capacitación, e-learning y bootcamps.

- **Chile:** Mercado Público (con criterios de evaluación, garantías y plazos de cada ficha) y Compra Ágil.
- **Internacional:** TED (Unión Europea), Banco Mundial, PNUD y UNGM (ONU).
- **Curadas a mano:** BID, ADB, AfDB y portales sin API pública (`seed.json`).

Los títulos y descripciones en otros idiomas se traducen al español, y el dashboard muestra el idioma de origen.

## Cómo se actualiza

GitHub Actions (`.github/workflows/actualizar.yml`) corre todos los días a las 7:15 de Chile:

1. `collector.py` recolecta las fuentes y escribe `data.json`.
2. `traducir_api.py` traduce lo nuevo con la API de Anthropic (secreto `ANTHROPIC_API_KEY`).
3. Guarda los datos en el repositorio y publica el sitio en GitHub Pages.

Para correrlo a mano: pestaña **Actions** → **Actualizar licitaciones** → **Run workflow**.
Cualquier cambio en `dashboard.html`, `collector.py`, `traducciones.py` o `seed.json` subido a `main` republica el sitio.

## En tu computador

```
python collector.py
python -m http.server 8000
```

Luego abre http://localhost:8000/dashboard.html
