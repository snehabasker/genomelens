import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ["CACHE_DB"] = str(Path(tempfile.mkdtemp()) / "test_cache.db")
