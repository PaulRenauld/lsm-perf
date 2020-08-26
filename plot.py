#!/usr/bin/python
#
# Copyright 2020 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
This file provides a template to draw box graphs for
the output of lsm-perf.py.
It should be adapted and modified for each usecase.

The path of the .csv file produced by lsm-perf.py 
should be given as parameter.
"""

import plotly.express as px
import pandas as pd
import sys
import re

# Modify the title and the axis' titles here
TITLE = "Running time of 1 million `eventfd_write`"
X_AXIS_TITLE = "Activated LSMs"
Y_AXIS_TITLE = u"Running time (\u03BCs)"  # (micro-s)

# Use this to rename raw bzImage paths into nicer names
# Keys are regexes
LSM_NICE_NAME = {
    # '.*bpf_selinux.*': 'BPF + Selinux',
    # '.*selinux.*': 'Selinux Only',
    # '.*bpf.*': 'BBPF Only',
    # '.*nolsm.*': 'No LSM',
}

# Add regexes that match bzImages that should be excluded
EXCLUDE_LSM = [
    # '.*call_cond_bpf_bzImage',
    # '.*call_default_bpf_bzImage'
]


def main(file):
    df = pd.read_csv(file)

    # Convert the table to have one row per measurement
    df["id"] = df.index
    df = pd.wide_to_long(df, 'run ', i='id', j='run')

    df = df.rename(columns={'run ': 'time', 'kernel path': 'kernel'})

    # filter out EXCLUDE_LSM
    if EXCLUDE_LSM:
        regex = '(' + ')|('.join(EXCLUDE_LSM) + ')'
        to_exclude = df['kernel'].str.contains(regex, regex=True)
        df = df.loc[~to_exclude]

    # compute averages for each kernel
    averages = df.groupby('kernel')['time'].mean()
    baseline = averages.min()
    kernels = averages.to_dict()

    # define the new name for each kernel, based on LSM_NICE_NAME
    # and on the difference between its average and the baseline
    replace = {}
    for kernel, avg in kernels.items():
        cost = "+{:.2%}".format(avg / baseline - 1.0)
        name = ([v for k, v in LSM_NICE_NAME.items() if re.match(k, kernel)]
                + [kernel.split('/')[-1]])[0]
        replace[kernel] = '{} ({})'.format(name, cost)
    df = df.replace(replace)

    # Draw the graph
    fig = px.box(df, x="kernel", y="time", points="all")
    fig.update_layout(
        title=TITLE,
        xaxis_title=X_AXIS_TITLE,
        yaxis_title=Y_AXIS_TITLE,
        xaxis_type='category',
        xaxis={'categoryorder':'category ascending'}
    )
    fig.show()


if __name__ == "__main__":
    main(sys.argv[1])
