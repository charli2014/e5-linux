#define E5_SIM_TEST
#include "sim-status.c"
#include <stdio.h>

int main(void) {
    (void)collect;
    (void)stop;
    GError *error = NULL;
    char *reply = query(0, "+COPS?", &error);
    if (reply) {
        printf("reply=%s", reply);
        g_free(reply);
        return 0;
    }
    printf("error=%s", error ? error->message : "none");
    g_clear_error(&error);
    return 1;
}
