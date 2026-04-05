import sqlite3
import os
import sys

# add current directory to path
sys.path.append(os.getcwd())

from nimui import chat_manager

try:
    print("Attempting to add message to non-existent chat_id...")
    chat_manager.add_message("invalid-id-that-does-not-exist", "user", "this should fail")
    print("ERROR: Message added to non-existent chat_id (Foreign Key not enforced!)")
    sys.exit(1)
except sqlite3.IntegrityError as e:
    print(f"SUCCESS: Caught expected IntegrityError: {e}")
    sys.exit(0)
except Exception as e:
    print(f"ERROR: Caught unexpected exception: {type(e).__name__}: {e}")
    sys.exit(1)
