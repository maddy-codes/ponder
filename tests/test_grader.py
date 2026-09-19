from agent.grader import extract_code, extract_number, grade
from agent.tasks import load_tasks

TASKS = {t.id: t for t in load_tasks()}


def test_reference_answers_all_self_grade():
    failing = [t.id for t in load_tasks() if not grade(t, t.answer)]
    assert failing == []


def test_numeric_tolerates_prose_and_takes_the_last_number():
    assert grade(TASKS["s01"], "15 mg/kg times 18 kg, so the dose is 270 mg")
    assert not grade(TASKS["s01"], "270 kg is the weight, so the dose is 27 mg")


def test_exec_runs_the_checks():
    assert grade(TASKS["x08"], f"```python\n{TASKS['x08'].answer}\n```")
    assert not grade(TASKS["x08"], "def check_transfer(b, a):\n    return 'ok'")


def test_extract_code_takes_the_last_fence():
    assert extract_code("bla ```python\nx=1\n``` and ```python\ny=2\n```") == "y=2"


def test_extract_number_handles_currency_and_separators():
    assert extract_number("that comes to £69,300.00") == 69300.0
