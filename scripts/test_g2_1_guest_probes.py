"""Host-side tests of evidence handling; no Hyper-V or guest workload."""

import errno
import os
import subprocess
from unittest.mock import patch

import pytest

from scripts import g2_1_guest_probes as probes


@pytest.mark.parametrize(('stdout', 'stderr', 'exit_code', 'expected'), [
    ('TIME_READY', 'Finished with result: timeout', 1, probes.PASS),
    ('TIME_READY', 'Finished with result: exit-code', 1, probes.UNKNOWN),
    ('', 'Finished with result: timeout', 1, probes.UNKNOWN),
    ('TIME_READY', 'Finished with result: timeout', 0, probes.UNKNOWN),
    ('TIME_READY\nTIME_COMPLETED', 'Finished with result: timeout', 1, probes.FAIL),
])
def test_timeout_requires_started_workload_and_systemd_timeout(stdout, stderr, exit_code, expected):
    assert probes.timeout_status(subprocess.CompletedProcess([], exit_code, stdout, stderr)) == expected


@pytest.mark.parametrize(('error', 'expected'), [
    (errno.EROFS, probes.PASS), (errno.EACCES, probes.UNKNOWN), (errno.ENOENT, probes.UNKNOWN),
])
def test_readonly_mount_requires_exact_denial(error, expected):
    with patch.object(os, 'open', side_effect=OSError(error, 'fixture')):
        assert probes.denial('/fixture', os.O_WRONLY, errno.EROFS) == (expected, error)


def test_write_open_is_not_a_pass(tmp_path):
    fixture = tmp_path / 'input'
    fixture.write_bytes(probes.FIXTURE)
    assert probes.denial(fixture, os.O_WRONLY | os.O_APPEND, errno.EROFS) == (probes.FAIL, 0)
    assert fixture.read_bytes() == probes.FIXTURE


def test_unexpected_network_does_not_attempt_connection():
    with (patch.object(probes.socket, 'if_nameindex', return_value=[(1, 'lo'), (2, 'eth0')]),
          patch.object(probes.subprocess, 'check_output', return_value=b'[]'),
          patch.object(probes.socket, 'socket') as connect):
        assert probes.guest_network() == probes.FAIL
    connect.assert_not_called()


def test_limit_mismatch_does_not_attempt_load(tmp_path):
    for name, value in {'cpu.max': 'max 100000', 'memory.max': '67108864', 'memory.swap.max': '0',
                        'memory.oom.group': '0', 'pids.max': '6'}.items():
        (tmp_path / name).write_text(value)
    with patch.object(probes.subprocess, 'run') as child:
        assert probes.resource_probes(tmp_path) == [probes.FAIL]
    child.assert_not_called()


def test_service_binds_non_root_worker_and_resource_limits():
    with patch.object(probes.subprocess, 'run') as run:
        probes.service('g2-probe-test', 2, ['-c', 'pass'])
    argv = run.call_args.args[0]
    assert {f'--property={option}' for option in (
        'User=g2worker', 'NoNewPrivileges=yes', 'CapabilityBoundingSet=', 'MemoryMax=64M',
        'MemorySwapMax=0', 'CPUQuota=25%', 'TasksMax=6', 'RuntimeMaxSec=2s', 'KillMode=control-group',
    )} <= set(argv)
    assert argv[-6:] == ['--', '/usr/bin/python3', '-I', '-B', '-c', 'pass']
    assert run.call_args.kwargs['timeout'] == 10
