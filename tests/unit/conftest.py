import json

import pytest
from mock_webhook import MockWebhook


@pytest.fixture
def webhook():
    mock = MockWebhook().start()
    yield mock
    mock.stop()


@pytest.fixture
def write_json(tmp_path):
    def write(name, data):
        path = tmp_path / name
        path.write_text(json.dumps(data, ensure_ascii=False))
        return path

    return write
