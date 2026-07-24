import os
from pathlib import Path
Path('./knowledge_base/.trigger_reindex').touch()
print('RAG reindex triggered.')
