#!/usr/bin/env

import argparse
import time
import plumbum
import sys
import statistics
import os
import collections
from plumbum import local, SshMachine


ROUNDS = 5
REPETITIONS_PER_ROUND = 100
WARMUP_RUNS = 5
ON_VM_WORKLOAD_PATH = '~/lsm-perf-workload'
ON_VM_WORKLOAD_CPU = 0
HOST_PORT = 5555
SSH_MAX_RETRY = 5

# TODO(renauld): make generic
QEMU_AFFINITY_PATH = '../qemu-affinity/qemu_affinity.py'


"""Holds the assignment of physical CPUs"""
CpuAllocation = collections.namedtuple('CpuAllocation',
                                       ('qemu_sys', 'host_kvm0', 'host_kvm1'))


def main(args):
    if args.cpu:
        print(('Specific CPU allocation provided. Remember to start your '
               'machine with `isolcpus=%s`.') % ','.join(map(str, args.cpu)))
        alloc = CpuAllocation(qemu_sys=args.cpu[0], host_kvm0=args.cpu[1],
                              host_kvm1=args.cpu[2])
    else:
        print('No dedicated CPUs provided.')
        alloc = None

    try:
        init_output_file(args.out)
        for round in range(ROUNDS):
            print('Starting round %d' % round)
            for kernel in args.kernels:
                results = evaluate_kernel(
                    kernel_path=kernel.name,
                    filesystem_img_path=args.image.name,
                    workload_path=args.workload.name,
                    keyfile=args.key.name,
                    cpus=alloc,
                )
                write_results_to_file(args.out, kernel.name, round, results)
    except KeyboardInterrupt:
        print('\nExit prematurely')
    finally:
        args.out.close()
    return 0


def evaluate_kernel(kernel_path, filesystem_img_path, workload_path,
                    keyfile, cpus):
    """Start a VM with the kernel and evaluates its performances

    :param kernel_path: Path of the kernel's bzImage
    :param filesystem_img_path: Path of the filesystem image (.img)
    :param workload_path: Path of the compiled workload program
    :param keyfile: Path of the rsa key that is authorized on the image
    :param cpus: CpuAllocation for qemu and the vm's cores,
                 or None to not assign CPUs
    :return: time measurements printed by each run of the workload
    :rtype: list[int]
    """
    results = []
    name = os.path.basename(kernel_path)
    isolcpus = [ON_VM_WORKLOAD_CPU] if cpus else []
    print_eta(name, info='connecting')

    with VM(kernel_path, filesystem_img_path, keyfile, cpus, isolcpus) as vm:
        vm.scp_to(workload_path, ON_VM_WORKLOAD_PATH)

        work_cmd = vm.ssh[ON_VM_WORKLOAD_PATH]
        if cpus:
            work_cmd = vm.ssh['taskset'][1 << ON_VM_WORKLOAD_CPU, work_cmd]

        print_eta(name, info='Running warm up')
        for _ in range(WARMUP_RUNS):
            work_cmd()

        for i in range(REPETITIONS_PER_ROUND):
            results.append(int(work_cmd().strip()))
            percentage = (i + 1) * 100 / REPETITIONS_PER_ROUND
            print_eta(name, info='%d%%' % percentage)

        vm.ssh.path(ON_VM_WORKLOAD_PATH).delete()

    stats = ('\taverage=%d, stdev=%d' %
             (statistics.mean(results), statistics.stdev(results)))
    print_eta(name, info=stats)
    print()
    return results


class VM:
    """
    Manage a qemu-system virtual machine.

    It will be started with `__init__` and the ssh connection will be
    established with `__enter__`, so any ssh operation should be done
    inside a `with` block.

    A CPU allocation can also be provided, to bind the cores of the
    virtual machine to physical cores.

    :ivar ssh: plumbum.SshMachine object, useful to run commands on
               the VM. It should only be used inside a `with` block.
    :ivar process: popen process of qemu, useful to send signals
                   or input to qemu.

    :example:
        with VM('bzImage', 'debian.img', '~/.ssh/id_rsa') as vm:
            vm.shh['ls']
    """

    def __init__(self, kernel_path, filesystem_img_path, keyfile,
                 cpu_allocation=None, isolcpus=[]):
        """Start the qemu VM (non blocking)

        :param kernel_path: Path of the kernel's bzImage
        :param filesystem_img_path: Path of the filesystem image (.img)
        :param keyfile: Path of rsa key that is authorized on the image
        :param cpu_allocation: CpuAllocation for qemu and the vm's cores,
                               or None to not assign CPUs
        :param isolcpus: list of CPU ID that should be isolated at boot time
        """
        qemu_args = VM.__construct_qemu_args(
            kernel_path=kernel_path,
            filesystem_img_path=filesystem_img_path,
            isolcpus=isolcpus)
        self.process = local['qemu-system-x86_64'].popen(qemu_args)
        self.ssh = None
        self.key = keyfile
        if cpu_allocation:
            VM.__qemu_affinity_setup(self.process.pid, cpu_allocation)

    def __enter__(self):
        """Initialize the ssh connection (blocks until success)"""
        err = None
        for _ in range(SSH_MAX_RETRY):
            time.sleep(1)
            try:
                self.ssh = SshMachine(
                    '127.0.0.1', user='root', port=HOST_PORT, keyfile=self.key)
                break
            except (EOFError, plumbum.machines.session.SSHCommsError) as e:
                err = e
                continue
        else:  # Reached maximum retries
            raise VMException(
                'SSH connection failed after too many retries', err)
        return self

    def __exit__(self, type, value, traceback):
        """Stop the SSH connection and the VM"""
        if self.ssh is not None:
            self.ssh.close()
            self.ssh = None
        self.process.terminate()

    def scp_to(self, src_local, dst_remote):
        """Send a file from the host to the VM

        :param src_local: local path of the file to send
        :param dst_remote: destination path on the vm
        :raises ValueError: when the ssh connection is not established,
                            i.e. when not used inside a `with` block
        """
        if self.ssh is None:
            raise VMException(
                '`VM.scp_to` must be used with an established SSH connection, '
                'i.e. inside a `with` block.')
        src = local.path(src_local)
        dst = self.ssh.path(dst_remote)
        plumbum.path.utils.copy(src, dst)

    @staticmethod
    def __construct_qemu_args(kernel_path, filesystem_img_path, isolcpus=[]):
        """Qemu arguments similar to what `vm start` produces"""
        kernel_opt = ''
        if isolcpus:
            kernel_opt = ' isolcpus=' + ','.join(map(str, isolcpus))

        return [
            '-nographic',
            '-s',
            '-machine', 'accel=kvm',
            '-cpu', 'host',
            '-device', 'e1000,netdev=net0',
            '-netdev', 'user,id=net0,hostfwd=tcp::%d-:22' % HOST_PORT,
            '-append',
                'console=ttyS0,115200 root=/dev/sda rw nokaslr' + kernel_opt,
            '-smp', '2',
            '-m', '4G',
            '-drive', 'if=none,id=hd,file=%s,format=raw' % filesystem_img_path,
            '-device', 'virtio-scsi-pci,id=scsi',
            '-device', 'scsi-hd,drive=hd',
            '-device', 'virtio-rng-pci,max-bytes=1024,period=1000',
            '-qmp', 'tcp:localhost:4444,server,nowait',
            '-serial', 'mon:stdio',
            '-kernel', '%s' % kernel_path,
            '-name', 'lsm_perf_vm,debug-threads=on'
        ]

    @staticmethod
    def __qemu_affinity_setup(qemu_pid, cpu_alloc):
        """Run qemu_affinity.py to allocate CPUs based on the CpuAllocation"""
        system_affinities = ('-p %(sys)d -i *:%(sys)d -q %(sys)d -w *:%(sys)d'
                             % {'sys': cpu_alloc.qemu_sys}).split(' ')
        kvm_affinities = ['-k', str(cpu_alloc.host_kvm0),
                                str(cpu_alloc.host_kvm1)]
        args = system_affinities + kvm_affinities + ['--', str(qemu_pid)]
        cmd = plumbum.cmd.sudo['python3'][QEMU_AFFINITY_PATH][args]
        return cmd()


class VMException(Exception):
    """Exceptions specific to the VM class"""
    pass


def print_eta(kernel_name, info=""):
    """Updates the status of the evaluation of a kernel"""
    sys.stdout.write('\r\tEvaluating %s: %s' % (kernel_name, info) + ' ' * 20)
    sys.stdout.flush()


def init_output_file(file):
    """Writes the header in the result file"""
    columns = (['kernel path', 'round'] +
               ['run %d' % i for i in range(REPETITIONS_PER_ROUND)])
    file.write(','.join(columns) + '\n')


def write_results_to_file(file, kernel_path, round, results):
    """Writes the results of the evaluation of a kernel to the file"""
    row = [kernel_path, round] + results
    file.write(','.join(map(str, row)) + '\n')
    file.flush()


def parse_args():
    """Parse arguments with argparse"""
    parser = argparse.ArgumentParser(
        description=('Compares the performances of several kernels'
                     ' on the same workload.'))
    parser.add_argument(
        '-i', '--image', type=argparse.FileType('r'), required=True,
        help='Path of the disk image to boot the kernels from.')
    parser.add_argument(
        '-k', '--kernels', type=argparse.FileType('r'), required=True,
        help='Path of all the kernels to evaluate.', nargs='+')
    parser.add_argument(
        '-w', '--workload', type=argparse.FileType('r'), required=True,
        help=('Path of the workload program to run to evaluate the kernels. '
              'This should take no argument, and simply output an integer '
              'to stdout (the time measurement)'))
    parser.add_argument(
        '-key', type=argparse.FileType('r'),
        default=os.path.expanduser('~/.ssh/id_rsa'),
        help=('Path of the RSA key to connect to the VM. '
              'It must be in the list of authorized keys in the image.'))
    parser.add_argument(
        '-o', '--out', type=argparse.FileType('w'), default='lsm-perf.csv',
        help='Path of the output file.')
    parser.add_argument(
        '-c', '--cpu', type=int, default=[], nargs='*',
        help=('CPUs that should be used to run the VM. '
              'Provide three CPUs [x,y,z], qemu-system will be assigned '
              'to x, the two CPUs of the VM will be assigned to y and z '
              'respectively, and the workload will be run on y. '
              'These CPUs should be isolated '
              '(i.e. start your machine with `isolcpus=x,y,z`). '
              'Keep this list empty to not assign CPUs'))
    args = parser.parse_args()
    if len(args.cpu) not in [0, 3]:
        parser.error(
            'Incorrect number of CPUs provided: expects either 0 or 3')
    return args


if __name__ == "__main__":
    main(parse_args())
