"""Try several body shapes against Pipedream's actions/run endpoint to find
the one that resolves OAuth correctly. We have 5 connected accounts; if any
shape succeeds for any account, we know the right structure.
"""
import os, json
from pathlib import Path

# Load env from gateway
pid = (Path.home() / "earl" / "gateway.pid").read_text().strip()
with open(f"/proc/{pid}/environ", "rb") as f:
    for e in f.read().split(b"\x00"):
        if e and b"=" in e:
            k, _, v = e.partition(b"=")
            os.environ[k.decode()] = v.decode()

import httpx, asyncio

PROJECT_ID = os.environ["EARL_PIPEDREAM_PROJECT_ID"]
EXTERNAL_USER_ID = os.environ["EARL_PIPEDREAM_EXTERNAL_USER_ID"]
ENV = os.environ.get("EARL_PIPEDREAM_ENVIRONMENT", "production")
CLIENT_ID = os.environ["EARL_PIPEDREAM_CLIENT_ID"]
CLIENT_SECRET = os.environ["EARL_PIPEDREAM_CLIENT_SECRET"]

async def get_token():
    async with httpx.AsyncClient(timeout=30.0) as c:
        r = await c.post(
            "https://api.pipedream.com/v1/oauth/token",
            data={"grant_type": "client_credentials", "client_id": CLIENT_ID, "client_secret": CLIENT_SECRET},
        )
        return r.json()["access_token"]

async def list_accounts(tok):
    async with httpx.AsyncClient(timeout=30.0) as c:
        r = await c.get(
            f"https://api.pipedream.com/v1/connect/{PROJECT_ID}/accounts",
            headers={"Authorization": f"Bearer {tok}", "X-PD-Environment": ENV},
            params={"external_user_id": EXTERNAL_USER_ID, "include_credentials": "true"},
        )
        return r.json().get("data", [])

async def try_shape(tok, shape_name, body):
    async with httpx.AsyncClient(timeout=60.0) as c:
        r = await c.post(
            f"https://api.pipedream.com/v1/connect/{PROJECT_ID}/actions/run",
            headers={"Authorization": f"Bearer {tok}", "X-PD-Environment": ENV, "Content-Type": "application/json"},
            json=body,
        )
        print(f"\n=== {shape_name} ===")
        print(f"status={r.status_code}")
        try:
            data = r.json()
            preview = json.dumps(data, indent=2)[:1200]
            print(preview)
            return data
        except Exception:
            print(r.text[:600])
            return None

async def main():
    tok = await get_token()
    accounts = await list_accounts(tok)
    print(f"accounts available: {len(accounts)}")
    for a in accounts:
        app = a.get("app", {})
        print(f"  {a['id']}  app={app.get('name_slug')}  name={a.get('name')}")

    # Find the Gmail account for simpler testing (just list inbox vs. needing dates)
    gmail = next((a for a in accounts if a.get("app", {}).get("name_slug") == "gmail"), None)
    gcal = next((a for a in accounts if a.get("app", {}).get("name_slug") == "google_calendar"), None)
    if not gcal:
        print("No google_calendar account!")
        return

    print(f"\nUsing gcal account: {gcal['id']}")

    # Shape A: our current shape — nested under app slug
    await try_shape(tok, "A: nested under google_calendar", {
        "id": "google_calendar-quick-add-event",
        "external_user_id": EXTERNAL_USER_ID,
        "configured_props": {
            "google_calendar": {"authProvisionId": gcal["id"]},
            "calendarId": "primary",
            "text": "Earl test event at 11am",
        },
    })

    # Shape B: account_id at top level of configured_props
    await try_shape(tok, "B: account_id top-level", {
        "id": "google_calendar-quick-add-event",
        "external_user_id": EXTERNAL_USER_ID,
        "configured_props": {
            "account_id": gcal["id"],
            "calendarId": "primary",
            "text": "Earl test event at 11am",
        },
    })

    # Shape C: just authProvisionId at top-level
    await try_shape(tok, "C: authProvisionId top-level", {
        "id": "google_calendar-quick-add-event",
        "external_user_id": EXTERNAL_USER_ID,
        "authProvisionId": gcal["id"],
        "configured_props": {
            "calendarId": "primary",
            "text": "Earl test event at 11am",
        },
    })

    # Shape D: maybe Pipedream wants the literal account id string
    await try_shape(tok, "D: nested as plain string", {
        "id": "google_calendar-quick-add-event",
        "external_user_id": EXTERNAL_USER_ID,
        "configured_props": {
            "google_calendar": gcal["id"],
            "calendarId": "primary",
            "text": "Earl test event at 11am",
        },
    })

    # Shape E: GET the action schema first — look for prop names
    async with httpx.AsyncClient(timeout=30.0) as c:
        r = await c.get(
            f"https://api.pipedream.com/v1/connect/{PROJECT_ID}/components/google_calendar-quick-add-event",
            headers={"Authorization": f"Bearer {tok}", "X-PD-Environment": ENV},
        )
        print(f"\n=== component schema ===")
        print(f"status={r.status_code}")
        try:
            comp = r.json().get("data", r.json())
            props = comp.get("configurable_props") if isinstance(comp, dict) else None
            if props:
                print("configurable_props names + types:")
                for p in props[:15]:
                    print(f"  {p.get('name')} :: type={p.get('type')} app={p.get('app')}")
        except Exception as ex:
            print(f"err: {ex}")
            print(r.text[:500])

asyncio.run(main())
