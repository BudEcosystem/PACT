"""Decide whether a purchase is inside the refund window."""
import sys
from datetime import date, timedelta

purchased = date.fromisoformat(sys.argv[1])
print("inside" if date.today() - purchased <= timedelta(days=30) else "outside")
