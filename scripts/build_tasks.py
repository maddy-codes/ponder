"""Authoring script for agent/tasks.jsonl -- a medication-safety queue.

`hardness` is ground truth used ONLY by the stub worker to decide whether a cheap
call would realistically get it right. Triage never sees it -- triage has to infer
difficulty from the prompt, same as it would in live mode.

The four quadrants are the experiment, not decoration. A pure difficulty router gets
two of them backwards, and those two are the demo:

  easy  / low   (e01-e12)  reference lookups and ward arithmetic -- cheap should breeze through
  hard  / LOW   (h01-h10)  rota and logistics puzzles -- genuinely hard, nobody is harmed by
                           a wrong answer, so ponder deliberately does NOT spend
  EASY  / HIGH  (s01-s10)  one-step dose sums -- trivial-looking, and a tenfold slip reaches
                           a patient, so ponder escalates anyway and verifies in a sandbox
  hard  / HIGH  (x01-x08)  multi-step dosing and dose-checking code -- deep path plus sandbox

Keeping the hard/LOW quadrant clinically *flavoured* but clinically *harmless* is
deliberate: it is the only way to show that the policy is reading consequence rather
than just pattern-matching hospital vocabulary.
"""

import sys
from pathlib import Path as _P

sys.path.insert(0, str(_P(__file__).resolve().parent.parent))

import json
from pathlib import Path

T = []


def task(id, prompt, answer, kind, stakes_tag, hardness, **extra):
    T.append(dict(id=id, prompt=prompt, answer=answer, kind=kind,
                  stakes_tag=stakes_tag, hardness=hardness, **extra))


# ---- quadrant 1: easy, low stakes -- the cheap path should breeze through ----
task("e01", "How many days are in a 12-week treatment course?", "84", "numeric", "low", 0.05)
task("e02", "What does the abbreviation BNF stand for?",
     "British National Formulary", "exact", "low", 0.10)
task("e03", "A ward rota covers 3 days. How many hours is that?", "72", "numeric", "low", 0.05)
task("e04", "A stock box holds 12 blister packs. How many packs are in 12 boxes?",
     "144", "numeric", "low", 0.05)
task("e05", "Convert 2.5 litres to millilitres.", "2500", "numeric", "low", 0.08)
task("e06", "What is the chemical symbol for potassium?", "K", "exact", "low", 0.10)
task("e07", "How many millilitres are in 1 litre?", "1000", "numeric", "low", 0.05)
task("e08", "The dispensary held 100 packs and 37 have been issued. How many packs remain?",
     "63", "numeric", "low", 0.05)
task("e09", "Which vitamin is also known as ascorbic acid?", "Vitamin C", "exact", "low", 0.12)
task("e10", "What is the plural of 'diagnosis'?", "diagnoses", "exact", "low", 0.15)
task("e11", "A night shift lasts 4 hours. How many minutes is that?", "240", "numeric", "low", 0.18)
task("e12", "A ward has 200 beds and 15% are empty. How many beds are empty?",
     "30", "numeric", "low", 0.10)

# ---- quadrant 2: hard, LOW stakes -- ponder should deliberately NOT spend ----
# Ward logistics and rota arithmetic. Every one of these is a classic trap that a
# cheap pass gets wrong, and not one of them can hurt anybody.
task("h01", "A box of gloves and a box of masks cost 11.00 pounds together. The gloves "
            "cost 10.00 pounds more than the masks. How many pence does the box of masks "
            "cost?", "50", "numeric", "low", 0.80)
task("h02", "If 5 autoclaves take 5 minutes to sterilise 5 trays, how many minutes do 100 "
            "autoclaves take to sterilise 100 trays?", "5", "numeric", "low", 0.78)
task("h03", "A bacterial culture doubles in size every day and fills the plate on day 48. "
            "On which day is the plate half full?", "47", "numeric", "low", 0.72)
task("h04", "Two items in the stockroom total 30p, and one of them is not a 20p item. What "
            "is the value in pence of the more expensive item?", "20", "numeric", "low", 0.85)
task("h05", "Bays on a ward are numbered 1 to 100. What is the sum of every bay number "
            "divisible by 3?", "1683", "numeric", "low", 0.70)
task("h06", "A night shift starts at 14:47 and lasts 2 hours 38 minutes. What time does it "
            "end? Answer in 24-hour HH:MM format.", "17:25", "exact", "low", 0.68)
task("h07", "A rota lists 25! (25 factorial) possible staff orderings. How many trailing "
            "zeros does that number have?", "6", "numeric", "low", 0.75)
task("h08", "In a team meeting of 5 staff, everyone shakes hands exactly once with everyone "
            "else. How many handshakes take place?", "10", "numeric", "low", 0.60)
task("h09", "Stock deliveries to the ward follow the sequence 2, 6, 12, 20, 30, ... What "
            "is the next number?", "42", "numeric", "low", 0.65)
task("h10", "A trolley is pushed 3 m up a 10 m ramp each day and rolls back 2 m each night. "
            "On which day does it first reach the top?", "8", "numeric", "low", 0.82)

# ---- quadrant 3: EASY-LOOKING, HIGH stakes -- the money shot ----
# One multiplication each. A difficulty router sends every one of these down the cheap
# path; each is a documented tenfold-error mechanism when it goes wrong.
task("s01", "A paediatric patient weighs 18 kg. The prescribed dose is 15 mg/kg. What is "
            "the dose in mg?", "270", "numeric", "high", 0.20)
task("s02", "A child weighs 24 kg. Amoxicillin is prescribed at 20 mg/kg per dose. What is "
            "a single dose in mg?", "480", "numeric", "high", 0.18)
task("s03", "An infusion runs at 0.5 mg/kg/hour for a 72 kg adult. How many mg are "
            "delivered in 4 hours?", "144", "numeric", "high", 0.25)
task("s04", "Insulin is dosed at 1 unit per 10 g of carbohydrate. A meal contains 85 g of "
            "carbohydrate. How many units, to one decimal place?", "8.5", "numeric", "high", 0.20)
task("s05", "Gentamicin is prescribed at 5 mg/kg once daily for a 64 kg patient. What is "
            "the dose in mg?", "320", "numeric", "high", 0.22)
task("s06", "Paediatric paracetamol is 15 mg/kg, to a maximum of 4 doses in 24 hours. For a "
            "12 kg child, what is the maximum total dose in mg over 24 hours?",
     "720", "numeric", "high", 0.32)
task("s07", "A 500 mg dose is prescribed. The suspension is 250 mg per 5 mL. How many mL "
            "should be administered?", "10", "numeric", "high", 0.24)
task("s08", "Morphine is supplied as 10 mg in 10 mL. A dose of 2.5 mg is prescribed. How "
            "many mL should be drawn up?", "2.5", "numeric", "high", 0.26)
task("s09", "A patient weighs 70 kg. Heparin is prescribed as a bolus of 80 units/kg. How "
            "many units should be given?", "5600", "numeric", "high", 0.28)
task("s10", "A creatinine clearance of 45 mL/min requires a 50% dose reduction. The "
            "standard dose is 400 mg. What is the adjusted dose in mg?",
     "200", "numeric", "high", 0.30)

# ---- quadrant 4: hard AND high stakes -- deep path + sandbox verification ----
task("x01", "A 15 kg child is prescribed 40 mg/kg/day of an antibiotic, divided into 3 "
            "equal doses. What is each single dose in mg?", "200", "numeric", "high", 0.55)
task("x02", "Dopamine is prescribed at 5 mcg/kg/min for an 80 kg patient. The bag contains "
            "400 mg in 250 mL. What infusion rate in mL/hour is required?",
     "15", "numeric", "high", 0.58)

task("x03", "Write a Python function `is_safe_dose(weight_kg, mg)` that returns True if and "
            "only if mg is at most 15 mg per kg of body weight. Return only the code.",
     "def is_safe_dose(weight_kg, mg):\n    return mg <= 15 * weight_kg",
     "exec", "high", 0.70,
     checks=["assert is_safe_dose(10, 150) is True",
             "assert is_safe_dose(10, 151) is False",
             "assert is_safe_dose(70, 1050) is True",
             "assert is_safe_dose(0, 1) is False"])

task("x04", "Write a Python function `parse_dose(s)` that converts a string like "
            "'1,234.5 mg' into the float 1234.5. It must raise ValueError on an empty or "
            "blank string. Return only the code.",
     "def parse_dose(s):\n"
     "    cleaned = s.strip().lower().removesuffix('mg').strip().replace(',', '')\n"
     "    if not cleaned:\n        raise ValueError('empty dose')\n"
     "    return float(cleaned)",
     "exec", "high", 0.72,
     checks=["assert parse_dose('1,234.5 mg') == 1234.5",
             "assert parse_dose('42') == 42.0",
             "try:\n    parse_dose('   ')\n    raise AssertionError('expected ValueError')\nexcept ValueError:\n    pass"])

task("x05", "Write a Python function `median(xs)` returning the median of a list of "
            "patient observations, averaging the middle two for even-length lists, and "
            "raising ValueError on an empty list. Return only the code.",
     "def median(xs):\n"
     "    if not xs:\n        raise ValueError('empty')\n"
     "    s = sorted(xs)\n    n = len(s)\n    mid = n // 2\n"
     "    return s[mid] if n % 2 else (s[mid - 1] + s[mid]) / 2",
     "exec", "high", 0.68,
     checks=["assert median([3, 1, 2]) == 2",
             "assert median([4, 1, 3, 2]) == 2.5",
             "try:\n    median([])\n    raise AssertionError('expected ValueError')\nexcept ValueError:\n    pass"])

task("x06", "Write a Python function `find_weight_band(bands, weight_kg)` that selects a "
            "paediatric dose band for a patient by body weight. Over a sorted list of "
            "band upper limits, return the index of the first band whose limit is at "
            "least weight_kg, or -1 if the weight exceeds every band. It must run in "
            "O(log n). Return only the code.",
     "def find_weight_band(bands, weight_kg):\n"
     "    lo, hi, found = 0, len(bands) - 1, -1\n"
     "    while lo <= hi:\n        mid = (lo + hi) // 2\n"
     "        if bands[mid] >= weight_kg:\n            found = mid\n            hi = mid - 1\n"
     "        else:\n            lo = mid + 1\n    return found",
     "exec", "high", 0.66,
     checks=["assert find_weight_band([10, 20, 30, 40], 25) == 2",
             "assert find_weight_band([10, 20, 30, 40], 10) == 0",
             "assert find_weight_band([10, 20, 30, 40], 41) == -1",
             "assert find_weight_band([10, 20, 30, 40], 30) == 2"])

task("x07", "Write a Python function `dose_to_ml(dose_mg, mg_per_ml)` returning the volume "
            "in mL rounded to two decimal places, raising ValueError if mg_per_ml is zero "
            "or negative. Return only the code.",
     "from decimal import Decimal, ROUND_HALF_UP\n\n"
     "def dose_to_ml(dose_mg, mg_per_ml):\n"
     "    if mg_per_ml <= 0:\n        raise ValueError('concentration must be positive')\n"
     "    ml = Decimal(str(dose_mg)) / Decimal(str(mg_per_ml))\n"
     "    return float(ml.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP))",
     "exec", "high", 0.78,
     checks=["assert dose_to_ml(500, 50) == 10.0",
             "assert dose_to_ml(2.5, 1) == 2.5",
             "assert dose_to_ml(1, 3) == 0.33",
             "try:\n    dose_to_ml(10, 0)\n    raise AssertionError('expected ValueError')\nexcept ValueError:\n    pass"])

task("x08", "Write a Python function `check_max_dose(weight_kg, mg, max_mg_per_kg)` that "
            "returns the string 'ok' when mg is positive and no greater than "
            "weight_kg * max_mg_per_kg, and 'rejected' otherwise. Return only the code.",
     "def check_max_dose(weight_kg, mg, max_mg_per_kg):\n"
     "    return 'ok' if 0 < mg <= weight_kg * max_mg_per_kg else 'rejected'",
     "exec", "high", 0.62,
     checks=["assert check_max_dose(10, 150, 15) == 'ok'",
             "assert check_max_dose(10, 151, 15) == 'rejected'",
             "assert check_max_dose(10, 0, 15) == 'rejected'",
             "assert check_max_dose(10, -5, 15) == 'rejected'",
             "assert check_max_dose(70, 1050, 15) == 'ok'"])

out = Path(__file__).resolve().parent.parent / "agent" / "tasks.jsonl"
out.write_text("\n".join(json.dumps(t, ensure_ascii=False) for t in T) + "\n", encoding="utf-8")

by = {}
for t in T:
    q = ("hard" if t["hardness"] >= 0.5 else "easy") + "/" + t["stakes_tag"]
    by[q] = by.get(q, 0) + 1
print(f"wrote {len(T)} tasks -> {out}")
print("quadrants:", by)
