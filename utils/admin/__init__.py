"""The admin dashboard: a read-only view over what Kaiacord writes.

Runs as its own process (`tools/maintenance/kaia_admin.py`), never inside the
bot: parsing the log and walking `memory/` and `knowledge_base/` holds the GIL
for seconds at a time, and the bot's voice thread needs a frame every 20 ms.
Every number it shows is read from a file named beside it.
"""
