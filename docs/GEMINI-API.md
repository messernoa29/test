# Gemini API — Cheat sheet Python (SDK `google-genai`)

> Source: docs officielles Gemini API (avril 2026). Modèle courant: `gemini-3-flash-preview` (aperçu) / stable `gemini-2.5-flash`.

---

## 1. Installation

```bash
pip install -U google-genai
```

Python 3.9+. Ancien SDK `google-generativeai` est déprécié.

## 2. Authentification

La clé se crée sur https://aistudio.google.com/apikey.

Le client lit automatiquement `GEMINI_API_KEY` ou `GOOGLE_API_KEY` (si les deux sont définies, `GOOGLE_API_KEY` gagne).

```bash
export GEMINI_API_KEY="sk-..."
```

```python
from google import genai

# Option A: via variable d'env (recommandé)
client = genai.Client()

# Option B: explicite
client = genai.Client(api_key="sk-...")
```

## 3. Modèles disponibles (utiles pour analyse web)

| Model ID | Usage | Free tier |
|---|---|---|
| `gemini-3-flash-preview` | Flash gen 3, rapide + grounding | Oui |
| `gemini-3.1-pro-preview` | Pro, raisonnement complexe | Non (payant uniquement) |
| `gemini-3.1-flash-lite-preview` | Le moins cher | Oui |
| `gemini-2.5-pro` | Pro stable | Oui |
| `gemini-2.5-flash` | Flash stable (recommandé prod) | Oui |
| `gemini-2.5-flash-lite` | Ultra-économique | Oui |
| `gemini-2.0-flash` | **Déprécié** — migrer vers 2.5 | - |

Alias dynamiques: `gemini-flash-latest`, `gemini-pro-latest` (peuvent changer sans préavis court).

## 4. Appel basique `generate_content`

```python
from google import genai

client = genai.Client()

response = client.models.generate_content(
    model="gemini-2.5-flash",
    contents="Résume ce site en 3 points.",
)
print(response.text)
```

`contents` accepte `str`, `list[str]`, ou `list[Content/Part]` pour multimodal.

## 5. System instruction

```python
from google import genai
from google.genai import types

client = genai.Client()

response = client.models.generate_content(
    model="gemini-2.5-flash",
    config=types.GenerateContentConfig(
        system_instruction="Tu es un auditeur SEO. Réponds en français, concis."
    ),
    contents="Analyse https://example.com",
)
print(response.text)
```

## 6. `max_output_tokens`, `temperature`, etc.

> Pour Gemini 3: garder `temperature=1.0` (défaut). La modifier peut causer boucles/dégradation.

```python
from google.genai import types

response = client.models.generate_content(
    model="gemini-2.5-flash",
    contents="Explique comment l'IA fonctionne",
    config=types.GenerateContentConfig(
        temperature=0.2,
        top_p=0.8,
        top_k=20,
        max_output_tokens=1024,
        stop_sequences=["FIN"],
    ),
)
```

## 7. JSON structured output (schéma → JSON direct)

Supporte Pydantic natif. Le SDK convertit en JSON Schema.

```python
from google import genai
from google.genai import types
from pydantic import BaseModel, Field
from typing import List, Optional

class PageAudit(BaseModel):
    url: str
    title: Optional[str]
    score_seo: int = Field(ge=0, le=100)
    issues: List[str]

client = genai.Client()

response = client.models.generate_content(
    model="gemini-2.5-flash",
    contents="Audit: <HTML ou description du site>",
    config={
        "response_mime_type": "application/json",
        "response_json_schema": PageAudit.model_json_schema(),
    },
)

audit = PageAudit.model_validate_json(response.text)
print(audit.score_seo, audit.issues)
```

**Types JSON Schema supportés**: `string`, `number`, `integer`, `boolean`, `object`, `array`, `null`.
**Props utiles**: `description`, `enum`, `format` (date/date-time/time), `minimum`/`maximum`, `minItems`/`maxItems`, `required`, `properties`, `items`.
**Limite**: schémas trop larges/imbriqués peuvent être refusés. Gemini 2.0 exige `propertyOrdering` explicite (pas Gemini 2.5+).

## 8. Google Search grounding (équivalent web_search)

```python
from google import genai
from google.genai import types

client = genai.Client()

grounding_tool = types.Tool(google_search=types.GoogleSearch())

response = client.models.generate_content(
    model="gemini-2.5-flash",
    contents="Que fait l'entreprise derrière example.com ? Cite tes sources.",
    config=types.GenerateContentConfig(tools=[grounding_tool]),
)

print(response.text)

# Métadonnées de grounding
meta = response.candidates[0].grounding_metadata
print(meta.web_search_queries)        # requêtes exécutées
for chunk in meta.grounding_chunks:
    print(chunk.web.uri, chunk.web.title)
for sup in meta.grounding_supports:
    print(sup.segment.start_index, sup.segment.end_index, sup.grounding_chunk_indices)
```

**Combinable** avec `url_context` (fetch d'URLs explicites) et structured output en Gemini 3:

```python
config={
    "tools": [{"google_search": {}}, {"url_context": {}}],
    "response_mime_type": "application/json",
    "response_json_schema": PageAudit.model_json_schema(),
}
```

**Facturation grounding**:
- Gemini 3: par **requête de recherche**. 5000 requêtes/mois gratuites partagées famille Gemini 3, puis 14$/1000.
- Gemini 2.5 Pro: 1500 RPD gratuits, puis 35$/1000. Flash/Flash-Lite: 500 RPD free tier.

Anciens modèles utilisaient `google_search_retrieval` — **utiliser `google_search` maintenant**.

## 9. Gestion d'erreurs

```python
from google import genai
from google.genai import errors

client = genai.Client()

try:
    response = client.models.generate_content(
        model="gemini-2.5-flash", contents="..."
    )
except errors.ClientError as e:      # 4xx (rate limit 429, auth 401/403, bad request 400)
    print("Client:", e.code, e.message)
except errors.ServerError as e:      # 5xx
    print("Server:", e.code, e.message)
except errors.APIError as e:
    print("API:", e)
```

429 arrive comme `ClientError` avec `.code == 429`. Retry exponentiel recommandé sur 429/5xx.

## 10. Streaming

```python
stream = client.models.generate_content_stream(
    model="gemini-2.5-flash",
    contents="Écris un résumé long",
)
for chunk in stream:
    print(chunk.text, end="", flush=True)
```

## 11. Rate limits — free tier vs payant

Mesure: **RPM** (requêtes/min), **TPM** (tokens/min input), **RPD** (requêtes/jour). Appliqués **par projet**. Reset RPD à minuit Pacific.

**Niveaux (upgrade auto)**:

| Tier | Critère | Plafond |
|---|---|---|
| Free | Aucun billing | — |
| Tier 1 | Compte de facturation lié | 250 $ |
| Tier 2 | 100 $ payés + 3 j | 2 000 $ |
| Tier 3 | 1 000 $ payés + 30 j | 20 000+ $ |

**Valeurs usuelles free tier (à vérifier dans AI Studio)**:
- `gemini-2.5-flash`: ~10 RPM, 250K TPM, 250 RPD.
- `gemini-2.5-pro`: ~5 RPM, 250K TPM, 100 RPD.

**Beaucoup plus généreux que Anthropic free tier (10K TPM)**.

## 12. Pricing (par 1M tokens, USD, Standard payant)

| Modèle | Input | Output | Cache |
|---|---|---|---|
| `gemini-3.1-pro-preview` | 2 $ (≤200k) / 4 $ | 12 $ / 18 $ | 0,20 $ / 0,40 $ |
| `gemini-3-flash-preview` | 0,50 $ | 3 $ | 0,05 $ / 0,10 $ |
| `gemini-3.1-flash-lite-preview` | 0,25 $ / 0,50 $ | 1,50 $ | 0,025 $ / 0,05 $ |
| `gemini-2.5-pro` | 1,25 $ (≤200k) / 2,50 $ | 10 $ / 15 $ | 0,125 $ / 0,25 $ |
| `gemini-2.5-flash` | 0,30 $ | 2,50 $ | 0,03 $ / 0,10 $ |
| `gemini-2.5-flash-lite` | 0,10 $ / 0,30 $ | 0,40 $ | 0,01 $ / 0,03 $ |

Batch API ~50% du Standard.
**Données free tier utilisées pour améliorer Google** (pas en payant).

## 13. Finish reasons (détection troncature)

Accessible via `response.candidates[0].finish_reason`.

| Valeur | Sens |
|---|---|
| `STOP` | Fin naturelle |
| `MAX_TOKENS` | Troncature: `max_output_tokens` atteint |
| `SAFETY` | Bloqué par filtres sécurité |
| `RECITATION` | Récitation contenu protégé |
| `PROHIBITED_CONTENT` | Contenu interdit |
| `SPII` | Info personnelle sensible |
| `BLOCKLIST` | Mot bloqué |
| `MALFORMED_FUNCTION_CALL` | Tool call mal formé |
| `OTHER` / `FINISH_REASON_UNSPECIFIED` | Autre |

```python
resp = client.models.generate_content(model="gemini-2.5-flash", contents=prompt)
cand = resp.candidates[0]
if cand.finish_reason.name == "MAX_TOKENS":
    # Sortie tronquée — relancer avec plus de max_output_tokens
    ...
elif cand.finish_reason.name == "SAFETY":
    # Bloqué — voir cand.safety_ratings
    ...
else:
    print(resp.text)
```

---

## Usage counts

```python
print(response.usage_metadata.prompt_token_count)
print(response.usage_metadata.candidates_token_count)
print(response.usage_metadata.total_token_count)
```

## Exemple complet — audit d'un site

```python
from google import genai
from google.genai import types
from pydantic import BaseModel
from typing import List

class SiteAudit(BaseModel):
    url: str
    category: str
    summary: str
    seo_score: int
    tech_stack: List[str]
    issues: List[str]
    sources: List[str]

client = genai.Client()

response = client.models.generate_content(
    model="gemini-2.5-flash",
    contents="Analyse https://stripe.com et produis un audit.",
    config=types.GenerateContentConfig(
        system_instruction="Tu es auditeur web senior. Factuel, sourcé.",
        temperature=0.2,
        max_output_tokens=2048,
        tools=[types.Tool(google_search=types.GoogleSearch())],
        # Combiner grounding + JSON schema = Gemini 3 uniquement
        # response_mime_type="application/json",
        # response_json_schema=SiteAudit.model_json_schema(),
    ),
)

print(response.text)
print("finish:", response.candidates[0].finish_reason)
meta = response.candidates[0].grounding_metadata
if meta:
    for c in meta.grounding_chunks:
        print("-", c.web.title, c.web.uri)
```

---

**Points à vérifier**:
- Valeurs RPM/TPM/RPD free tier exactes → AI Studio par projet.
- Dispo `gemini-1.5-*` → absents pricing 2026, probablement dépréciés.
- Nom exact d'un `RateLimitError` dédié → pas documenté, en pratique `ClientError(code=429)`.
- Structured output + tools (grounding) = **Gemini 3 uniquement** (confirmé).
