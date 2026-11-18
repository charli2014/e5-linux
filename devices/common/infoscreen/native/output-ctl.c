#define _GNU_SOURCE
/* zwlr-output-management-unstable-v1 client on the raw Wayland wire protocol.
 * Static and dependency-free like t551m-screen-power: cage 0.2.0 already
 * implements the protocol (output.c handle_output_manager_apply), so the
 * display pipeline can be disabled/enabled without patching the compositor.
 * Exit codes: 0 success, 1 protocol/apply failure, 2 connect/timeout. */
#include <errno.h>
#include <poll.h>
#include <stdarg.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>
#include <sys/uio.h>
#include <sys/un.h>
#include <time.h>
#include <unistd.h>

#define MAXOBJ 64
#define RBUF (64 * 1024)
#define DEADLINE_MS 3000
#define MANAGER "zwlr_output_manager_v1"

enum kind { K_NONE, K_REGISTRY, K_MANAGER, K_HEAD, K_MODE, K_CONFIG, K_CFGHEAD };

struct obj {
    uint32_t id;
    enum kind kind;
    bool dead;
    char name[64];
    int enabled;
    uint32_t mode, preferred, first, head_id;
    int32_t x, y, scale;
};

static int fd = -1;
static unsigned char rbuf[RBUF];
static size_t rlen;
static uint32_t next_id = 2; /* wl_display is always 1 */
static struct obj objs[MAXOBJ];
static uint32_t manager_id, serial;
static bool bound, got_done;
static int apply_result = -1;

static void die(int code, const char *fmt, ...) __attribute__((format(printf, 2, 3)));
static void die(int code, const char *fmt, ...) {
    va_list ap;
    va_start(ap, fmt);
    fputs("e5-output-ctl: ", stderr);
    vfprintf(stderr, fmt, ap);
    fputc('\n', stderr);
    va_end(ap);
    exit(code);
}

static struct obj *find(uint32_t id) {
    for (unsigned i = 0; i < MAXOBJ; i++)
        if (objs[i].kind != K_NONE && objs[i].id == id)
            return &objs[i];
    return NULL;
}

static struct obj *alloc(enum kind kind) {
    for (unsigned i = 0; i < MAXOBJ; i++)
        if (objs[i].kind == K_NONE) {
            struct obj *o = &objs[i];
            memset(o, 0, sizeof(*o));
            o->id = next_id++;
            o->kind = kind;
            o->enabled = -1;
            o->scale = 256; /* wl_fixed 1.0 */
            return o;
        }
    die(1, "object table full");
    return NULL;
}

static struct obj *server_obj(uint32_t id, enum kind kind) {
    struct obj *o = find(id);
    if (o)
        return o;
    for (unsigned i = 0; i < MAXOBJ; i++)
        if (objs[i].kind == K_NONE) {
            o = &objs[i];
            memset(o, 0, sizeof(*o));
            o->id = id;
            o->kind = kind;
            o->enabled = -1;
            o->scale = 256;
            return o;
        }
    die(1, "object table full");
    return NULL;
}

struct wb {
    unsigned char b[1024];
    size_t n;
};

static void w32(struct wb *w, uint32_t v) {
    if (w->n + 4 > sizeof(w->b))
        die(1, "request too large");
    memcpy(w->b + w->n, &v, 4);
    w->n += 4;
}

static void wstr(struct wb *w, const char *s) {
    uint32_t l = (uint32_t)strlen(s) + 1;
    if (w->n + 4 + l + 3 > sizeof(w->b))
        die(1, "request too large");
    w32(w, l);
    memcpy(w->b + w->n, s, l);
    w->n += l;
    while (w->n & 3)
        w->b[w->n++] = 0;
}

static void send_msg(uint32_t sender, uint16_t opcode, struct wb *w) {
    uint32_t hdr[2] = {sender, ((uint32_t)(8 + w->n) << 16) | opcode};
    struct iovec iov[2] = {{hdr, sizeof(hdr)}, {w->b, w->n}};
    ssize_t n = writev(fd, iov, w->n ? 2 : 1);
    if (n != (ssize_t)(8 + w->n))
        die(2, "write: %s", strerror(errno));
}

struct rb {
    const unsigned char *p;
    size_t left;
};

static uint32_t r32(struct rb *r) {
    if (r->left < 4)
        die(1, "truncated message");
    uint32_t v;
    memcpy(&v, r->p, 4);
    r->p += 4;
    r->left -= 4;
    return v;
}

static const char *rstr(struct rb *r) {
    uint32_t l = r32(r);
    uint32_t pad = (l + 3) & ~3u;
    if (!l || l > pad || r->left < pad)
        die(1, "bad string argument");
    const char *s = (const char *)r->p;
    if (s[l - 1])
        die(1, "unterminated string");
    r->p += pad;
    r->left -= pad;
    return s;
}

static void dispatch(uint32_t sender, uint16_t opcode, struct rb *r) {
    if (sender == 1) { /* wl_display */
        if (opcode == 0) {
            uint32_t oid = r32(r), code = r32(r);
            die(1, "compositor error on object %u: %u %s", oid, code, rstr(r));
        } else if (opcode == 1) {
            struct obj *o = find(r32(r));
            if (o)
                o->dead = true;
        }
        return;
    }
    struct obj *o = find(sender);
    if (!o || o->dead)
        return;
    switch (o->kind) {
    case K_REGISTRY:
        if (opcode == 0) { /* global */
            uint32_t name = r32(r);
            const char *iface = rstr(r);
            uint32_t ver = r32(r);
            if (!bound && !strcmp(iface, MANAGER)) {
                struct obj *m = alloc(K_MANAGER);
                manager_id = m->id;
                struct wb w = {0};
                w32(&w, name);
                wstr(&w, MANAGER);
                w32(&w, ver < 2 ? ver : 2);
                w32(&w, manager_id);
                send_msg(sender, 0, &w); /* bind */
                bound = true;
            }
        }
        break;
    case K_MANAGER:
        if (opcode == 0) { /* head */
            server_obj(r32(r), K_HEAD);
        } else if (opcode == 1) { /* done */
            serial = r32(r);
            got_done = true;
        } else if (opcode == 2) { /* finished */
            o->dead = true;
        }
        break;
    case K_HEAD:
        switch (opcode) {
        case 0: /* name */
            snprintf(o->name, sizeof(o->name), "%s", rstr(r));
            break;
        case 3: { /* mode */
            struct obj *m = server_obj(r32(r), K_MODE);
            m->head_id = sender;
            if (!o->first)
                o->first = m->id;
            break;
        }
        case 4: /* enabled */
            o->enabled = r32(r) != 0;
            break;
        case 5: /* current_mode */
            o->mode = r32(r);
            break;
        case 6: /* position */
            o->x = (int32_t)r32(r);
            o->y = (int32_t)r32(r);
            break;
        case 8: /* scale (fixed) */
            o->scale = (int32_t)r32(r);
            break;
        case 9: /* finished */
            o->dead = true;
            break;
        case 1: /* description */
        case 10: /* make */
        case 11: /* model */
        case 12: /* serial_number */
            rstr(r);
            break;
        case 2: /* physical_size */
            r32(r);
            r32(r);
            break;
        case 7: /* transform */
            r32(r);
            break;
        }
        break;
    case K_MODE:
        switch (opcode) {
        case 2: { /* preferred */
            struct obj *h = find(o->head_id);
            if (h)
                h->preferred = sender;
            break;
        }
        case 3: /* finished */
            o->dead = true;
            break;
        case 0: /* size */
            r32(r);
            r32(r);
            break;
        case 1: /* refresh */
            r32(r);
            break;
        }
        break;
    case K_CONFIG:
        if (opcode <= 2) /* succeeded / failed / cancelled */
            apply_result = opcode;
        break;
    default:
        break;
    }
}

static long long now_ms(void) {
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return (long long)ts.tv_sec * 1000 + ts.tv_nsec / 1000000;
}

static void loop_until(bool (*pred)(void)) {
    long long deadline = now_ms() + DEADLINE_MS;
    while (!pred()) {
        long long rem = deadline - now_ms();
        if (rem <= 0)
            die(2, "timeout waiting for compositor");
        struct pollfd p = {fd, POLLIN, 0};
        int rc = poll(&p, 1, (int)rem);
        if (rc < 0) {
            if (errno == EINTR)
                continue;
            die(2, "poll: %s", strerror(errno));
        }
        if (!rc)
            continue;
        ssize_t n = read(fd, rbuf + rlen, RBUF - rlen);
        if (n <= 0)
            die(2, "compositor connection closed");
        rlen += (size_t)n;
        while (rlen >= 8) {
            uint32_t hdr[2];
            memcpy(hdr, rbuf, 8);
            uint32_t size = hdr[1] >> 16;
            if (size < 8 || size > RBUF)
                die(1, "bad message size %u", size);
            if (rlen < size)
                break;
            struct rb r = {rbuf + 8, size - 8};
            dispatch(hdr[0], (uint16_t)(hdr[1] & 0xffff), &r);
            memmove(rbuf, rbuf + size, rlen - size);
            rlen -= size;
        }
    }
}

static bool initial(void) {
    return bound && got_done;
}

static bool applied(void) {
    return apply_result >= 0;
}

static void connect_socket(void) {
    char buf[256];
    const char *path = getenv("E5_WAYLAND_SOCKET");
    if (!path) {
        const char *xdg = getenv("XDG_RUNTIME_DIR"), *wl = getenv("WAYLAND_DISPLAY");
        if (xdg && wl) {
            snprintf(buf, sizeof(buf), "%s/%s", xdg, wl);
            path = buf;
        } else {
            path = "/tmp/run/e5-infoscreen/wayland-0";
        }
    }
    fd = socket(AF_UNIX, SOCK_STREAM | SOCK_CLOEXEC, 0);
    if (fd < 0)
        die(2, "socket: %s", strerror(errno));
    struct sockaddr_un addr = {.sun_family = AF_UNIX};
    snprintf(addr.sun_path, sizeof(addr.sun_path), "%s", path);
    if (connect(fd, (struct sockaddr *)&addr, sizeof(addr)) < 0)
        die(2, "connect %s: %s", path, strerror(errno));
}

int main(int argc, char **argv) {
    if (argc != 2 || (strcmp(argv[1], "on") && strcmp(argv[1], "off") && strcmp(argv[1], "status"))) {
        fprintf(stderr, "usage: e5-output-ctl on|off|status\n");
        return 2;
    }
    const char *cmd = argv[1];
    connect_socket();
    struct obj *reg = alloc(K_REGISTRY);
    struct wb w = {0};
    w32(&w, reg->id);
    send_msg(1, 1, &w); /* wl_display.get_registry */
    loop_until(initial);

    unsigned heads = 0;
    bool all_on = true;
    for (unsigned i = 0; i < MAXOBJ; i++)
        if (objs[i].kind == K_HEAD && !objs[i].dead) {
            heads++;
            if (objs[i].enabled != 1)
                all_on = false;
        }
    if (!heads)
        die(1, "compositor advertises no heads");
    if (!strcmp(cmd, "status")) {
        puts(all_on ? "on" : "off");
        return 0;
    }

    bool enable = !strcmp(cmd, "on");
    struct obj *cfg = alloc(K_CONFIG);
    w = (struct wb){0};
    w32(&w, cfg->id);
    w32(&w, serial);
    send_msg(manager_id, 0, &w); /* create_configuration */
    for (unsigned i = 0; i < MAXOBJ; i++) {
        struct obj *h = &objs[i];
        if (h->kind != K_HEAD || h->dead)
            continue;
        if (!enable) {
            w = (struct wb){0};
            w32(&w, h->id);
            send_msg(cfg->id, 1, &w); /* disable_head */
            continue;
        }
        uint32_t mode = h->mode ? h->mode : (h->preferred ? h->preferred : h->first);
        if (!mode)
            die(1, "head %s has no mode to enable", h->name);
        struct obj *ch = alloc(K_CFGHEAD);
        w = (struct wb){0};
        w32(&w, ch->id);
        w32(&w, h->id);
        send_msg(cfg->id, 0, &w); /* enable_head */
        w = (struct wb){0};
        w32(&w, mode);
        send_msg(ch->id, 0, &w); /* set_mode */
        w = (struct wb){0};
        w32(&w, (uint32_t)h->x);
        w32(&w, (uint32_t)h->y);
        send_msg(ch->id, 2, &w); /* set_position */
        w = (struct wb){0};
        w32(&w, (uint32_t)h->scale);
        send_msg(ch->id, 4, &w); /* set_scale */
    }
    w = (struct wb){0};
    send_msg(cfg->id, 2, &w); /* apply */
    loop_until(applied);
    w = (struct wb){0};
    send_msg(cfg->id, 4, &w); /* destroy */
    if (apply_result != 0)
        die(1, "configuration %s", apply_result == 1 ? "failed" : "cancelled (stale serial)");
    return 0;
}