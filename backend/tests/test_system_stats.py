"""
System Stats Service Tests.
Covers cgroup limit parsing, snapshot shape, and ring-buffer bounding.
"""

from unittest import mock

import pytest

from backend.app.services import system_stats


class TestCgroupParsing:
    def test_memory_limit_v2(self, monkeypatch):
        monkeypatch.setattr(
            system_stats,
            "_read_int_file",
            lambda p: 536870912 if p == system_stats.CGROUP_V2_MEM else None,
        )
        assert system_stats.get_memory_limit_bytes() == 536870912

    def test_memory_limit_v1(self, monkeypatch):
        def fake_read(path):
            if path == system_stats.CGROUP_V1_MEM:
                return 536870912
            return None

        monkeypatch.setattr(system_stats, "_read_int_file", fake_read)
        assert system_stats.get_memory_limit_bytes() == 536870912

    def test_memory_unlimited_when_v1_reports_huge(self, monkeypatch):
        # cgroup v1 reports a near-max int when unlimited; v2 reports "max" -> None
        def fake_read(path):
            if path == system_stats.CGROUP_V1_MEM:
                return 1 << 62
            return None

        monkeypatch.setattr(system_stats, "_read_int_file", fake_read)
        assert system_stats.get_memory_limit_bytes() is None

    def test_memory_none_when_missing(self, monkeypatch):
        monkeypatch.setattr(system_stats, "_read_int_file", lambda p: None)
        assert system_stats.get_memory_limit_bytes() is None

    def test_cpu_limit_v2(self, monkeypatch):
        # 10000us quota per 100000us period = 0.1 CPU (Render free tier)
        def fake_open(path, *args, **kw):
            import io

            if path == system_stats.CGROUP_V2_CPU:
                return io.StringIO("10000 100000\n")
            raise OSError("missing")

        monkeypatch.setattr("builtins.open", fake_open)
        monkeypatch.setattr(system_stats, "_read_int_file", lambda p: None)
        assert system_stats.get_cpu_limit() == pytest.approx(0.1)

    def test_cpu_limit_v1(self, monkeypatch):
        monkeypatch.setattr("builtins.open", mock.mock_open(read_data="max 100000"))

        def fake_read(path):
            if path == system_stats.CGROUP_V1_CPU_QUOTA:
                return 50000
            if path == system_stats.CGROUP_V1_CPU_PERIOD:
                return 100000
            return None

        monkeypatch.setattr(system_stats, "_read_int_file", fake_read)
        assert system_stats.get_cpu_limit() == pytest.approx(0.5)

    def test_effective_core_count_capped(self, monkeypatch):
        monkeypatch.setattr(system_stats, "get_cpu_limit", lambda: 0.1)
        assert system_stats.get_effective_core_count() == 1

    def test_effective_core_count_unlimited(self, monkeypatch):
        monkeypatch.setattr(system_stats, "get_cpu_limit", lambda: None)
        import os

        assert system_stats.get_effective_core_count() == (os.cpu_count() or 1)


class TestCollectStats:
    @pytest.fixture(autouse=True)
    def reset_cache(self):
        with system_stats._cache_lock:
            system_stats._cache.update({"stats": None, "at": 0.0})
        yield

    def test_snapshot_shape(self):
        stats = system_stats.collect_stats(force=True)
        assert "cpu" in stats and "memory" in stats and "disk" in stats
        assert "process" in stats and "workers" in stats and "mongodb" in stats
        assert stats["memory"]["process_rss_mb"] > 0
        assert stats["cpu"]["core_count_effective"] >= 1
        assert stats["process"]["thread_count"] >= 1
        # Open FDs: Unix reports a number; Windows falls back to handles or None
        assert stats["process"]["open_fds"] is None or stats["process"]["open_fds"] > 0

    def test_cache_hit(self):
        first = system_stats.collect_stats(force=True)
        second = system_stats.collect_stats()  # within TTL
        assert first["timestamp"] == second["timestamp"]

    def test_ring_buffer_bounded(self):
        # Simulate overfilling the ring buffer
        for i in range(system_stats.HISTORY_MAXLEN + 20):
            with system_stats._hist_lock:
                system_stats._history.append(
                    {"ts": i, "cpu_percent": 1.0, "mem_percent": 1.0}
                )
        history = system_stats.get_history()
        assert len(history) <= system_stats.HISTORY_MAXLEN
