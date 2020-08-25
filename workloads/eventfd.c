/*
 * Copyright 2020 Google LLC
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *      http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

#include <sys/eventfd.h>
#include <unistd.h>
#include <time.h>
#include <stdio.h>

int main(void) {
        int fd = eventfd(0, 0);
        int c = 1000 * 1000;
        clock_t start, end;

        struct timespec tim;
        tim.tv_sec = 0;
        tim.tv_nsec = 200L * 1000L * 1000L;
        nanosleep(&tim, NULL);

        start = clock();
        while (c--) eventfd_write(fd, 1);
        end = clock();
        printf("%ld\n", end - start);

        nanosleep(&tim, NULL);
        return 0;
}

