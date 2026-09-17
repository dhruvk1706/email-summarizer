from gmail import get_current_history_id
from state import save_history_id


history_id = get_current_history_id()

save_history_id(history_id)

print(f"Initialized Gmail history ID: {history_id}")