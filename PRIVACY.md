# VynxDesk Client Privacy Notice

This notice describes the VynxDesk client software. A hosted rendezvous, relay,
API, or support service requires its own operator-specific privacy notice.

## Data handled by the client

VynxDesk stores application settings, device identity material, trusted-device
records, address-book data, connection history, and diagnostic logs on the local
device. Remote-control sessions can carry screen, audio, clipboard, input, chat,
terminal, and file-transfer data when the user enables the corresponding feature.

To discover and connect devices, the client sends device and connection metadata
to the configured rendezvous service. Session traffic can pass through the
configured relay when a direct connection is unavailable. The service operator's
retention, access, and hosting practices are outside the client source tree and
must be documented before operating a public service.

## Analytics and advertising

The client build does not enable an analytics or advertising SDK by default.
Production distributors must update this notice before enabling telemetry,
crash-report uploads, advertising, or any additional data collection.

## Diagnostics

On an unexpected native crash, the desktop client can write a local diagnostic
file named `vynxdesk-panic.log` in the operating system temporary directory. It
is not uploaded automatically by this source tree. Diagnostic files can contain
technical paths and failure context and should be shared only when needed for
support.

## User controls

Users can remove local VynxDesk configuration and diagnostic files through the
operating system. Server-side requests concerning hosted-service records must be
directed to the operator named in the commercial service's published privacy
notice.

## Production publication requirement

Before public release, the distributor must add its legal identity, contact
details, service locations, retention periods, subprocessors, and jurisdictional
rights to the hosted-service notice and publish it at the product website.
