# LSM Perf
This tool is to evaluate and compare the performances of different kernel implementations for syscalls. Specifically, it starts a qemu virtual machine with each kernel, runs a workload that triggers many system calls, and report the results. This is particularly useful to evaluate the cost of a Linux Security Module (LSM).

## Requirements
### Installation
You need the following installed on your system:
- [Python 3](https://www.python.org/downloads/) 
- The [plumbum library](https://pypi.org/project/plumbum/) (`pip install plumbum`)
- [Qemu](https://www.qemu.org/download/) (`apt-get install qemu`)
- [qemu-affinity](https://github.com/zegelin/qemu-affinity) if you want to use the CPU management. This is provided as a git submodule, so clone this repository with `git clone --recursive https://github.com/PaulRenauld/lsm-perf.git`. If you already cloned the repository without the recursive option, just run `git submodule update --init --recursive`

### Files
The `bzImage` of the kernels to be tested are required. You can build them from the [Linux](https://github.com/torvalds/linux) codebase. 

You also need a filesystem image disk (`.img`) into which you can SSH as the root user without needing a password. You might need to create an rsa key and add it in the filesystem image disk as an authorized key. Instructions for this are [here](http://www.linuxproblem.org/art_9.html).

Finally, you need a compiled workload. It should run many times a function with critical performances that you aim to improve, and output the running time in stdout. This should be the only thing printed to stdout. Workload samples are provided in `wokloads/`, you just need to compile them with `make <some workload>`.


## Run


Usage:
``` 
usage: lsm-perf.py [-h] -i IMAGE -k KERNELS [KERNELS ...] -w WORKLOAD
                   [--key KEY] [-o OUT] [-c CPU-QEMU CPU-KVM1 CPU-KVM2]
                   [--runs RUNS] [--rounds ROUNDS] [--warmups WARMUPS]

Compares the performances of several kernels on the same workload.

optional arguments:
  -h, --help            show this help message and exit
  -i IMAGE, --image IMAGE
                        Path of the disk image to boot the kernels from.
  -k KERNELS [KERNELS ...], --kernels KERNELS [KERNELS ...]
                        Path of all the kernels to evaluate.
  -w WORKLOAD, --workload WORKLOAD
                        Path of the workload program to run to evaluate the
                        kernels. This should take no argument, and simply
                        output an integer to stdout (the time measurement)
  --key KEY             Path of the RSA key to connect to the VM. It must be
                        in the list of authorized keys in the image.
  -o OUT, --out OUT     Path of the output file.
  -c CPU-QEMU CPU-KVM1 CPU-KVM2, --cpu CPU-QEMU CPU-KVM1 CPU-KVM2
                        CPUs that should be used to run the VM. Qemu-system
                        will be assigned to `CPU-QEMU`, the two CPUs of the VM
                        will be assigned to `CPU-KVM1` and `CPU-KVM2`
                        respectively, and the workload will be run on `CPU-
                        KVM1`. These CPUs should be isolated (i.e. start your
                        machine with `isolcpus=CPU-QEMU,CPU-KVM1,CPU-KVM2`.
                        Omit this parameter to not assign CPUs
  --runs RUNS           Number of times the workload should be evaluated for
                        each kernel in each round.
  --rounds ROUNDS       Number of times the tested are repeated and the VMs
                        restarted.
  --warmups WARMUPS     Number of times the workload will be run but not
                        measured after starting the VM.

```

You can give as many kernels as you want (`-k`). They will all be evaluated several times and the results will be written in the output file (`-o`). You also need to provide the image (`-i`) with the authorized ssh key (`--key`). The progress will be displayed in stdout.

You can use the CPU management with `-c`. This will assign the virtual machine's CPUs to the physical host's CPUs. You should also start the host with the kernel parameter `isolcpus=...`, so that the virtual machine will have dedicated CPUs. This ensures the most reliable benchmark measurements. It is also recommended to start your machine in non-graphical mode.

## Example 

Run (in progress) example:

```
$ python3 lsm-perf.py -i ../../images/debian.img -k ../../images/alllsm ../../images/bpflsm ../../images/paulsm ../../images/nolsm -w workloads/eventfd -key ****
No dedicated CPUs provided.
Starting round 0
        Evaluating alllsm: 100% average=634125, stdev=6516                    
        Evaluating bpflsm: 100% average=591334, stdev=5978                    
        Evaluating paulsm: 100% average=592567, stdev=7477                    
        Evaluating nolsm: 100%  average=565212, stdev=10426                    
Starting round 1
        Evaluating alllsm: 100% average=641875, stdev=3505                    
        Evaluating bpflsm: 100% average=594381, stdev=8446                    
        Evaluating paulsm: 80%                              
```

Output file content example:

```
kernel path,round,run 0,run 1,run 2,run 3,run 4,run 5,run 6,run 7,run 8,run 9
../../images/alllsm,0,632534,637162,633624,639046,640437,632283,638391,621850,624864,641063
../../images/bpflsm,0,588247,589773,592864,586622,592978,601313,590462,579478,594899,596710
../../images/paulsm,0,585694,600144,584909,585880,598131,597167,605159,583542,591269,593776
../../images/nolsm,0,572458,558261,553266,574269,572572,569700,568683,549366,579234,554316
../../images/alllsm,1,644304,639634,637911,643676,647124,635481,641246,642767,645180,641430
../../images/bpflsm,1,585039,584189,591454,598259,599099,613591,593824,595055,588458,594850
../../images/paulsm,1,585049,582425,602832,588233,584257,597798,600553,592897,599376,596029
../../images/nolsm,1,559117,571304,560387,574854,580482,570355,561769,565104,575381,567941
../../images/alllsm,2,623583,630186,621311,642966,621754,628041,628981,639126,638830,642383
../../images/bpflsm,2,586485,600646,587043,590295,601922,587821,584644,592760,590667,581323
../../images/paulsm,2,583044,577246,580257,586506,593093,591338,596610,579747,588739,584627
../../images/nolsm,2,562076,564104,570189,570115,557956,564576,574262,558895,574167,569505
```
