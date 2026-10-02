"""Regression checks from the review following version 3.8.6.

File: tests/test_review_after_386.py

Tests exercise the behavior described below using pure helper calls or
Home Assistant fixtures as appropriate. Device/service doubles keep tests
local and repeatable; they do not prove real hardware response timing.
Assertions and test names describe the expected result of each scenario.
"""

import asyncio
from copy import deepcopy
from unittest.mock import AsyncMock

import pytest
from freezegun.api import real_monotonic
from homeassistant.exceptions import HomeAssistantError

from tests.test_irrigation import _controller


@pytest.mark.parametrize("action", ["watering", "fertilizing", "mowing", "undo"])
@pytest.mark.parametrize("cancellations", [1, 2, 3])
async def test_maintenance_waits_for_durable_write_after_repeated_cancellation(
    hass, monkeypatch, action, cancellations
):
    monkeypatch.setattr(asyncio.get_running_loop(), "time", real_monotonic)
    c = _controller(hass)
    coordinator = c.coordinator
    if action == "undo":
        await coordinator.async_mark_fertilized()
    operations = {
        "watering": lambda: coordinator.async_mark_watered(5),
        "fertilizing": coordinator.async_mark_fertilized,
        "mowing": coordinator.async_mark_mowed,
        "undo": coordinator.async_undo_last_action,
    }
    entered, release = asyncio.Event(), asyncio.Event()
    persisted = None
    write_cancelled = False

    async def save(data):
        nonlocal persisted, write_cancelled
        entered.set()
        try:
            await release.wait()
        except asyncio.CancelledError:
            write_cancelled = True
            raise
        persisted = deepcopy(data)

    coordinator._store.async_save = AsyncMock(side_effect=save)
    task = asyncio.create_task(operations[action]())
    await asyncio.wait_for(entered.wait(), 1)
    for _ in range(cancellations):
        task.cancel()
        await asyncio.sleep(0)
    pending = not task.done()
    locked = coordinator._state_lock.locked()
    release.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert pending, "Cancellation must not release a pending storage transaction"
    assert locked
    assert not write_cancelled
    assert persisted == c.state.as_dict()
    assert len(c.state.maintenance_history) == (0 if action == "undo" else 1)


@pytest.mark.parametrize("failure", [OSError, HomeAssistantError])
@pytest.mark.parametrize("cancellations", [0, 1, 3])
async def test_failed_maintenance_write_rolls_back_before_retry(
    hass, monkeypatch, failure, cancellations
):
    monkeypatch.setattr(asyncio.get_running_loop(), "time", real_monotonic)
    c = _controller(hass)
    before = deepcopy(c.state.as_dict())
    entered, release = asyncio.Event(), asyncio.Event()

    async def save(data):
        entered.set()
        await release.wait()
        raise failure("disk failure")

    c.coordinator._store.async_save = AsyncMock(side_effect=save)
    task = asyncio.create_task(c.coordinator.async_mark_watered(5))
    await asyncio.wait_for(entered.wait(), 1)
    for _ in range(cancellations):
        task.cancel()
        await asyncio.sleep(0)
    release.set()
    expected = asyncio.CancelledError if cancellations else HomeAssistantError
    with pytest.raises(expected):
        await task
    assert c.state.as_dict() == before
    assert not c.coordinator._state_lock.locked()
    c.coordinator._store.async_save = AsyncMock()
    await c.coordinator.async_mark_watered(5)
    assert len(c.state.water_usage) == 1
    assert len(c.state.maintenance_history) == 1


async def test_cancelled_maintenance_serializes_a_following_action(hass, monkeypatch):
    monkeypatch.setattr(asyncio.get_running_loop(), "time", real_monotonic)
    c = _controller(hass)
    entered, release = asyncio.Event(), asyncio.Event()
    persisted = []

    async def save(data):
        entered.set()
        await release.wait()
        persisted.append(deepcopy(data))

    c.coordinator._store.async_save = AsyncMock(side_effect=save)
    first = asyncio.create_task(c.coordinator.async_mark_watered(5))
    await asyncio.wait_for(entered.wait(), 1)
    first.cancel()
    await asyncio.sleep(0)
    first.cancel()
    await asyncio.sleep(0)
    second = asyncio.create_task(c.coordinator.async_mark_fertilized())
    await asyncio.sleep(0)
    calls_before_release = c.coordinator._store.async_save.call_count
    release.set()
    with pytest.raises(asyncio.CancelledError):
        await first
    await second
    assert calls_before_release == 1
    assert len(persisted) == 2
    assert len(persisted[0]["maintenance_history"]) == 1
    assert len(persisted[1]["maintenance_history"]) == 2
    assert persisted[-1] == c.state.as_dict()
