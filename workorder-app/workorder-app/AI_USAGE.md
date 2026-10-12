# AI Usage

> **Draft prepared with the AI assistant — review and edit before submitting.** The sections marked
> **✏️ YOURS** can only be answered by you; I've left them for you to fill in honestly after reading the code.
> Please make sure you can explain every file before you submit — you are responsible for the code.

## AI tools used

* **Claude** (Anthropic, Claude Sonnet 5.5), used in a single agentic coding session: it wrote files, ran the code,
  ran the tests, and drove the UI in a headless browser.

## What AI assisted with

Essentially the whole first draft:

* Interpreting the brief and choosing the stack (Flask + SQLite + plain JS) and the project layout.
* Database design: tables, constraints, indexes, the `maintenance_types` lookup, the `work_order_events` audit table.
* The pure rules module and state machine (`app/rules.py`), the service layer, REST endpoints, validation and error format.
* The frontend (list / create / detail screens, plus assets & technicians and asset history).
* All tests (39), `seed.py`, `README.md`, and this file's draft.

## Significant AI-generated code that you modified

**✏️ YOURS** — list the parts you changed after reading them, and why. For example, if you altered a rule, a status code,
a message, a column, or restyled the UI, say so here. *(At the time of writing, nothing had been changed by a human — the
code is as generated. Don't leave this saying "none" unless that's still true when you submit.)*

## Bugs / issues found in AI-generated output

Things found while building and verifying (all fixed unless noted):

1. **Environment, not code:** the sandbox blocked PyPI (HTTP 403 from the egress proxy), so the originally planned
   FastAPI + SQLAlchemy + pytest stack couldn't be installed. The stack was changed to what was available
   (Flask + raw `sqlite3` + `unittest`). Side effect: the schema is plain, visible DDL.
2. **Design loophole caught before shipping:** with Rule 6 enforced only at creation, a user could create an emergency
   work order on an out-of-service asset and then switch its type to "Repair". The rule is now also enforced on type
   change, and tested (`test_rule6_out_of_service_asset`).
3. **Wrong test, correct API:** the first full test run had 1 failure — an AI-written test re-posted a whole API response
   (including read-only `id`/`created_at`), which the API correctly rejected with 422. The test was fixed, not the API.
4. **Clumsy test code:** the first version of the database-constraint test contained leftover scaffolding and
   `x if False else y` hacks. It was rewritten as a clear table of invalid rows using `subTest`.
5. **UI test-script mistakes (not app bugs):** the browser smoke test twice mis-read the app — once reading a stale error
   banner when the browser's own `required` validation blocked a submit, once refilling only some required fields after a
   form reset. In both cases the UI was behaving correctly; the script was wrong.
6. **Not covered / open:** no load testing beyond the small concurrency tests; rule 5 uses the server's local date;
   see "Assumptions and known limitations" in `README.md`.

**✏️ YOURS** — add anything *you* find while reviewing and running it. A reviewer will value one real issue you found over a clean list.

## Important technical decisions you made yourself

**✏️ YOURS** — write only decisions you actually made or consciously agreed with, in your own words.

For reference, these are the judgement calls built into the code that an interviewer is likely to ask about.
They were *proposed by the AI*; decide which you agree with, change those you don't, and be ready to defend each:

* Rules enforced in **two layers** — service layer for friendly errors, database `CHECK`/`UNIQUE` as a safety net.
* `is_emergency` lives on a **`maintenance_types` table**, not on each work order.
* HTTP status split: **409** for conflicts (duplicates, illegal transitions, closed orders), **422** for validation/business-rule failures.
* **Forward-only** state machine; COMPLETED/CANCELLED are terminal and read-only.
* Assigning a technician to an OPEN order **auto-moves it to ASSIGNED**; creating with a technician starts it as ASSIGNED.
* `BEGIN IMMEDIATE` transactions so concurrent status changes can't both succeed.
* `PUT` behaves as a **partial update**; `asset_id` and `work_order_number` are immutable.
* An **audit-trail table** for status/assignment history, separate from the asset's maintenance history view.
