# HubSpot setup guide

This walks through connecting the dashboard's **Live HubSpot** mode to a real HubSpot portal — creating the custom properties it reads, creating a scoped API token, and tagging a deal to test it. It's written for someone who hasn't created a HubSpot private app before, with every click spelled out.

Do this against a **HubSpot developer test account** (free, disposable) or a sandbox portal, not a production portal with real customer data — see "A note on data" at the bottom for why.

Budget about 20 minutes.

---

## 1. Get a HubSpot account to test against

If you don't already have one you're happy to experiment in:

1. Go to HubSpot's developer signup and create a **free developer account**. This gives you an empty test portal — nothing done here touches a real customer.
2. Log in to that portal.

If you already have a sandbox or developer portal, use that instead.

---

## 2. Create the custom deal properties

The connector maps HubSpot deals onto the bowtie stages through one custom property (`bowtie_stage`), plus a handful of others that carry the fields the rest of the project already expects (segment, motion, churn, expansion revenue).

1. Click the **settings gear icon** (top navigation bar).
2. In the left sidebar, go to **Data Management → Properties**.
3. Make sure the object dropdown at the top says **Deal properties**.
4. Click **Create property** and create each of the following. For every one, set the **Group** to something recognizable later (e.g. "Bowtie Diagnostic") — it just keeps them together in the property list.

| Internal name | Label | Field type | Values / notes |
|---|---|---|---|
| `bowtie_stage` | Bowtie Stage | Dropdown select | `Selection`, `Commit`, `Onboarding`, `Adoption`, `Renewal`, `Expansion` — add all six, in that order |
| `bowtie_segment` | Bowtie Segment | Dropdown select | `SMB`, `Mid-Market`, `Enterprise` |
| `bowtie_motion` | Bowtie Motion | Dropdown select | `Sales-led`, `PLG` |
| `bowtie_churned` | Bowtie Churned | Single checkbox | Check this the moment a deal is lost or lapses |
| `bowtie_expansion_revenue` | Bowtie Expansion Revenue | Number | Leave at 0 unless the deal expanded |
| `bowtie_activated` | Bowtie Activated | Single checkbox | Optional — only meaningful for PLG deals |

HubSpot lower-cases and underscores whatever label you type to generate the internal name, so typing "Bowtie Stage" as the label should produce `bowtie_stage` automatically — double-check it in the property's "internal name" field before saving, since that's the exact string the connector looks for.

**Why not just use HubSpot's native deal pipeline/stage?** HubSpot pipelines are built for a single sales-to-close motion, and mapping their default stages onto the eight-stage Bowtie model (which spans pre-sale *and* post-sale) would need either a custom pipeline per motion or a lot of if/else logic in the connector. One dropdown property that means exactly "which Bowtie stage is this deal in right now" is simpler to reason about and easier to defend.

---

## 3. Create a private app

A private app is how you get an API token scoped to just this integration, without publishing anything to the HubSpot marketplace.

1. Click the **settings gear icon** again.
2. In the left sidebar, go to **Integrations → Private Apps**.
3. Click **Create a private app**.
4. On the **Basic Info** tab, give it a name (e.g. "GTM Health Diagnostic") and an optional description.

### Scopes

5. Go to the **Scopes** tab and enable exactly these two, under **CRM**:
   - `crm.objects.deals.read`
   - `crm.objects.owners.read`

   That's it — the connector never writes back to HubSpot, so it doesn't need any `.write` scope.

6. Click **Create app** (top right). HubSpot shows the **access token** once. **Copy it now** — unlike an old-style API key, HubSpot will not show the full token again after this dialog closes. If it's lost, come back to this private app and click **Rotate** to issue a new one.

---

## 4. Tag a deal to test it

Before pointing the app at HubSpot, create at least one test deal so there's something to find:

1. Go to **CRM → Deals** and click **Create deal**.
2. Give it a name and an amount (this becomes `deal_value`).
3. Open the deal record, scroll to **Deal properties**, and set:
   - **Bowtie Stage** → e.g. `Selection`
   - **Bowtie Segment** → e.g. `Mid-Market`
   - **Bowtie Motion** → e.g. `Sales-led`
4. Save, wait a moment, then **change Bowtie Stage again** (e.g. to `Commit`). This second change is what creates the property *history* the connector reads to reconstruct how long the deal spent in each stage — a deal whose stage has only ever been set once still works, it just won't have a `days_in_stage` figure for that first stage yet.
5. Repeat with a few more deals at different stages, segments, and motions, so the dashboard has something to show across the funnel. HubSpot's Import tool (Data Management → Import) can also bulk-create deals from a CSV if a larger test set is useful faster than clicking through the UI one deal at a time — the same custom properties above map as import columns.

---

## 5. Add the token to the app

Locally, in `.streamlit/secrets.toml` at the project root (create the folder/file if it doesn't exist — it's already in `.gitignore`, so it never gets committed):

```toml
ANTHROPIC_API_KEY = "sk-ant-..."
HUBSPOT_ACCESS_TOKEN = "pat-..."
```

Or, running via an environment variable instead:

```bash
export HUBSPOT_ACCESS_TOKEN="pat-..."
```

On a hosted deployment (e.g. Streamlit Community Cloud), add the same `HUBSPOT_ACCESS_TOKEN` line to the app's own secrets manager — local `secrets.toml` files never get uploaded.

Restart the app (`streamlit run app.py`), open the sidebar, and switch **Data Source** to **Live HubSpot**.

---

## What happens if something's wrong

The app is built to degrade to Demo Data rather than crash, with a specific sidebar message for each failure mode:

- **No token found** — "No HubSpot access token configured." Check `.streamlit/secrets.toml`, the environment variable, or the hosting platform's secrets manager.
- **401 Unauthorized** — the token is wrong, expired, or was rotated since it was copied. Go back to the private app and copy the current token.
- **403 Forbidden** — the token is valid but the private app is missing one of the two scopes above. Go to the private app's Scopes tab, add the missing one, and save (existing tokens pick up new scopes automatically).
- **"found no deals with a bowtie_stage value set"** — the connection worked, but no deal has the `Bowtie Stage` property filled in. Go back to step 4.

In every case, Demo Data keeps working underneath so the rest of the app stays usable while the connection gets fixed.

---

## What the connector actually does

`data/hubspot_source.py` calls two HubSpot endpoints:

- `GET /crm/v3/owners` — to turn `hubspot_owner_id` into a rep's name.
- `GET /crm/v3/objects/deals`, with `propertiesWithHistory=bowtie_stage` — this is the part worth understanding. Instead of returning just the deal's *current* stage, HubSpot returns every value that property has ever held, each with a timestamp. The connector sorts that list chronologically and turns each consecutive pair into one row: the stage entered, the stage exited into, and the number of days between the two timestamps. The final entry (the deal's current stage) becomes the one row with an empty `stage_exited` — exactly the "snapshot" row the metrics layer already knows how to find in the synthetic data.

Because the reconstructed dataframe has the same shape as the synthetic generator's, nothing in `metrics/`, `advisor/`, or `charts/` needed to change. The diagnostic logic doesn't know or care whether a row came from a CSV or from HubSpot's API — it's a data source swap, not a rewrite.

**Scoped range:** Live mode only covers Selection → Expansion (the six `bowtie_stage` values). HubSpot deals don't naturally represent the pre-deal Awareness/Education stages, so those two blocks read zero in Live mode — the app shows a banner explaining this rather than silently displaying a misleading number.

---

## A note on data

Use a developer/sandbox portal with test deals, not a production portal with real customer or prospect data. The connector only ever reads — it has no write scope and cannot modify a portal — but running it against live customer records would sit uneasily with the project's own commitment (see the README's "what I deliberately did not build") that no personal data leaves the session.
