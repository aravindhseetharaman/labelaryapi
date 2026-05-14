import pathlib
import pytest
from fastapi.testclient import TestClient
from app.main import app

SAMPLES_DIR = pathlib.Path(__file__).parent.parent / "samples"
BIN_FILE = SAMPLES_DIR / "shelfitem.bin"

RAW_BIN_TEXT = (
    "V D 100\n"
    "T 1 (0,0,2,2) 490 0 l\n"
    "ULTRA_FONT C84 (8,0,0) 520 15 8.99\n"
    "T 1 520 84 Just For Men\n"
    "T 1 520 106 hair colorant\n"
    "T 1 520 128 drk brown/black\n"
    "B F5-(3:6) 520 228 31 210600008993\n"
    "J RIGHT\n"
    "T 0 635 228 21-06-000\n"
    "END\n"
    "\n"
    "\n"
    "! 0 100 246 1\n"
    "P 200\n"
    "V L\n"
    "V D 100\n"
    "T 1 520 97 END OF BATCH\n"
    "T 1 520 122 17/04/26 12:05\n"
    "T 1 520 147 ALL ACCESS\n"
    "END\n"
)


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="module")
def bin_bytes():
    return BIN_FILE.read_bytes()


@pytest.fixture(scope="module")
def bin_path():
    return BIN_FILE
