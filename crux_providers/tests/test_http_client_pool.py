"""Unit tests for shared httpx client pool.

Covers:
- Same key (base_url, purpose) returns the same instance.
- Different purpose yields different instances.
- Different base_url yields different instances.
"""
from __future__ import annotations

from crux_providers.base.http import get_httpx_client, close_all_clients


def setup_function(_):
    # Ensure a clean slate for each test
    close_all_clients()


def teardown_function(_):
    close_all_clients()


def test_same_key_returns_same_instance():
    c1 = get_httpx_client("https://api.example.com", purpose="chat")
    c2 = get_httpx_client("https://api.example.com", purpose="chat")
    assert c1 is c2, "Expected pooled client instances to be identical for same key"


def test_different_purpose_returns_different_instances():
    c1 = get_httpx_client("https://api.example.com", purpose="chat")
    c2 = get_httpx_client("https://api.example.com", purpose="stream")
    assert c1 is not c2, "Different purposes should not share the same client instance"


def test_different_base_url_returns_different_instances():
    c1 = get_httpx_client("https://api.example.com", purpose="chat")
    c2 = get_httpx_client("https://api.other.com", purpose="chat")
    assert c1 is not c2, "Different base URLs should not share the same client instance"
