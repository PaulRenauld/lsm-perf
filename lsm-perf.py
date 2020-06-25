#!/usr/bin/env

import argparse
import time
import plumbum
from plumbum import local, SshMachine # TODO: requirements


NUMBER_OF_ROUNDS = 1
QEMU_EXIT_CMD=b'\x01cq\n' # -> ctrl+a c q


def evaluating_kernel(kernel_path, img_path, workload_path):
    with VM(kernel_path, img_path) as vm:
        print('\tEvaluating %s' % vm.name)
        conn = vm.ssh()
        print(conn['ls']())
        vm.scp_to(workload_path, "~/lsm-perf-workload")
        print(conn['ls']())
        work_cmd = conn['~/lsm-perf-workload']
        results = [work_cmd() for _ in range(10)]
        print(results)


class VM:
    def __init__(self, kernel_path, img_path):
        self.process = local['vm'].popen(['start', '-k', kernel_path, '-i', img_path])
        self.name = kernel_path[kernel_path.rfind('/') + 1:]
        self.ssh_con = None

    def ssh(self, keyfile='~/.ssh/id_rsa_nopassw'):
        c = 5
        while self.ssh_con is None:
            time.sleep(1)
            try: 
                self.ssh_con = SshMachine('127.0.0.1', user='root', port=5555, keyfile=keyfile)
            except (EOFError, plumbum.machines.session.SSHCommsError) as e:
                c -= 1
                if c == 0:
                    raise e
                else:
                    print('Failed to ssh, retrying...')
        return self.ssh_con

    def __enter__(self):
        return self

    def __exit__(self, type, value, traceback):
        if self.ssh_con is not None:
            self.ssh_con.close()
            self.ssh_con = None
        self.process.stdin.write(QEMU_EXIT_CMD)

    def scp_to(self, src_local, dst_remote):
        assert self.ssh_con is not None
        fro = local.path(src_local)
        to = self.ssh_con.path(dst_remote)
        plumbum.path.utils.copy(fro, to)


def main(args):
    for round in range(NUMBER_OF_ROUNDS):
        print('Starting round %d' % round)
        for kernel in args.kernels:
            evaluating_kernel(kernel.name, args.image.name, args.workload.name)
    return 0


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
    return parser.parse_args()


if __name__ == "__main__":
    main(parse_args())
