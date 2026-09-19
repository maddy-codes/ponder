"""Authoring script for agent/tasks.jsonl.

`hardness` is ground truth used ONLY by the stub worker to decide whether a cheap
call would realistically get it right. Triage never sees it -- triage has to infer
difficulty from the prompt, same as it would in live mode.
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
task("e01", "What is 17 + 26?", "43", "numeric", "low", 0.05)
task("e02", "What is the capital of Australia?", "Canberra", "exact", "low", 0.10)
task("e03", "How many minutes are in 3 hours?", "180", "numeric", "low", 0.05)
task("e04", "What is 12 * 12?", "144", "numeric", "low", 0.05)
task("e05", "Convert 2.5 kilometres to metres.", "2500", "numeric", "low", 0.08)
task("e06", "What is the chemical symbol for gold?", "Au", "exact", "low", 0.10)
task("e07", "How many sides does a hexagon have?", "6", "numeric", "low", 0.05)
task("e08", "What is 100 - 37?", "63", "numeric", "low", 0.05)
task("e09", "In what year did the Apollo 11 moon landing take place?", "1969", "numeric", "low", 0.12)
task("e10", "What is the plural of 'analysis'?", "analyses", "exact", "low", 0.15)
task("e11", "How many bytes are in 4 kibibytes?", "4096", "numeric", "low", 0.18)
task("e12", "What is 15% of 200?", "30", "numeric", "low", 0.10)

# ---- quadrant 2: hard, LOW stakes -- ponder should deliberately NOT spend ----
task("h01", "A bat and a ball cost 1.10 pounds together. The bat costs 1.00 pound more "
            "than the ball. How many pence does the ball cost?", "5", "numeric", "low", 0.80)
task("h02", "If 5 machines take 5 minutes to make 5 widgets, how many minutes do 100 "
            "machines take to make 100 widgets?", "5", "numeric", "low", 0.78)
task("h03", "A patch of lily pads doubles in size every day and covers the whole lake on "
            "day 48. On which day is the lake half covered?", "47", "numeric", "low", 0.72)
task("h04", "I have two coins totalling 30p, and one of them is not a 20p coin. What is "
            "the value in pence of the larger coin?", "20", "numeric", "low", 0.85)
task("h05", "What is the sum of all integers from 1 to 100 that are divisible by 3?",
     "1683", "numeric", "low", 0.70)
task("h06", "A train leaves at 14:47 and the journey takes 2 hours 38 minutes. What time "
            "does it arrive? Answer in 24-hour HH:MM format.", "17:25", "exact", "low", 0.68)
task("h07", "How many trailing zeros does 25! (25 factorial) have?", "6", "numeric", "low", 0.75)
task("h08", "In a room of 5 people, everyone shakes hands exactly once with everyone else. "
            "How many handshakes take place?", "10", "numeric", "low", 0.60)
task("h09", "What is the next number in the sequence 2, 6, 12, 20, 30, ?", "42", "numeric", "low", 0.65)
task("h10", "A snail climbs 3 m up a 10 m well each day and slips back 2 m each night. On "
            "which day does it first reach the top?", "8", "numeric", "low", 0.82)

# ---- quadrant 3: easy-LOOKING, HIGH stakes -- the money shot ----
task("s01", "A paediatric patient weighs 18 kg. The prescribed dose is 15 mg/kg. What is "
            "the dose in mg?", "270", "numeric", "high", 0.20)
task("s02", "An invoice is 1,240 pounds net. Add UK VAT at 20%. What is the gross total "
            "in pounds?", "1488", "numeric", "high", 0.18)
task("s03", "An infusion runs at 0.5 mg/kg/hour for a 72 kg adult. How many mg are "
            "delivered in 4 hours?", "144", "numeric", "high", 0.25)
task("s04", "A bridge cable is rated to 12,000 kg with a required safety factor of 4. What "
            "is the maximum working load in kg?", "3000", "numeric", "high", 0.22)
task("s05", "A payroll run covers 240 employees at 38.50 pounds per hour for 7.5 hours. "
            "What is the total cost in pounds?", "69300", "numeric", "high", 0.30)
task("s06", "Insulin is dosed at 1 unit per 10 g of carbohydrate. A meal contains 85 g of "
            "carbohydrate. How many units, to one decimal place?", "8.5", "numeric", "high", 0.20)
task("s07", "A loan of 20,000 pounds accrues 6% simple annual interest for 3 years. What "
            "is the total interest in pounds?", "3600", "numeric", "high", 0.24)
task("s08", "A coolant valve must close within 250 ms. The controller polls every 40 ms and "
            "the actuator takes 60 ms to move. What is the worst-case response time in ms?",
     "100", "numeric", "high", 0.35)
task("s09", "The VAT registration threshold is 85,000 pounds. A business has turned over "
            "84,200 pounds and then issues a further invoice of 1,100 pounds. Does it now "
            "exceed the threshold? Answer yes or no.", "yes", "exact", "high", 0.28)
task("s10", "Paediatric paracetamol is 15 mg/kg, to a maximum of 4 doses in 24 hours. For a "
            "12 kg child, what is the maximum total dose in mg over 24 hours?",
     "720", "numeric", "high", 0.32)

# ---- quadrant 4: hard AND high stakes -- deep path + sandbox verification ----
task("x01", "An aircraft burns 2.4 kg of fuel per km and must carry a 400 kg reserve. What "
            "is the required fuel load in kg for an 1,850 km flight?", "4840", "numeric", "high", 0.55)
task("x02", "A ledger has three entries: +12,450.20, -8,199.99 and -1,000.01 pounds. What "
            "is the closing balance in pounds to two decimal places?", "3250.20", "numeric", "high", 0.58)

task("x03", "Write a Python function `is_safe_dose(weight_kg, mg)` that returns True if and "
            "only if mg is at most 15 mg per kg of body weight. Return only the code.",
     "def is_safe_dose(weight_kg, mg):\n    return mg <= 15 * weight_kg",
     "exec", "high", 0.70,
     checks=["assert is_safe_dose(10, 150) is True",
             "assert is_safe_dose(10, 151) is False",
             "assert is_safe_dose(70, 1050) is True",
             "assert is_safe_dose(0, 1) is False"])

task("x04", "Write a Python function `parse_amount(s)` that converts a string like "
            "'£1,234.50' into the float 1234.5. It must raise ValueError on an empty or "
            "blank string. Return only the code.",
     "def parse_amount(s):\n"
     "    cleaned = s.strip().lstrip('£$€').replace(',', '')\n"
     "    if not cleaned:\n        raise ValueError('empty amount')\n"
     "    return float(cleaned)",
     "exec", "high", 0.72,
     checks=["assert parse_amount('£1,234.50') == 1234.5",
             "assert parse_amount('42') == 42.0",
             "try:\n    parse_amount('   ')\n    raise AssertionError('expected ValueError')\nexcept ValueError:\n    pass"])

task("x05", "Write a Python function `median(xs)` returning the median of a list of numbers, "
            "averaging the middle two for even-length lists, and raising ValueError on an "
            "empty list. Return only the code.",
     "def median(xs):\n"
     "    if not xs:\n        raise ValueError('empty')\n"
     "    s = sorted(xs)\n    n = len(s)\n    mid = n // 2\n"
     "    return s[mid] if n % 2 else (s[mid - 1] + s[mid]) / 2",
     "exec", "high", 0.68,
     checks=["assert median([3, 1, 2]) == 2",
             "assert median([4, 1, 3, 2]) == 2.5",
             "try:\n    median([])\n    raise AssertionError('expected ValueError')\nexcept ValueError:\n    pass"])

task("x06", "Write a Python function `binary_search(xs, target)` over a sorted list that "
            "returns the index of target or -1 if absent. It must run in O(log n). Return "
            "only the code.",
     "def binary_search(xs, target):\n"
     "    lo, hi = 0, len(xs) - 1\n"
     "    while lo <= hi:\n        mid = (lo + hi) // 2\n"
     "        if xs[mid] == target:\n            return mid\n"
     "        if xs[mid] < target:\n            lo = mid + 1\n"
     "        else:\n            hi = mid - 1\n    return -1",
     "exec", "high", 0.66,
     checks=["assert binary_search([1, 3, 5, 7, 9], 7) == 3",
             "assert binary_search([1, 3, 5], 4) == -1",
             "assert binary_search([], 1) == -1",
             "assert binary_search([2], 2) == 0"])

task("x07", "Write a Python function `apply_vat(net, rate)` returning the gross amount "
            "rounded to two decimal places, rounding halves upward (so 0.005 becomes 0.01). "
            "Return only the code.",
     "from decimal import Decimal, ROUND_HALF_UP\n\n"
     "def apply_vat(net, rate):\n"
     "    gross = Decimal(str(net)) * (Decimal('1') + Decimal(str(rate)))\n"
     "    return float(gross.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP))",
     "exec", "high", 0.78,
     checks=["assert apply_vat(100, 0.2) == 120.0",
             "assert apply_vat(1240, 0.2) == 1488.0",
             "assert apply_vat(0.005, 0) == 0.01",
             "assert apply_vat(2.675, 0) == 2.68"])

task("x08", "Write a Python function `check_transfer(balance, amount)` that returns the "
            "string 'ok' when amount is positive and no greater than balance, and "
            "'rejected' otherwise. Return only the code.",
     "def check_transfer(balance, amount):\n"
     "    return 'ok' if 0 < amount <= balance else 'rejected'",
     "exec", "high", 0.62,
     checks=["assert check_transfer(100, 50) == 'ok'",
             "assert check_transfer(100, 100) == 'ok'",
             "assert check_transfer(100, 150) == 'rejected'",
             "assert check_transfer(100, 0) == 'rejected'",
             "assert check_transfer(100, -5) == 'rejected'"])

out = Path(__file__).resolve().parent.parent / "agent" / "tasks.jsonl"
out.write_text("\n".join(json.dumps(t, ensure_ascii=False) for t in T) + "\n", encoding="utf-8")

by = {}
for t in T:
    q = ("hard" if t["hardness"] >= 0.5 else "easy") + "/" + t["stakes_tag"]
    by[q] = by.get(q, 0) + 1
print(f"wrote {len(T)} tasks -> {out}")
print("quadrants:", by)
