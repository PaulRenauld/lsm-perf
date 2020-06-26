#!/usr/bin/env

import argparse
import time
import plumbum
import sys
import statistics
from plumbum import local, SshMachine # TODO: requirements


NUMBER_OF_ROUNDS = 3
NUMBER_OF_REPETITIONS = 50
WARMUP_RUNS = 5
ON_VM_WORKLOAD_PATH = '~/lsm-perf-workload'
QEMU_EXIT_CMD=b'\x01cq\n' # -> ctrl+a c q


def main(args):
    for round in range(NUMBER_OF_ROUNDS):
        print('Starting round %d' % round)
        for kernel in args.kernels:
            evaluating_kernel(kernel.name, args.image.name, args.workload.name, args.key.name)
    return 0


def print_eta(kernel_name, info=""):
    sys.stdout.write('\r\tEvaluating %s: %s            ' % (kernel_name, info))
    sys.stdout.flush()


def evaluating_kernel(kernel_path, img_path, workload_path, keyfile):
    results = []
    name = kernel_path[kernel_path.rfind('/') + 1:]
    print_eta(name, info='connecting')

    with VM(kernel_path, img_path, keyfile) as vm:
        vm.scp_to(workload_path, ON_VM_WORKLOAD_PATH)
        work_cmd = vm.ssh[ON_VM_WORKLOAD_PATH]

        print_eta(name, info='Running warm up')
        for _ in range(WARMUP_RUNS):
            work_cmd()

        for i in range(NUMBER_OF_REPETITIONS):
            results.append(int(work_cmd().strip()))
            percentage = (i + 1) * 100 / NUMBER_OF_REPETITIONS
            print_eta(name, info='%d%%' % percentage)

        vm.ssh.path(ON_VM_WORKLOAD_PATH).delete()

    stats = '\taverage=%d, stdev=%d' % (statistics.mean(results), statistics.stdev(results))
    print_eta(name, info=stats)
    print()
    return results


class VM:
    def __init__(self, kernel_path, img_path, keyfile):
        self.process = local['vm'].popen(['start', '-k', kernel_path, '-i', img_path])
        self.ssh = None
        self.key = keyfile

    def __enter__(self):
        # Initialize ssh connection
        c = 5
        while self.ssh is None:
            time.sleep(1)
            try: 
                self.ssh = SshMachine('127.0.0.1', user='root', port=5555, keyfile=self.key)
            except (EOFError, plumbum.machines.session.SSHCommsError) as e:
                c -= 1
                if c == 0:
                    raise e
        return self

    def __exit__(self, type, value, traceback):
        if self.ssh is not None:
            self.ssh.close()
            self.ssh = None
        self.process.stdin.write(QEMU_EXIT_CMD)
        self.process.terminate()
        time.sleep(0.5)

    def scp_to(self, src_local, dst_remote):
        assert self.ssh is not None
        fro = local.path(src_local)
        to = self.ssh.path(dst_remote)
        plumbum.path.utils.copy(fro, to)


def parse_args():
    parser = argparse.ArgumentParser(description=
                        'Compares the performances of several kernels on the same workload.')
    parser.add_argument('-i', '--image', type=argparse.FileType('r'), required=True, 
                        help='Path of the disk image to boot the kernels from.')
    parser.add_argument('-k', '--kernels', type=argparse.FileType('r'), nargs='+', required=True, 
                        help='Path of all the kernels to evaluate.')
    parser.add_argument('-w', '--workload', type=argparse.FileType('r'), required=True, 
                        help='Path of the workload program to run to evaluate the kernels. ' +
                        'This should take no argument, and simply output an integer to stdout ' +
                        '(the time measurement)')
    parser.add_argument('-key', type=argparse.FileType('r'), default='~/.ssh/id_rsa', 
                        help='Path of the RSA key to connect to the VM. ' + 
                        'It must be in the list of authorized keys in the image.')
    
    return parser.parse_args()


if __name__ == "__main__":
    main(parse_args())
