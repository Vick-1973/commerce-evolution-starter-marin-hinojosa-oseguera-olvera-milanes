# Commerce Evolution — Starter

A small working e-commerce web application used as the baseline for the **ITESO Software Design — Fall 2026 Final Project**.

The system is deliberately modest: it works, it has tests and persistence, and its design is reasonable for its original requirements. Your job is to **understand it before you redesign it**, then evolve it when new requirements are released.

## What already works

- Visual product catalog and product detail pages
- Session-based shopping cart
- Checkout with one standard shipping option
- Simulated payment provider
- Persistent orders and order items
- Inventory updates
- Order history
- SQLite persistence through SQLAlchemy
- Automated tests with pytest
- GitHub Actions CI

## Technology

- Python 3.11 or newer
- Flask
- Jinja / HTML / CSS
- SQLAlchemy
- SQLite
- pytest
- Git + GitHub
- GitHub Actions

# Start here — create your team repository

Do **not** work directly in this starter repository.

1. Open the official starter repository in GitHub.
2. Select **Use this template → Create a new repository**.
3. **Only one teammate** creates the repository for the team.
4. Create **one public repository** for the entire team.
5. Give it a recognizable name, such as `commerce-evolution-pixel-vault`.
6. Do not add another README, `.gitignore`, or license during repository creation; the template already contains the project files.
7. Add the remaining teammates as collaborators.
8. Every teammate then clones **the new team repository**, not this starter repository.

Your team will keep evolving this same repository through all Final Project milestones.

## Clone the team repository

Copy the HTTPS URL from your team's repository and run:

```bash
git clone YOUR_TEAM_REPOSITORY_URL
cd YOUR_TEAM_REPOSITORY
```

Open the cloned folder in **VS Code**.

# Local setup

## 1. Create a virtual environment

### macOS / Linux

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### Windows PowerShell

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
```

In VS Code, select the Python interpreter inside `.venv` when prompted.

## 2. Install the project

With `.venv` active:

```bash
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

## 3. Seed the database

```bash
python seed.py
```

## 4. Run the tests

```bash
python -m pytest
```

All baseline tests should pass before you begin modifying the application.

## 5. Run the application

```bash
flask --app store run --debug
```

Open the local URL shown by Flask.

Use:

- `tok_success` as the test payment token
- `tok_fail` to simulate a declined payment

Before changing the design, verify the complete baseline flow: catalog → product → cart → checkout → order confirmation → order history, including persistent inventory/order changes.

## 6. Confirm GitHub Actions

Open your **team repository** on GitHub and select **Actions**.

Confirm that the test workflow completes successfully. The team should begin Milestone 1 with local tests passing and GitHub Actions green.

# Database reset during development

The project intentionally does not introduce a migration framework. If a milestone changes the local schema, reset and reseed the development SQLite database:

```bash
python reset_db.py
python seed.py
```

# One-command verification — macOS / Linux

From the project root you can run:

```bash
./scripts/verify.sh
```

The script creates `.venv`, installs the project, recreates the development database, seeds it, and runs the automated test suite.

If `.venv` already exists, the script reuses it only if it was created with Python 3.11 or newer. Otherwise, it stops and explains how to recreate the environment.

# Start Milestone 1

Read:

- [`docs/project-overview.md`](docs/project-overview.md)
- [`docs/milestone-1.md`](docs/milestone-1.md)

Then make the storefront your team's own while preserving the baseline behavior.

The Canvas assignment defines the required submission and evidence PDF. The repository documentation is where your team's evolving design story should live.

## Important: do not redesign for future requirements

During Milestone 1, change the structure only when necessary for storefront customization or to fix an actual defect.

Do **not** add speculative layers, interfaces, patterns, repositories, factories, or architectural scaffolding "just in case."

Future requirements will be released progressively.

# Troubleshooting checklist

Before assuming the starter is broken, verify:

1. `.venv` is active.
2. VS Code is using the `.venv` interpreter.
3. Dependencies were installed with `python -m pip install -e ".[dev]"`.
4. The database was seeded with `python seed.py`.
5. You are running commands from the repository root.
6. `python -m pytest` passes locally.

If something still fails, capture the exact command and complete error output before asking for help.

# BANVO — Milestone 2 fulfillment options

The checkout now supports **Standard Shipping ($99 MXN)**, **Express Shipping ($199 MXN)**, and **Store Pickup ($0 MXN)**. Standard/Express require an address; pickup does not. Fees are computed on the server and the selected method is saved with the order.

Start with your normal environment (Windows: `.\.venv\Scripts\Activate.ps1`), then run:

```powershell
python -m pip install -e ".[dev]"
python seed.py
python -m pytest -v
flask --app store run --debug
```

Add a product, go to `/checkout`, choose each fulfillment option, then use `tok_success` or `tok_fail` to validate the flow. Run `python scripts/inspect_persistence.py` to see the stored `fulfillment_method`, address, shipping fee, order and stock. **Do not reset** a development database if you need its historical orders: M2 adds the order column automatically on startup. Keep Flask stopped for database maintenance.

See [`docs/milestone-2.md`](docs/milestone-2.md) for the before/after design, decisions and trade-offs, and tests.

# BANVO — Milestone 3: Marketplace ordering

The app has **two entry points**, storefront checkout and `POST /api/marketplace/orders`, using the shared `src/store/ordering.py` service for authoritative SKU prices, fulfillment pricing, order persistence, order items and inventory updates. The marketplace payment is already complete; the integration does **not** invoke the web payment processor.

M3 also introduces **Strategy** implementations in `src/store/fulfillment.py`: `FlatRateDeliveryStrategy` (Standard/Express) and `StorePickupStrategy` (Pickup). These are composed with the option registry so new method behavior does not become a long set of checkout conditions. See [`docs/milestone-3.md`](docs/milestone-3.md).

## Run and test

```powershell
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
python -m pytest -v
python seed.py  # Only seeds when the product table is empty; never resets old orders
$env:MARKETPLACE_API_KEY = "local-demo-key" # development demo; set a real secret for deployment
flask --app store run --debug
```

**In a second PowerShell terminal**, use these commands for a real marketplace order (the server terminal keeps Flask running):

```powershell
$uri = "http://127.0.0.1:5000/api/marketplace/orders"
$headers = @{ "X-Marketplace-Key" = "local-demo-key" }
$body = @{
    external_order_id = "BANVO-MP-1001"
    buyer = @{ name = "Marketplace Buyer"; email = "buyer@example.com" }
    shipping = @{ method = "store_pickup"; address = "" }
    items = @( @{ sku = "BNV-MOU-002"; quantity = 1 } )
} | ConvertTo-Json -Depth 6

Invoke-RestMethod -Uri $uri -Method Post -Headers $headers -ContentType "application/json" -Body $body
# Repeat the exact same command: replayed=true and the order_id stays unchanged
Invoke-RestMethod -Uri $uri -Method Post -Headers $headers -ContentType "application/json" -Body $body
python scripts/inspect_persistence.py
```

Create a web order with `tok_success` to demonstrate the storefront still charges normally. Use `tok_fail` to verify declined payments do not persist orders.

**HTTP behavior:** 201 new order; 200 identical retry; 409 duplicate external ID with conflicting content or insufficient inventory; 400 invalid request; 401 bad key; 503 no server integration key; 415 non-JSON. Never submit an externally controlled `price_cents` or `payment_token` and expect it to override server prices/payment behavior. The integration secret is an academic demonstration credential; use a real authenticated and signed provider integration for production.

**Persistence:** M3 automatically adds `source`, `external_order_id` and `external_payload_hash` to existing SQLite `orders` tables and adds a unique index on `(source, external_order_id)`. Historical orders and inventories are retained. **Do not run `reset_db.py` to migrate.**
