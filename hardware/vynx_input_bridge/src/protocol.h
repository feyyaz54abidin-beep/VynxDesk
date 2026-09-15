#ifndef VYNX_INPUT_BRIDGE_PROTOCOL_H
#define VYNX_INPUT_BRIDGE_PROTOCOL_H

#include <stdint.h>

#define VYNX_PROTOCOL_VERSION 1u
#define VYNX_FRAME_SIZE 32u
#define VYNX_PAYLOAD_SIZE 20u
#define VYNX_REPORT_ID_KEYBOARD 1u
#define VYNX_REPORT_ID_RELATIVE_MOUSE 2u
#define VYNX_REPORT_ID_ABSOLUTE_MOUSE 3u
#define VYNX_REPORT_ID_VENDOR 4u

typedef enum {
    VYNX_COMMAND_KEYBOARD_STATE = 1,
    VYNX_COMMAND_RELATIVE_MOUSE = 2,
    VYNX_COMMAND_ABSOLUTE_MOUSE = 3,
    VYNX_COMMAND_RELEASE_ALL = 4,
    VYNX_COMMAND_HEARTBEAT = 5,
} vynx_command_t;

typedef struct __attribute__((packed)) {
    uint8_t magic[2];
    uint8_t version;
    uint8_t command;
    uint16_t sequence;
    uint8_t payload_length;
    uint8_t flags;
    uint8_t payload[VYNX_PAYLOAD_SIZE];
    uint16_t crc;
    uint8_t reserved[2];
} vynx_frame_t;

typedef struct __attribute__((packed)) {
    uint8_t modifiers;
    uint8_t usages[16];
} vynx_keyboard_report_t;

typedef struct __attribute__((packed)) {
    uint8_t buttons;
    int16_t x;
    int16_t y;
    int8_t wheel;
    int8_t pan;
} vynx_relative_mouse_report_t;

typedef struct __attribute__((packed)) {
    uint8_t buttons;
    uint16_t x;
    uint16_t y;
    int8_t wheel;
    int8_t pan;
} vynx_absolute_mouse_report_t;

_Static_assert(sizeof(vynx_frame_t) == VYNX_FRAME_SIZE, "Protocol frame size mismatch");
_Static_assert(sizeof(vynx_keyboard_report_t) == 17u, "Keyboard report size mismatch");
_Static_assert(sizeof(vynx_relative_mouse_report_t) == 7u, "Relative mouse report size mismatch");
_Static_assert(sizeof(vynx_absolute_mouse_report_t) == 7u, "Absolute mouse report size mismatch");

#endif
