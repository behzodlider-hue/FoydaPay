import os
import sys
from pathlib import Path

os.environ["FOYDAPAY_LLM"] = "0"  # tests never call a paid API
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402

from app.toolbox import Session  # noqa: E402


@pytest.fixture
def s() -> Session:
    return Session()
