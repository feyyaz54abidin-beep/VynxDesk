#include <string.h>

#include "pico/unique_id.h"
#include "tusb.h"

#include "protocol.h"
#include "usb_descriptors.h"

#ifndef VYNX_USB_VID
#error "VYNX_USB_VID is required"
#endif
#ifndef VYNX_USB_PID
#error "VYNX_USB_PID is required"
#endif

tusb_desc_device_t const vynx_device_descriptor = {
    .bLength = sizeof(tusb_desc_device_t),
    .bDescriptorType = TUSB_DESC_DEVICE,
    .bcdUSB = 0x0200,
    .bDeviceClass = 0x00,
    .bDeviceSubClass = 0x00,
    .bDeviceProtocol = 0x00,
    .bMaxPacketSize0 = CFG_TUD_ENDPOINT0_SIZE,
    .idVendor = VYNX_USB_VID,
    .idProduct = VYNX_USB_PID,
    .bcdDevice = 0x0100,
    .iManufacturer = 0x01,
    .iProduct = 0x02,
    .iSerialNumber = 0x03,
    .bNumConfigurations = 0x01,
};

uint8_t const *tud_descriptor_device_cb(void) {
    return (uint8_t const *)&vynx_device_descriptor;
}

uint8_t const vynx_hid_report_descriptor[] = {
    HID_USAGE_PAGE(HID_USAGE_PAGE_DESKTOP),
    HID_USAGE(HID_USAGE_DESKTOP_KEYBOARD),
    HID_COLLECTION(HID_COLLECTION_APPLICATION),
        HID_REPORT_ID(VYNX_REPORT_ID_KEYBOARD)
        HID_USAGE_PAGE(HID_USAGE_PAGE_KEYBOARD),
        HID_USAGE_MIN(0xE0),
        HID_USAGE_MAX(0xE7),
        HID_LOGICAL_MIN(0),
        HID_LOGICAL_MAX(1),
        HID_REPORT_SIZE(1),
        HID_REPORT_COUNT(8),
        HID_INPUT(HID_DATA | HID_VARIABLE | HID_ABSOLUTE),
        HID_USAGE_MIN(0),
        HID_USAGE_MAX(127),
        HID_REPORT_COUNT_N(128, 2),
        HID_REPORT_SIZE(1),
        HID_INPUT(HID_DATA | HID_VARIABLE | HID_ABSOLUTE),
        HID_USAGE_PAGE(HID_USAGE_PAGE_LED),
        HID_USAGE_MIN(1),
        HID_USAGE_MAX(5),
        HID_REPORT_COUNT(5),
        HID_REPORT_SIZE(1),
        HID_OUTPUT(HID_DATA | HID_VARIABLE | HID_ABSOLUTE),
        HID_REPORT_COUNT(1),
        HID_REPORT_SIZE(3),
        HID_OUTPUT(HID_CONSTANT),
    HID_COLLECTION_END,

    HID_USAGE_PAGE(HID_USAGE_PAGE_DESKTOP),
    HID_USAGE(HID_USAGE_DESKTOP_MOUSE),
    HID_COLLECTION(HID_COLLECTION_APPLICATION),
        HID_REPORT_ID(VYNX_REPORT_ID_RELATIVE_MOUSE)
        HID_USAGE(HID_USAGE_DESKTOP_POINTER),
        HID_COLLECTION(HID_COLLECTION_PHYSICAL),
            HID_USAGE_PAGE(HID_USAGE_PAGE_BUTTON),
            HID_USAGE_MIN(1),
            HID_USAGE_MAX(5),
            HID_LOGICAL_MIN(0),
            HID_LOGICAL_MAX(1),
            HID_REPORT_COUNT(5),
            HID_REPORT_SIZE(1),
            HID_INPUT(HID_DATA | HID_VARIABLE | HID_ABSOLUTE),
            HID_REPORT_COUNT(1),
            HID_REPORT_SIZE(3),
            HID_INPUT(HID_CONSTANT),
            HID_USAGE_PAGE(HID_USAGE_PAGE_DESKTOP),
            HID_USAGE(HID_USAGE_DESKTOP_X),
            HID_USAGE(HID_USAGE_DESKTOP_Y),
            HID_LOGICAL_MIN_N(0x8001, 2),
            HID_LOGICAL_MAX_N(0x7FFF, 2),
            HID_REPORT_COUNT(2),
            HID_REPORT_SIZE(16),
            HID_INPUT(HID_DATA | HID_VARIABLE | HID_RELATIVE),
            HID_USAGE(HID_USAGE_DESKTOP_WHEEL),
            HID_LOGICAL_MIN(0x81),
            HID_LOGICAL_MAX(0x7F),
            HID_REPORT_COUNT(1),
            HID_REPORT_SIZE(8),
            HID_INPUT(HID_DATA | HID_VARIABLE | HID_RELATIVE),
            HID_USAGE_PAGE(HID_USAGE_PAGE_CONSUMER),
            HID_USAGE_N(HID_USAGE_CONSUMER_AC_PAN, 2),
            HID_REPORT_COUNT(1),
            HID_REPORT_SIZE(8),
            HID_INPUT(HID_DATA | HID_VARIABLE | HID_RELATIVE),
        HID_COLLECTION_END,
    HID_COLLECTION_END,

    TUD_HID_REPORT_DESC_ABSMOUSE(HID_REPORT_ID(VYNX_REPORT_ID_ABSOLUTE_MOUSE)),
    HID_USAGE_PAGE_N(HID_USAGE_PAGE_VENDOR, 2),
    HID_USAGE(0x01),
    HID_COLLECTION(HID_COLLECTION_APPLICATION),
        HID_REPORT_ID(VYNX_REPORT_ID_VENDOR)
        HID_USAGE(0x02),
        HID_LOGICAL_MIN(0),
        HID_LOGICAL_MAX_N(0xFF, 2),
        HID_REPORT_SIZE(8),
        HID_REPORT_COUNT(VYNX_FRAME_SIZE),
        HID_INPUT(HID_DATA | HID_VARIABLE | HID_ABSOLUTE),
        HID_USAGE(0x03),
        HID_REPORT_COUNT(VYNX_FRAME_SIZE),
        HID_OUTPUT(HID_DATA | HID_VARIABLE | HID_ABSOLUTE),
        HID_USAGE(0x04),
        HID_REPORT_COUNT(VYNX_FRAME_SIZE),
        HID_FEATURE(HID_DATA | HID_VARIABLE | HID_ABSOLUTE),
    HID_COLLECTION_END,
};

uint8_t const *tud_hid_descriptor_report_cb(uint8_t instance) {
    (void)instance;
    return vynx_hid_report_descriptor;
}

enum {
    ITF_NUM_HID,
    ITF_NUM_TOTAL,
};

#define VYNX_CONFIG_TOTAL_LEN (TUD_CONFIG_DESC_LEN + TUD_HID_INOUT_DESC_LEN)
#define VYNX_ENDPOINT_OUT 0x01
#define VYNX_ENDPOINT_IN 0x81

uint8_t const vynx_configuration_descriptor[] = {
    TUD_CONFIG_DESCRIPTOR(
        1,
        ITF_NUM_TOTAL,
        0,
        VYNX_CONFIG_TOTAL_LEN,
        TUSB_DESC_CONFIG_ATT_REMOTE_WAKEUP,
        100
    ),
    TUD_HID_INOUT_DESCRIPTOR(
        ITF_NUM_HID,
        0x04,
        HID_ITF_PROTOCOL_NONE,
        sizeof(vynx_hid_report_descriptor),
        VYNX_ENDPOINT_OUT,
        VYNX_ENDPOINT_IN,
        CFG_TUD_HID_EP_BUFSIZE,
        1
    ),
};

uint8_t const *tud_descriptor_configuration_cb(uint8_t index) {
    (void)index;
    return vynx_configuration_descriptor;
}

uint16_t const *tud_descriptor_string_cb(uint8_t index, uint16_t language_id) {
    (void)language_id;
    static uint16_t descriptor[32];
    char serial[2 * PICO_UNIQUE_BOARD_ID_SIZE_BYTES + 1] = {0};
    char const *value = NULL;
    size_t length = 0;

    if (index == 0) {
        descriptor[1] = 0x0409;
        length = 1;
    } else {
        switch (index) {
            case 1:
                value = "VynxDesk";
                break;
            case 2:
                value = "VynxDesk Play Bridge";
                break;
            case 3:
                pico_get_unique_board_id_string(serial, sizeof(serial));
                value = serial;
                break;
            case 4:
                value = "VynxDesk Input Transport";
                break;
            default:
                return NULL;
        }
        length = strlen(value);
        if (length > 31) {
            length = 31;
        }
        for (size_t i = 0; i < length; ++i) {
            descriptor[i + 1] = (uint8_t)value[i];
        }
    }
    descriptor[0] = (uint16_t)((TUSB_DESC_STRING << 8) | (2 * length + 2));
    return descriptor;
}
