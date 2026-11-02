"""The fakes must stay in step with the ports they stand in for."""

import inspect

import pytest

from app.ports.callback_client import ICallbackClient
from app.ports.file_store import IFileStore
from app.ports.llm_client import ILlmClient
from app.ports.tracking_repo import ITrackingRepository, TrackingStatus
from tests.fakes import FakeCallbackClient, FakeFileStore, FakeLlmClient, FakeTrackingRepository


@pytest.mark.parametrize(
    "port,fake",
    [
        (IFileStore, FakeFileStore),
        (ILlmClient, FakeLlmClient),
        (ICallbackClient, FakeCallbackClient),
        (ITrackingRepository, FakeTrackingRepository),
    ],
)
def test_fake_matches_port_signatures(port, fake):
    for name, member in inspect.getmembers(port, inspect.isfunction):
        if name.startswith("_"):
            continue
        assert hasattr(fake, name), f"{fake.__name__} lacks {name}"
        assert inspect.signature(getattr(fake, name)) == inspect.signature(member), name
        assert inspect.iscoroutinefunction(getattr(fake, name)) == inspect.iscoroutinefunction(member)


def test_completed_and_failed_are_terminal_statuses():
    assert TrackingStatus.COMPLETED.is_terminal and TrackingStatus.FAILED.is_terminal
    assert not TrackingStatus.RECEIVED.is_terminal and not TrackingStatus.PROCESSING.is_terminal
