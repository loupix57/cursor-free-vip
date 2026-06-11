import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime
from account_manager import AccountManager

am = AccountManager()
now = datetime.now()
for a in am.get_saved_accounts():
    ca = a.get("created_at")
    age = (now - ca).days if ca else None
    if age is not None and age <= 3:
        has_pw = bool((a.get("password") or "").strip())
        print(f"age={age}d email={a['email']} password={'yes' if has_pw else 'no'}")
