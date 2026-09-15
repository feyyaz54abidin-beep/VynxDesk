#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <string.h>

#include "bsp/board.h"
#include "pico/stdlib.h"
#include "tusb.h"

#include "protocol.h"

#define VYNX_QUEUE_CAPACITY 64u
#define VYNX_WATCHDOG_MS 750u

typedef struct {
    vynx_frame_t frames[VYNX_QUEUE_CAPACITY];
    uint8_t head;
    uint8_t tail;
    uint8_t count;
} vynx_queue_t;

typedef struct {
    uint32_t accepted;
    uint32_t rejected;
    uint32_t watchdog_releases;
    uint16_t last_sequence;
    uint8_t queue_depth;
    uint8_t release_stage;
} vynx_status_t;

static vynx_queue_t command_queue;
static vynx_status_t bridge_status;
static uint64_t last_contact_ms;
static bool watchdog_armed;
static bool usb_mounted;

static uint64_t now_ms(void) {
    return time_us_64() / 1000u;
}

static uint16_t crc16_ccitt(uint8_t const *data, size_t size) {
    uint16_t crc = 0xFFFFu;
    for (size_t i = 0; i < size; ++i) {
        crc ^= (uint16_t)data[i] << 8;
        for (uint8_t bit = 0; bit < 8; ++bit) {
            crc = (crc & 0x8000u) != 0u ? (uint16_t)((crc << 1) ^ 0x1021u)
                                         : (uint16_t)(crc << 1);
        }
    }
    return crc;
}

static bool frame_is_valid(vynx_frame_t const *frame) {
    if (frame->magic[0] != 'V' || frame->magic[1] != 'X' ||
        frame->version != VYNX_PROTOCOL_VERSION ||
        frame->payload_length > VYNX_PAYLOAD_SIZE) {
        return false;
    }
    uint16_t expected = crc16_ccitt((uint8_t const *)frame, 28);
    return expected == frame->crc;
}

static bool command_payload_is_valid(vynx_frame_t const *frame) {
    switch (frame->command) {
        case VYNX_COMMAND_KEYBOARD_STATE:
            return frame->payload_length == sizeof(vynx_keyboard_report_t);
        case VYNX_COMMAND_RELATIVE_MOUSE:
            return frame->payload_length == sizeof(vynx_relative_mouse_report_t);
        case VYNX_COMMAND_ABSOLUTE_MOUSE:
            return frame->payload_length == sizeof(vynx_absolute_mouse_report_t);
        case VYNX_COMMAND_RELEASE_ALL:
        case VYNX_COMMAND_HEARTBEAT:
            return frame->payload_length == 0;
        default:
            return false;
    }
}

static void queue_clear(void) {
    command_queue.head = 0;
    command_queue.tail = 0;
    command_queue.count = 0;
    bridge_status.queue_depth = 0;
}

static bool queue_push(vynx_frame_t const *frame) {
    if (command_queue.count == VYNX_QUEUE_CAPACITY) {
        return false;
    }
    command_queue.frames[command_queue.tail] = *frame;
    command_queue.tail = (uint8_t)((command_queue.tail + 1u) % VYNX_QUEUE_CAPACITY);
    ++command_queue.count;
    bridge_status.queue_depth = command_queue.count;
    return true;
}

static vynx_frame_t const *queue_front(void) {
    return command_queue.count == 0 ? NULL : &command_queue.frames[command_queue.head];
}

static void queue_pop(void) {
    if (command_queue.count == 0) {
        return;
    }
    command_queue.head = (uint8_t)((command_queue.head + 1u) % VYNX_QUEUE_CAPACITY);
    --command_queue.count;
    bridge_status.queue_depth = command_queue.count;
}

static void request_release_all(void) {
    queue_clear();
    bridge_status.release_stage = 1;
    watchdog_armed = false;
}

static void release_task(void) {
    if (bridge_status.release_stage == 0 || !tud_hid_ready()) {
        return;
    }
    if (bridge_status.release_stage == 1) {
        vynx_keyboard_report_t report = {0};
        if (tud_hid_report(VYNX_REPORT_ID_KEYBOARD, &report, sizeof(report))) {
            bridge_status.release_stage = 2;
        }
    } else {
        vynx_relative_mouse_report_t report = {0};
        if (tud_hid_report(VYNX_REPORT_ID_RELATIVE_MOUSE, &report, sizeof(report))) {
            bridge_status.release_stage = 0;
        }
    }
}

static bool send_command(vynx_frame_t const *frame) {
    if (!tud_hid_ready()) {
        return false;
    }
    switch (frame->command) {
        case VYNX_COMMAND_KEYBOARD_STATE: {
            if (frame->payload_length != sizeof(vynx_keyboard_report_t)) {
                return true;
            }
            vynx_keyboard_report_t report;
            memcpy(&report, frame->payload, sizeof(report));
            return tud_hid_report(VYNX_REPORT_ID_KEYBOARD, &report, sizeof(report));
        }
        case VYNX_COMMAND_RELATIVE_MOUSE: {
            if (frame->payload_length != sizeof(vynx_relative_mouse_report_t)) {
                return true;
            }
            vynx_relative_mouse_report_t report;
            memcpy(&report, frame->payload, sizeof(report));
            return tud_hid_report(VYNX_REPORT_ID_RELATIVE_MOUSE, &report, sizeof(report));
        }
        case VYNX_COMMAND_ABSOLUTE_MOUSE: {
            if (frame->payload_length != sizeof(vynx_absolute_mouse_report_t)) {
                return true;
            }
            vynx_absolute_mouse_report_t report;
            memcpy(&report, frame->payload, sizeof(report));
            return tud_hid_report(VYNX_REPORT_ID_ABSOLUTE_MOUSE, &report, sizeof(report));
        }
        case VYNX_COMMAND_RELEASE_ALL:
            request_release_all();
            return true;
        case VYNX_COMMAND_HEARTBEAT:
            return true;
        default:
            return true;
    }
}

static void command_task(void) {
    if (bridge_status.release_stage != 0) {
        release_task();
        return;
    }
    vynx_frame_t const *frame = queue_front();
    if (frame != NULL && send_command(frame)) {
        queue_pop();
    }
}

static void watchdog_task(void) {
    if (watchdog_armed && now_ms() - last_contact_ms > VYNX_WATCHDOG_MS) {
        ++bridge_status.watchdog_releases;
        request_release_all();
    }
}

static void led_task(void) {
    static uint64_t last_update_ms;
    uint64_t now = now_ms();
    if (now - last_update_ms < 50u) {
        return;
    }
    last_update_ms = now;
    bool on;
    if (!usb_mounted) {
        on = (now / 500u) % 2u != 0;
    } else if (bridge_status.release_stage != 0) {
        on = (now / 100u) % 2u != 0;
    } else if (watchdog_armed || now - last_contact_ms < 1000u) {
        on = true;
    } else {
        on = (now / 200u) % 2u != 0;
    }
    board_led_write(on);
}

int main(void) {
    board_init();
    tusb_init();
    while (true) {
        tud_task();
        watchdog_task();
        command_task();
        led_task();
        tight_loop_contents();
    }
}

void tud_mount_cb(void) {
    usb_mounted = true;
    queue_clear();
    bridge_status.release_stage = 1;
    watchdog_armed = false;
}

void tud_umount_cb(void) {
    usb_mounted = false;
    queue_clear();
    watchdog_armed = false;
}

void tud_suspend_cb(bool remote_wakeup_enabled) {
    (void)remote_wakeup_enabled;
    request_release_all();
}

void tud_resume_cb(void) {
    request_release_all();
}

uint16_t tud_hid_get_report_cb(
    uint8_t instance,
    uint8_t report_id,
    hid_report_type_t report_type,
    uint8_t *buffer,
    uint16_t requested_length
) {
    (void)instance;
    if (report_id != VYNX_REPORT_ID_VENDOR ||
        (report_type != HID_REPORT_TYPE_INPUT && report_type != HID_REPORT_TYPE_FEATURE) ||
        requested_length < VYNX_FRAME_SIZE) {
        return 0;
    }
    memset(buffer, 0, VYNX_FRAME_SIZE);
    buffer[0] = 'V';
    buffer[1] = 'X';
    buffer[2] = VYNX_PROTOCOL_VERSION;
    buffer[3] = 0x80;
    memcpy(&buffer[4], &bridge_status, sizeof(bridge_status));
    uint16_t crc = crc16_ccitt(buffer, 28);
    memcpy(&buffer[28], &crc, sizeof(crc));
    return VYNX_FRAME_SIZE;
}

void tud_hid_set_report_cb(
    uint8_t instance,
    uint8_t report_id,
    hid_report_type_t report_type,
    uint8_t const *buffer,
    uint16_t buffer_size
) {
    (void)instance;
    if (report_id == VYNX_REPORT_ID_KEYBOARD && report_type == HID_REPORT_TYPE_OUTPUT) {
        return;
    }
    if (report_id == 0 && buffer_size == VYNX_FRAME_SIZE + 1u &&
        buffer[0] == VYNX_REPORT_ID_VENDOR) {
        report_id = buffer[0];
        ++buffer;
        --buffer_size;
    }
    if (report_id != VYNX_REPORT_ID_VENDOR ||
        (report_type != HID_REPORT_TYPE_OUTPUT && report_type != HID_REPORT_TYPE_FEATURE) ||
        buffer_size != VYNX_FRAME_SIZE) {
        ++bridge_status.rejected;
        return;
    }

    vynx_frame_t frame;
    memcpy(&frame, buffer, sizeof(frame));
    if (!frame_is_valid(&frame) || !command_payload_is_valid(&frame)) {
        ++bridge_status.rejected;
        return;
    }
    last_contact_ms = now_ms();
    watchdog_armed = true;
    bridge_status.last_sequence = frame.sequence;
    if (frame.command == VYNX_COMMAND_HEARTBEAT) {
        ++bridge_status.accepted;
        return;
    }
    if (queue_push(&frame)) {
        ++bridge_status.accepted;
    } else {
        ++bridge_status.rejected;
    }
}
