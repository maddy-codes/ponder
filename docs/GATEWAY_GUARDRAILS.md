# Gateway guardrails — stopping patient data at the boundary

Two different things are called "guardrails" in this project. They are complementary and
neither replaces the other.

| | Gateway protection | `agent/guardrails.py` |
|---|---|---|
| Lives in | Logfire → Gateway → Guardrails (UI) | our Python process |
| Acts on | the **request**, before it leaves the boundary | the prompt and the answer |
| Guarantee | the model **never receives** the data | we never *return* it |
| Configured by | clicking, no code | `agent/rules.json` |
| Covers | every call through the route, including ones we didn't write | calls this loop makes |

The gateway cleans what goes **in**. The harness layer polices what comes **out** and, on
a trip, buys more compute instead of refusing. A judge for the hackathon bonus is asking
for the first one: *"does the guardrail actually fire? A trace showing a redaction or a
block, not an `Observe` entry."*

## Why the in-process layer is not enough on its own

`detectors.personal_data()` from the harness catches emails, card numbers and
SSN/NI-shaped strings. It does **not** catch UK phone numbers or NHS numbers — verified,
not assumed:

```
07700 900123     -> allow      jane@acme.com        -> block
+44 7700 900123  -> allow      4111 1111 1111 1111  -> block
020 7946 0958    -> allow      123-45-6789          -> block
```

That gap is why `no_patient_identifiers` adds its own NHS/phone/MRN/DOB/postcode
patterns. But even with that, a prompt typed somewhere else — another service on the same
route, a colleague's script — never passes through our code at all. Only a protection at
the gateway covers those.

## Setup

1. Reveal the tabs. Append to your Logfire project URL:

   ```
   #enableFlags=gateway_optimizations,gateway_guardrails_beta
   ```

2. **Gateway → Guardrails → New protection → Custom pattern.**

3. Create each protection below, set **Apply to** your Modal endpoint, and set
   **Action** to `Redact` (or `Block`). **Not `Observe`** — it records without changing
   the request, so it demonstrates nothing and is explicitly excluded from the bonus.

### Protection 1 — NHS number

```regex
\b\d{3}[ -]?\d{3}[ -]?\d{4}\b
```

**Pattern tests — should match:**

```
NHS number 943 476 5919          nhs no 9434765919
Patient NHS 943-476-5919         NHS: 485 777 3456
```

**Should not match:**

```
Serum sodium 139 mmol/L          Give 500 mg in 5 mL
Bay 12, bed 4                    Batch 4471 expires 2027
```

> **Known limitation.** The gateway matches patterns, so this catches any ten-digit
> group — a lab accession number will be redacted too. The real NHS number has a
> Modulus 11 check digit, which a regex cannot express. `agent/guardrails.py`
> does validate the checksum, so the in-process layer is the precise one and this is
> the blunt one. Over-redacting a request is the safe direction; if it proves noisy,
> narrow the **Apply to** scope rather than loosening the pattern.

### Protection 2 — UK phone number

```regex
(?:\+44[\s.-]?\(?0\)?|\+44|0)[\s.-]?\d{2,4}[\s.-]?\d{3,4}[\s.-]?\d{3,4}
```

No lookarounds, so it stays portable across regex engines. Covers mobile, London,
regional, freephone and international forms with space, dot or hyphen separators.

**Should match:**

```
Call me on 07911 123456          Office line 020 7946 0958
Mobile: 07911123456              +44 20 7946 0958 ext 12
Reach me at +44 7911 123456      Manchester office: 0161 496 0000
+447911123456 is my cell         tel: +44 (0)7911 123456
Direct dial 0131-496-0123        0800 001 0000 for support
```

**Should not match** — the near-misses are what separate a useful protection from a
noisy one:

```
The meeting is on 2026-09-18     We shipped 45 tickets
Invoice total 1234.56            Room 401, Building 3
Sprint 4 planning at 10:30       Budget is 25000 GBP
Version 2.1.4 shipped            Ref ABC-123-XY
sarah@design.co.uk               Q3 2026 roadmap
```

### Protection 3 — date of birth

```regex
\b(?:\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{4}-\d{2}-\d{2})\b
```

Two separators are required, so `15/20` and `mg/kg/day` do not match.

## Proving it fired

An answer that simply omits the value proves nothing — a terse optimization rule can
drop a line for unrelated reasons. Ask the model to echo the string back:

```bash
uv run python scripts/echo_test.py
```

With no protection installed the digits come back verbatim:

```
MODEL RETURNED: 'my direct line is 07700 900123'
-> digits reached the model: YES
```

With a `Redact` protection on the route:

```
MODEL RETURNED: 'my direct line is [REDACTED]'
-> digits reached the model: NO
```

`07700 900123` is inside the range Ofcom reserves for drama and documentation, so it is
never a real subscriber. Use that range in anything you publish.

> **Watch the direction.** A redaction protection cleans the **request**. To stop the
> model *emitting* something in its reply, that is the response side — `Flag response`
> is a separate action, and `no_patient_identifiers` in `agent/guardrails.py` is our
> own response-side control.

## What to submit for the bonus

1. The protection and its action (screenshot of the rule page)
2. The stored **Pattern tests**, showing the match/near-miss samples
3. The echo test output above, before and after
4. A Logfire trace of the redaction firing
