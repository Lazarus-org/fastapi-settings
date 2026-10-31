"""Bounded subprocess regressions using real Python imports and source objects."""

from __future__ import annotations

import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest


def _run(tmp_path: Path, script: str, **modules: str) -> None:
    for name, body in modules.items():
        (tmp_path / f"{name}.py").write_text(textwrap.dedent(body), encoding="utf-8")
    env = os.environ.copy()
    env.pop("FASTAPI_SETTINGS_MODULE", None)
    env["PYTHONPATH"] = os.pathsep.join(
        (str(tmp_path), str(Path(__file__).resolve().parents[2] / "src"))
    )
    result = subprocess.run(
        [sys.executable, "-c", textwrap.dedent(script)],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_direct_import_versus_proxy_initialization(tmp_path):
    _run(
        tmp_path,
        """
        import os, sys, threading
        import support
        from fastapi_settings import settings, SettingsInitializationError
        from fastapi_settings._loader import _load_module
        os.environ['FASTAPI_SETTINGS_MODULE'] = 'app_settings'
        errors = []
        def direct():
            import app_settings
        def profile(frame, event, arg):
            if event == 'call' and frame.f_code is _load_module.__code__:
                support.proxy_loading.set()
        def reader():
            # Observe the real loader entry without replacing the import path.
            sys.setprofile(profile)
            try:
                settings.EARLY
            except SettingsInitializationError:
                errors.append('reader')
            finally:
                sys.setprofile(None)
        a = threading.Thread(target=direct, daemon=True)
        b = threading.Thread(target=reader, daemon=True)
        a.start()
        assert support.entered.wait(5)
        b.start()
        assert support.proxy_loading.wait(5)
        support.resume.set()
        a.join(5); b.join(5)
        assert not a.is_alive() and not b.is_alive(), 'initialization deadlock'
        assert errors == ['reader']
        assert support.rejected and support.partial_snapshot is None
        assert settings.EARLY and settings.LATE == 42
        """,
        support="""
        import threading
        entered = threading.Event()
        resume = threading.Event()
        proxy_loading = threading.Event()
        rejected = False
        partial_snapshot = 'not checked'
        """,
        app_settings="""
        import support
        EARLY = True
        support.entered.set()
        assert support.resume.wait(5)
        from fastapi_settings import settings, SettingsInitializationError
        try:
            settings.EARLY
        except SettingsInitializationError:
            support.rejected = True
            support.partial_snapshot = settings._values
        LATE = 42
        """,
    )


@pytest.mark.parametrize("object_mode", [False, True])
def test_recursive_direct_import_rejects_partial_snapshot_and_recovers(
    tmp_path, object_mode
):
    final = "SETTINGS = {'EARLY': True, 'LATE': 42}" if object_mode else "LATE = 42"
    early = "" if object_mode else "EARLY = True"
    _run(
        tmp_path,
        """
        import os
        os.environ['FASTAPI_SETTINGS_MODULE'] = 'app_settings'
        import app_settings
        from fastapi_settings import settings, SettingsInitializationError
        assert isinstance(app_settings.failure, SettingsInitializationError)
        assert app_settings.partial_snapshot is None
        assert settings.EARLY and settings.LATE == 42
        """,
        app_settings=f"""
        {early}
        from fastapi_settings import settings, SettingsInitializationError
        try:
            settings.EARLY
        except SettingsInitializationError as exc:
            failure = exc
            partial_snapshot = settings._values
        else:
            raise AssertionError('partial settings were accepted')
        {final}
        """,
    )


def test_concurrent_first_access_publishes_exactly_one_snapshot(tmp_path):
    _run(
        tmp_path,
        """
        import threading
        from concurrent.futures import ThreadPoolExecutor
        import support
        from fastapi_settings import create_settings
        proxy = create_settings(module='app_settings')
        gate = threading.Barrier(12)
        def reader():
            gate.wait(5)
            return proxy.VALUE
        with ThreadPoolExecutor(max_workers=12) as pool:
            tasks = [pool.submit(reader) for _ in range(12)]
            assert support.started.wait(5)
            support.resume.set()
            values = [task.result(5) for task in tasks]
        assert support.imports == 1 and support.snapshots == 1
        assert all(value is support.value for value in values)
        assert proxy.VALUE is support.value and support.snapshots == 1
        """,
        support="""
        import threading
        started = threading.Event()
        resume = threading.Event()
        imports = 0
        snapshots = 0
        value = object()
        """,
        app_settings="""
        from collections.abc import Mapping
        import support
        support.imports += 1
        class Config(Mapping):
            def __len__(self): return 1
            def __iter__(self): return iter(('VALUE',))
            def __getitem__(self, key):
                support.snapshots += 1
                support.started.set()
                assert support.resume.wait(5)
                return support.value
        SETTINGS = Config()
        """,
    )


@pytest.mark.parametrize("threaded", [False, True])
def test_cross_proxy_import_cycles_fail_and_recover(tmp_path, threaded):
    _run(
        tmp_path,
        f"""
        import threading
        import support
        from fastapi_settings import create_settings, SettingsInitializationError
        support.first = create_settings(module='first_settings')
        support.second = create_settings(module='second_settings')
        support.threaded = {threaded!r}
        errors = []
        def read(proxy):
            try: proxy.VALUE
            except SettingsInitializationError: errors.append(True)
        if support.threaded:
            threads = [threading.Thread(target=read, args=(proxy,), daemon=True)
                       for proxy in (support.first, support.second)]
            for thread in threads: thread.start()
            for thread in threads: thread.join(5)
            assert not any(thread.is_alive() for thread in threads)
            assert len(errors) == 2
        else:
            read(support.first)
            assert len(errors) == 1
        assert support.first._values is None and support.second._values is None
        support.cycle = False
        assert support.first.VALUE == 1 and support.second.VALUE == 2
        """,
        support="""
        import threading
        barrier = threading.Barrier(2)
        seen = set()
        cycle = True
        """,
        first_settings="""
        import support
        if support.cycle:
            if support.threaded and 'first' not in support.seen:
                support.seen.add('first')
                support.barrier.wait(5)
            support.second.VALUE
        VALUE = 1
        """,
        second_settings="""
        import support
        if support.cycle:
            if support.threaded and 'second' not in support.seen:
                support.seen.add('second')
                support.barrier.wait(5)
            support.first.VALUE
        VALUE = 2
        """,
    )


@pytest.mark.parametrize("identical", [False, True])
def test_concurrent_public_configuration(tmp_path, identical):
    _run(
        tmp_path,
        f"""
        import threading
        from concurrent.futures import ThreadPoolExecutor
        from fastapi_settings import configure, settings, SettingsAlreadyConfiguredError
        sources = [{{'VALUE': index}} for index in range(12)]
        gate = threading.Barrier(12)
        def select(index):
            gate.wait(5)
            try:
                configure(settings_object=sources[0 if {identical!r} else index])
                return index, settings.VALUE
            except SettingsAlreadyConfiguredError:
                return None
        with ThreadPoolExecutor(max_workers=12) as pool:
            results = list(pool.map(select, range(12)))
        winners = [result for result in results if result is not None]
        if {identical!r}:
            assert len(winners) == 12 and all(value == 0 for _, value in winners)
        else:
            assert len(winners) == 1
            assert winners[0][0] == winners[0][1] == settings.VALUE
        """,
    )


def test_missing_module_can_be_retried_without_changing_source(tmp_path):
    _run(
        tmp_path,
        """
        import importlib
        from pathlib import Path
        from fastapi_settings import configure, settings, SettingsModuleImportError
        configure(module='created_later')
        try:
            settings.VALUE
        except SettingsModuleImportError as exc:
            assert isinstance(exc.__cause__, ModuleNotFoundError)
        else: raise AssertionError('missing import succeeded')
        assert settings._values is None
        Path('created_later.py').write_text('VALUE = 42\\n', encoding='utf-8')
        importlib.invalidate_caches()
        configure(module='created_later')
        assert settings.VALUE == 42
        """,
    )


def test_failure_releases_waiters_even_for_base_exception(tmp_path):
    _run(
        tmp_path,
        """
        import threading
        from collections.abc import Mapping
        from fastapi_settings import create_settings
        started, resume, waiting = (threading.Event() for _ in range(3))
        class Config(Mapping):
            attempts = 0
            def __len__(self): return 1
            def __iter__(self): return iter(('VALUE',))
            def __getitem__(self, key):
                self.attempts += 1
                if self.attempts == 1:
                    started.set()
                    assert resume.wait(5)
                    raise KeyboardInterrupt
                return 42
        source = Config()
        proxy = create_settings(settings_object=source)
        original_wait = proxy._lock.wait
        def observed_wait(*args, **kwargs):
            waiting.set()
            return original_wait(*args, **kwargs)
        proxy._lock.wait = observed_wait
        results = []
        def read():
            try: results.append(proxy.VALUE)
            except KeyboardInterrupt: results.append('failed')
        a = threading.Thread(target=read, daemon=True)
        b = threading.Thread(target=read, daemon=True)
        a.start(); assert started.wait(5)
        b.start(); assert waiting.wait(5)
        resume.set()
        a.join(5); b.join(5)
        assert not a.is_alive() and not b.is_alive()
        assert sorted(results, key=str) == [42, 'failed']
        assert source.attempts == 2 and proxy.VALUE == 42
        """,
    )


def test_object_source_import_lock_cycle_does_not_wait(tmp_path):
    _run(
        tmp_path,
        """
        import threading
        from collections.abc import Mapping
        import support
        from fastapi_settings import create_settings
        class Config(Mapping):
            def __len__(self): return 1
            def __iter__(self): return iter(('VALUE',))
            def __getitem__(self, key):
                support.resume.set()
                import helper_module
                return 42
        support.proxy = create_settings(settings_object=Config())
        results = []
        def importer():
            import helper_module
            results.append('imported')
        def reader(): results.append(support.proxy.VALUE)
        a = threading.Thread(target=importer, daemon=True)
        b = threading.Thread(target=reader, daemon=True)
        a.start(); assert support.entered.wait(5)
        b.start()
        a.join(5); b.join(5)
        assert not a.is_alive() and not b.is_alive()
        assert support.rejected and 42 in results and 'imported' in results
        assert support.proxy.VALUE == 42
        """,
        support="""
        import threading
        entered, resume = threading.Event(), threading.Event()
        rejected = False
        """,
        helper_module="""
        import support
        from fastapi_settings import SettingsInitializationError
        support.entered.set()
        assert support.resume.wait(5)
        try: support.proxy.VALUE
        except SettingsInitializationError: support.rejected = True
        else: raise AssertionError('importing caller waited on busy proxy')
        """,
    )


def test_acyclic_cross_proxy_initialization_is_supported(tmp_path):
    _run(
        tmp_path,
        """
        import support
        from fastapi_settings import create_settings
        support.second = create_settings(module='second_settings')
        first = create_settings(module='first_settings')
        assert first.VALUE == 43 and support.second.VALUE == 42
        """,
        support="",
        first_settings="import support\nVALUE = support.second.VALUE + 1",
        second_settings="VALUE = 42",
    )


def test_configuration_during_object_loading_does_not_block_or_change_source(tmp_path):
    _run(
        tmp_path,
        """
        import threading
        from collections.abc import Mapping
        from fastapi_settings import configure, settings, SettingsAlreadyConfiguredError
        started, resume = threading.Event(), threading.Event()
        class Config(Mapping):
            def __len__(self): return 1
            def __iter__(self): return iter(('VALUE',))
            def __getitem__(self, key):
                started.set()
                assert resume.wait(5)
                return 42
        source = Config()
        configure(settings_object=source)
        results = []
        thread = threading.Thread(target=lambda: results.append(settings.VALUE), daemon=True)
        thread.start(); assert started.wait(5)
        configure(settings_object=source)
        try: configure(settings_object={'VALUE': 100})
        except SettingsAlreadyConfiguredError: pass
        else: raise AssertionError('conflicting source accepted')
        assert settings._values is None
        resume.set(); thread.join(5)
        assert not thread.is_alive() and results == [42]
        """,
    )
