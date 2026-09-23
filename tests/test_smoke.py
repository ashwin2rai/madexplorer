import pytest

import madexplorer


def test_main_runs(capsys: pytest.CaptureFixture[str]) -> None:
    madexplorer.main()
    assert "madexplorer" in capsys.readouterr().out
