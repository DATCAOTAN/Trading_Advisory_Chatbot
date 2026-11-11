"""Operator-only benign probes in the offline G2.1 Debian guest. See the handoff."""

import errno
import hashlib
import json
import os
from pathlib import Path
import platform
import socket
import subprocess
import sys
import tempfile
import time


PYTHON = '/usr/bin/python3'
WORKER = 'g2worker'
FIXTURE = b'G2.1 benign input v1\n'
PASS, FAIL, UNKNOWN = 'PASS', 'FAIL', 'INCONCLUSIVE'


def evidence(probe, status, detail):
    print(f'{probe} {status} {detail}', flush=True)
    return status


def guest_network():
    links = {name for _, name in socket.if_nameindex()}
    routes = [route for family in ('-4', '-6') for route in json.loads(
        subprocess.check_output(['/usr/sbin/ip', '-j', family, 'route', 'show', 'table', 'all'], timeout=2)
    )]
    if links != {'lo'} or any(route.get('dst') == 'default' for route in routes):
        return evidence('A_GUEST', FAIL, 'unexpected interface or default route; no connect attempted')
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as client:
        client.settimeout(1)
        try:
            client.connect(('192.0.2.1', 443))
        except OSError as exc:
            status = PASS if exc.errno == errno.ENETUNREACH else UNKNOWN
            return evidence('A_GUEST', status, f'loopback only; no default route; connect errno={exc.errno}')
    return evidence('A_GUEST', FAIL, 'unexpected TCP connection')


def sharing_observation():
    mounts = {line.split(' - ', 1)[1].split()[0]
              for line in Path('/proc/self/mountinfo').read_text().splitlines()}
    shared = mounts & {'9p', 'virtiofs', 'cifs', 'smb3', 'drvfs', 'vboxsf', 'hgfs',
                       'fuse.vmhgfs-fuse', 'nfs', 'nfs4', 'fuse.sshfs'}
    docker = os.path.lexists('/run/docker.sock')
    if shared or docker:
        return evidence('B', FAIL, 'shared filesystem or Docker socket found')
    return evidence('B', UNKNOWN, 'common mount/socket indicators absent; operator must attest clean guest/media')


def denial(path, flags, expected):
    try:
        fd = os.open(path, flags)
    except OSError as exc:
        return (PASS if exc.errno == expected else UNKNOWN), exc.errno
    os.close(fd)
    return FAIL, 0


def counter(cgroup, name, key):
    return int(dict(line.split() for line in (cgroup / name).read_text().splitlines())[key])


def resource_probes(cgroup):
    quota = (cgroup / 'cpu.max').read_text().split()
    limits = {name: (cgroup / name).read_text().strip()
              for name in ('memory.max', 'memory.swap.max', 'memory.oom.group', 'pids.max')}
    if (len(quota) != 2 or not all(part.isdecimal() for part in quota)
            or int(quota[0]) * 4 != int(quota[1]) or limits != {
                'memory.max': '67108864', 'memory.swap.max': '0', 'memory.oom.group': '0', 'pids.max': '6',
            }):
        return [evidence('E_LIMITS', FAIL, 'cgroup limits differ; stress not attempted')]

    before = counter(cgroup, 'cpu.stat', 'nr_throttled')
    end = time.monotonic() + 1.5
    while time.monotonic() < end:
        pass
    throttled = counter(cgroup, 'cpu.stat', 'nr_throttled') - before
    cpu = evidence('E_CPU', PASS if throttled > 0 else UNKNOWN,
                   f'quota={quota[0]}/{quota[1]} throttled_delta={throttled}')

    before = counter(cgroup, 'pids.events', 'max')
    children = []
    rejected = False
    try:
        for _ in range(6):
            try:
                pid = os.fork()
            except BlockingIOError:
                rejected = True
                break
            if pid == 0:
                time.sleep(3)
                os._exit(0)
            children.append(pid)
        rejected_count = counter(cgroup, 'pids.events', 'max') - before
    finally:
        for pid in children:
            os.waitpid(pid, 0)
    tasks = evidence('E_TASKS', PASS if rejected and rejected_count > 0 else UNKNOWN,
                     f'limit=6 additional_started={len(children)} rejected={rejected} max_delta={rejected_count}')

    before = counter(cgroup, 'memory.events', 'oom_kill')
    child = subprocess.run([PYTHON, '-I', '-B', '-c',
                            'b = bytearray(96 * 1024 * 1024); b[::4096] = bytes(24576)'], timeout=5)
    kills = counter(cgroup, 'memory.events', 'oom_kill') - before
    mem = evidence('E_RAM', PASS if child.returncode == -9 and kills > 0 else
                   FAIL if child.returncode == 0 else UNKNOWN,
                   f'limit=64MiB swap=0 child_exit={child.returncode} oom_kill_delta={kills}')
    return [cpu, tasks, mem]


def inside(root, unit, uid, gid):
    status = dict(line.split(':', 1) for line in Path('/proc/self/status').read_text().splitlines())
    cgroup = f'/system.slice/{unit}.service'
    if (uid <= 0 or gid <= 0 or os.getresuid() != (uid,) * 3 or os.getresgid() != (gid,) * 3
            or not set(os.getgroups()) <= {gid} or status['NoNewPrivs'].strip() != '1'
            or any(int(status[key], 16) for key in ('CapInh', 'CapPrm', 'CapEff', 'CapBnd', 'CapAmb'))
            or Path('/proc/self/cgroup').read_text().strip() != f'0::{cgroup}'):
        evidence('D', FAIL, 'wrong worker identity, privilege boundary or cgroup; stress not attempted')
        return 1

    protected, code = denial(root / 'private' / 'marker', os.O_RDONLY, errno.EACCES)
    evidence('D', protected, f'dedicated uid={uid}; no capabilities; NoNewPrivs=1; private read errno={code}')
    input_file = root / 'input'
    with input_file.open('rb') as stream:
        payload = stream.read(len(FIXTURE) + 1)
    read_matches = payload == FIXTURE
    write, code = denial(input_file, os.O_WRONLY | os.O_APPEND, errno.EROFS)
    readonly = write if read_matches else FAIL
    digest = hashlib.sha256(payload).hexdigest() if read_matches else 'UNVERIFIED'
    evidence('C', readonly, f'fixture_match={read_matches}; write-open errno={code}; input_sha256={digest}')
    if protected != PASS or readonly != PASS:
        return 1 if FAIL in (protected, readonly) else 2
    results = resource_probes(Path('/sys/fs/cgroup' + cgroup))
    return 1 if FAIL in results else 2 if UNKNOWN in results else 0


def service(unit, runtime, command, *extra):
    options = ('User=' + WORKER, 'NoNewPrivileges=yes', 'CapabilityBoundingSet=',
               'CPUQuota=25%', 'MemoryMax=64M', 'MemorySwapMax=0', 'OOMPolicy=continue', 'TasksMax=6',
               f'RuntimeMaxSec={runtime}s', 'TimeoutStopSec=1s', 'KillMode=control-group',
               'ProtectHome=yes', 'ProtectSystem=strict', 'PrivateDevices=yes', 'WorkingDirectory=/', *extra)
    return subprocess.run(['/usr/bin/systemd-run', '--unit=' + unit, '--slice=system.slice',
                           '--wait', '--pipe', '--collect',
                           '--service-type=exec', *('--property=' + option for option in options),
                           '--', PYTHON, '-I', '-B', *command],
                          capture_output=True, text=True, timeout=runtime + 8, stdin=subprocess.DEVNULL,
                          env={'LC_ALL': 'C', 'SYSTEMD_LOG_TARGET': 'console'})


def timeout_status(result):
    started = 'TIME_READY' in result.stdout.splitlines()
    finished = 'TIME_COMPLETED' in result.stdout.splitlines()
    timed_out = 'Finished with result: timeout' in result.stderr.splitlines()
    if finished:
        return FAIL
    return PASS if started and result.returncode != 0 and timed_out else UNKNOWN


def main():
    import pwd

    if (os.geteuid() != 0 or platform.freedesktop_os_release().get('ID') != 'debian'
            or platform.freedesktop_os_release().get('VERSION_ID') != '13'
            or Path('/sys/class/dmi/id/sys_vendor').read_text().strip() != 'Microsoft Corporation'
            or Path('/sys/class/dmi/id/product_name').read_text().strip() != 'Virtual Machine'
            or Path('/proc/1/comm').read_text().strip() != 'systemd'
            or not Path('/sys/fs/cgroup/cgroup.controllers').is_file()):
        raise ValueError('not the supported guest environment')
    print(f'GUEST Debian 13; Python={platform.python_version()}; cgroup=v2', flush=True)
    network = guest_network()
    sharing = sharing_observation()
    if FAIL in (network, sharing):
        return 1
    if network != PASS:
        return 2
    account = pwd.getpwnam(WORKER)
    if (account.pw_uid <= 0 or account.pw_gid <= 0 or account.pw_shell not in ('/usr/sbin/nologin', '/bin/false')
            or set(os.getgrouplist(WORKER, account.pw_gid)) != {account.pw_gid}):
        evidence('D', FAIL, 'dedicated account is not non-login and primary-group only')
        return 1

    with tempfile.TemporaryDirectory(prefix='g2-probe-', dir='/run') as directory:
        root = Path(directory)
        root.chmod(0o755)
        (root / 'probe.py').write_bytes(Path(__file__).read_bytes())
        (root / 'probe.py').chmod(0o644)
        (root / 'input').write_bytes(FIXTURE)
        (root / 'input').chmod(0o666)  # Prove the mount denies writing, not just the file mode.
        (root / 'private').mkdir(mode=0o700)
        (root / 'private' / 'marker').touch()
        unit = root.name
        result = service(unit, 15, [str(root / 'probe.py'), '--inside', str(root), unit,
                                    str(account.pw_uid), str(account.pw_gid)], 'ReadOnlyPaths=' + str(root / 'input'))
        print(result.stdout, end='', flush=True)
        if result.returncode != 0:
            verdict = FAIL if any(line.split()[1:2] == [FAIL] for line in result.stdout.splitlines()) else UNKNOWN
            evidence('C_D_E', verdict, f'service exit={result.returncode}; no further workloads')
            return 1 if verdict == FAIL else 2
        timer = service(unit + '-timer', 2, ['-c', 'import time; print("TIME_READY", flush=True); '
                                             'time.sleep(12); print("TIME_COMPLETED", flush=True)'])
        timeout_result = 'Finished with result: timeout' in timer.stderr.splitlines()
        timed = evidence('E_TIME', timeout_status(timer),
                         f'limit=2s started={"TIME_READY" in timer.stdout.splitlines()} exit={timer.returncode}; '
                         f'timeout_result={timeout_result}')
    for probe in ('F', 'G', 'H'):
        evidence(probe, UNKNOWN, 'operator host evidence required')
    return 1 if timed == FAIL else 2  # Guest results alone never close G2.1.


if __name__ == '__main__':
    try:
        if sys.platform != 'linux':
            raise ValueError('Linux guest required')
        if len(sys.argv) == 6 and sys.argv[1] == '--inside':
            sys.exit(inside(Path(sys.argv[2]), sys.argv[3], int(sys.argv[4]), int(sys.argv[5])))
        if sys.argv[1:]:
            raise ValueError('unexpected arguments')
        sys.exit(main())
    except (OSError, ValueError, KeyError, subprocess.SubprocessError) as exc:
        evidence('HARNESS', UNKNOWN, f'{type(exc).__name__}; check guest prerequisites; no isolation verdict')
        sys.exit(2)
