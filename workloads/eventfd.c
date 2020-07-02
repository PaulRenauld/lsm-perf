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

