#!/usr/bin/env

import argparse
import time
import plumbum
import sys
import statistics
import os
from plumbum import local, SshMachine  # TODO: requirements


ROUNDS = 3
REPETITIONS_PER_ROUND = 50
WARMUP_RUNS = 5
ON_VM_WORKLOAD_PATH = '~/lsm-perf-workload'
QEMU_EXIT_CMD = b'\x01cq\n'  # -> ctrl+a c q


def main(args):
    try:
        init_output_file(args.out)
        for round in range(ROUNDS):
            print('Starting round %d' % round)
            for kernel in args.kernels:
                results = evaluating_kernel(
                    kernel_path=kernel.name,
                    filesystem_path=args.image.name,
                    workload_path=args.workload.name,
                    keyfile=args.key.name
                )
                write_results_to_file(args.out, kernel.name, round, results)
    except KeyboardInterrupt:
        print('\nExit prematurely')
    finally:
        args.out.close()
    return 0


def evaluate_kernel(kernel_path, filesystem_path, workload_path, keyfile):
    """Starts a VM with the kernel and evaluates its
    performances on the provided workload
    """
    results = []
    name = os.path.basename(kernel_path)
    print_eta(name, info='connecting')

    with VM(kernel_path, filesystem_path, keyfile) as vm:
        vm.scp_to(workload_path, ON_VM_WORKLOAD_PATH)
        work_cmd = vm.ssh[ON_VM_WORKLOAD_PATH]

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
    """Represents a qemu VM with an SSH connection.
    To use with the `with` construct
    """
    def __init__(self, kernel_path, filesystem_path, keyfile):
        """Starts the qemu VM"""
        qemu_args = construct_qemu_args(kernel_path, filesystem_path)
        self.process = local['qemu-system-x86_64'].popen(qemu_args)
        self.ssh = None
        self.key = keyfile

    def __enter__(self):
        """Initialize ssh connection"""
        c = 5
        while self.ssh is None:
            time.sleep(1)
            try:
                self.ssh = SshMachine(
                    '127.0.0.1', user='root', port=5555, keyfile=self.key)
            except (EOFError, plumbum.machines.session.SSHCommsError) as e:
                c -= 1
                if c == 0:
                    raise e
        return self

    def __exit__(self, type, value, traceback):
        """Stops the SSH connection and the VM"""
        if self.ssh is not None:
            self.ssh.close()
            self.ssh = None
        self.process.stdin.write(QEMU_EXIT_CMD)
        self.process.terminate()
        time.sleep(0.5)

    def scp_to(self, src_local, dst_remote):
        """Send a file from the host to the VM"""
        assert self.ssh is not None
        fro = local.path(src_local)
        to = self.ssh.path(dst_remote)
        plumbum.path.utils.copy(fro, to)


def construct_qemu_args(kernel_path, filesystem_path):
    """Qemu arguments similar to what `vm start` produces"""
    return [
        '-nographic',
        '-s',
        '-machine', 'accel=kvm',
        '-cpu', 'host',
        '-device', 'e1000,netdev=net0',
        '-netdev', 'user,id=net0,hostfwd=tcp::5555-:22',
        '-append', 'console=ttyS0,115200 root=/dev/sda rw nokaslr',
        '-smp', '4',
        '-m', '4G',
        '-drive', 'if=none,id=hd,file=%s,format=raw' % filesystem_path,
        '-device', 'virtio-scsi-pci,id=scsi',
        '-device', 'scsi-hd,drive=hd',
        '-device', 'virtio-rng-pci,max-bytes=1024,period=1000',
        '-qmp', 'tcp:localhost:4444,server,nowait',
        '-serial', 'mon:stdio',
        '-kernel', '%s' % kernel_path,
        '-name', 'lsm_perf_vm,debug-threads=on'
    ]


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
    file.write(','.join([str(x) for x in row]) + '\n')
    file.flush()


def parse_args():
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
        '-key', type=argparse.FileType('r'), default='~/.ssh/id_rsa',
        help=('Path of the RSA key to connect to the VM. '
              'It must be in the list of authorized keys in the image.'))
    parser.add_argument(
        '-o', '--out', type=argparse.FileType('w'), default='lsm-perf.csv',
        help='Path of the output file.')

    return parser.parse_args()


if __name__ == "__main__":
    main(parse_args())
