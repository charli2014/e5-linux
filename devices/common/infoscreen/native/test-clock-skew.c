/* LD_PRELOAD shim for test_screen_runtime: a finished deep sleep leaves
 * CLOCK_BOOTTIME ahead of CLOCK_MONOTONIC while nothing else changes. */
#define _GNU_SOURCE
#include <dlfcn.h>
#include <time.h>

int clock_gettime(clockid_t id, struct timespec *ts) {
    static int (*real)(clockid_t, struct timespec *);
    if (!real) real = dlsym(RTLD_NEXT, "clock_gettime");
    int rc = real(id, ts);
    if (!rc && id == CLOCK_BOOTTIME) ts->tv_sec += 1670;
    return rc;
}
