# The body contract (`pact_adapters.programs`): `inputs` is given, keyed by the
# program's `takes:` names; the last expression is the answer.
import datetime

bought = datetime.date.fromisoformat(inputs["purchased-on"])
today = datetime.date.fromisoformat(inputs["today"])
days = (today - bought).days
{"verdict": "inside" if 0 <= days <= 30 else "outside", "days": days}
