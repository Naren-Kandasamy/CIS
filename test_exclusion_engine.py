import pytest
from unittest.mock import patch, AsyncMock
from shared.exclusion_engine import create_exclusion, reverse_exclusion, get_active_exclusions
from shared.exclusion_models import ExclusionRecord


def _record(**overrides):
    base = dict(
        exclusion_id="e1",
        fir_id="FIR1",
        accused_id="ACC1",
        exclusion_type="ruled_out",
        reason="Not the guy",
        officer_id="officer_1",
        date="2024-01-01T00:00:00",
    )
    base.update(overrides)
    return ExclusionRecord(**base)


@pytest.mark.anyio
@patch("shared.exclusion_engine.run_write", new_callable=AsyncMock)
@patch("shared.exclusion_engine.run_query", new_callable=AsyncMock)
async def test_create_exclusion_success(mock_query, mock_write):
    # 1st call: Accused exists, 2nd: FIR exists, 3rd: get_active_exclusions (none active)
    mock_query.side_effect = [
        [{"id": "ACC1"}],
        [{"id": "FIR1"}],
        [],
    ]
    await create_exclusion(_record())
    mock_write.assert_called_once()


@pytest.mark.anyio
@patch("shared.exclusion_engine.run_write", new_callable=AsyncMock)
@patch("shared.exclusion_engine.run_query", new_callable=AsyncMock)
async def test_create_exclusion_rejects_unknown_accused(mock_query, mock_write):
    mock_query.side_effect = [[]]  # Accused existence check returns nothing
    with pytest.raises(ValueError, match="No Accused node"):
        await create_exclusion(_record())
    mock_write.assert_not_called()


@pytest.mark.anyio
@patch("shared.exclusion_engine.run_write", new_callable=AsyncMock)
@patch("shared.exclusion_engine.run_query", new_callable=AsyncMock)
async def test_create_exclusion_rejects_unknown_fir(mock_query, mock_write):
    mock_query.side_effect = [[{"id": "ACC1"}], []]  # Accused ok, FIR missing
    with pytest.raises(ValueError, match="No FIR node"):
        await create_exclusion(_record())
    mock_write.assert_not_called()


@pytest.mark.anyio
@patch("shared.exclusion_engine.run_write", new_callable=AsyncMock)
@patch("shared.exclusion_engine.run_query", new_callable=AsyncMock)
async def test_create_exclusion_rejects_duplicate_active(mock_query, mock_write):
    # BUG FIX regression coverage: a second active exclusion for the same
    # (accused_id, fir_id) pair must be rejected, not silently create a
    # second edge that get_active_exclusions can't distinguish between.
    existing_row = {
        "accused_id": "ACC1",
        "exclusion": {
            "exclusion_id": "e_existing",
            "fir_id": "FIR1",
            "accused_id": "ACC1",
            "exclusion_type": "ruled_out",
            "reason": "already excluded",
            "officer_id": "officer_1",
            "date": "2024-01-01T00:00:00",
            "status": "active",
        },
    }
    mock_query.side_effect = [
        [{"id": "ACC1"}],
        [{"id": "FIR1"}],
        [existing_row],  # get_active_exclusions -- ACC1 already has an active exclusion
    ]
    with pytest.raises(ValueError, match="already exists"):
        await create_exclusion(_record(exclusion_id="e_new"))
    mock_write.assert_not_called()


@pytest.mark.anyio
@patch("shared.exclusion_engine.run_write", new_callable=AsyncMock)
@patch("shared.exclusion_engine.run_query", new_callable=AsyncMock)
async def test_reverse_exclusion_success(mock_query, mock_write):
    mock_query.return_value = [{"status": "active"}]
    await reverse_exclusion("e1", "officer_2", "Alibi turned out to be false")
    mock_write.assert_called_once()
    call_args = mock_write.call_args
    params = call_args[0][1]
    assert params["reversed_by"] == "officer_2"
    assert params["reversed_reason"] == "Alibi turned out to be false"


@pytest.mark.anyio
@patch("shared.exclusion_engine.run_write", new_callable=AsyncMock)
@patch("shared.exclusion_engine.run_query", new_callable=AsyncMock)
async def test_reverse_exclusion_rejects_unknown_id(mock_query, mock_write):
    mock_query.return_value = []
    with pytest.raises(ValueError, match="No exclusion with id"):
        await reverse_exclusion("nonexistent", "officer_2", "reason")
    mock_write.assert_not_called()


@pytest.mark.anyio
@patch("shared.exclusion_engine.run_write", new_callable=AsyncMock)
@patch("shared.exclusion_engine.run_query", new_callable=AsyncMock)
async def test_reverse_exclusion_rejects_double_reversal(mock_query, mock_write):
    # BUG FIX regression coverage: reversing an already-reversed exclusion a
    # second time must not silently overwrite the first reversal's audit
    # trail (reversed_by/reversed_reason/reversed_date).
    mock_query.return_value = [{"status": "reversed"}]
    with pytest.raises(ValueError, match="not active"):
        await reverse_exclusion("e1", "officer_3", "trying again")
    mock_write.assert_not_called()


@pytest.mark.anyio
@patch("shared.exclusion_engine.run_query", new_callable=AsyncMock)
async def test_get_active_exclusions_keyed_by_accused(mock_query):
    mock_query.return_value = [
        {
            "accused_id": "ACC1",
            "exclusion": {
                "exclusion_id": "e1",
                "fir_id": "FIR1",
                "accused_id": "ACC1",
                "exclusion_type": "ruled_out",
                "reason": "not the guy",
                "officer_id": "officer_1",
                "date": "2024-01-01T00:00:00",
                "status": "active",
            },
        }
    ]
    result = await get_active_exclusions("FIR1")
    assert "ACC1" in result
    assert result["ACC1"].exclusion_id == "e1"
