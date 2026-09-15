cmake_minimum_required(VERSION 3.13)

if(NOT DEFINED ENV{PICO_SDK_PATH})
    message(FATAL_ERROR "PICO_SDK_PATH must point to the Raspberry Pi Pico SDK")
endif()
if(NOT DEFINED VYNX_USB_VID OR NOT DEFINED VYNX_USB_PID)
    message(FATAL_ERROR "Set assigned VYNX_USB_VID and VYNX_USB_PID values")
endif()

include($ENV{PICO_SDK_PATH}/external/pico_sdk_import.cmake)

project(vynx_input_bridge C CXX ASM)
set(CMAKE_C_STANDARD 11)
set(CMAKE_CXX_STANDARD 17)

pico_sdk_init()

add_executable(vynx_input_bridge
    src/main.c
    src/usb_descriptors.c
)

target_include_directories(vynx_input_bridge PRIVATE src)
target_compile_definitions(vynx_input_bridge PRIVATE
    VYNX_USB_VID=${VYNX_USB_VID}
    VYNX_USB_PID=${VYNX_USB_PID}
)
target_compile_options(vynx_input_bridge PRIVATE -Wall -Wextra -Werror)
target_link_libraries(vynx_input_bridge PRIVATE pico_stdlib pico_unique_id tinyusb_device tinyusb_board)

pico_enable_stdio_uart(vynx_input_bridge 0)
pico_enable_stdio_usb(vynx_input_bridge 0)
pico_add_extra_outputs(vynx_input_bridge)
