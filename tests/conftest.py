import sys
from pathlib import Path

# Allow "import stock_advisor" when tests are run from anywhere (e.g. `pytest tests/`).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
