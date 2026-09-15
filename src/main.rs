#![cfg_attr(
    all(target_os = "windows", any(not(debug_assertions), feature = "desktop-windowed")),
    windows_subsystem = "windows"
)]

use librustdesk::*;

#[cfg(all(windows, not(feature = "flutter")))]
mod connection_status;

fn install_production_panic_hook() {
    std::panic::set_hook(Box::new(|info| {
        use std::io::Write;
        use std::time::{SystemTime, UNIX_EPOCH};

        let payload = info
            .payload()
            .downcast_ref::<&str>()
            .copied()
            .or_else(|| info.payload().downcast_ref::<String>().map(String::as_str))
            .unwrap_or("panic payload unavailable");
        let location = info
            .location()
            .map(|l| format!("{}:{}:{}", l.file(), l.line(), l.column()))
            .unwrap_or_else(|| "unknown location".to_string());
        let thread = std::thread::current();
        let pid = std::process::id();
        let timestamp = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .map(|d| d.as_millis())
            .unwrap_or(0);
        let backtrace = std::backtrace::Backtrace::capture();
        let msg = format!(
            "[rustdesk] panic pid={pid} ts_ms={timestamp} thread={:?} at={location} payload={payload:?}",
            thread.name()
        );
        eprintln!("{msg}");
        let log_path = std::env::temp_dir().join("vynxdesk-panic.log");
        if let Ok(mut file) = std::fs::OpenOptions::new()
            .create(true)
            .append(true)
            .open(log_path)
        {
            let _ = writeln!(file, "{msg}");
            let _ = writeln!(file, "{backtrace}");
        }
    }));
}

#[cfg(any(target_os = "android", target_os = "ios", feature = "flutter"))]
fn main() {
    install_production_panic_hook();
    if !common::global_init() {
        eprintln!("Global initialization failed.");
        return;
    }
    common::test_rendezvous_server();
    common::test_nat_type();
    common::global_clean();
}

#[cfg(not(any(target_os = "android", target_os = "ios", feature = "flutter")))]
fn main() {
    install_production_panic_hook();
    #[cfg(all(windows, not(feature = "inline")))]
    unsafe {
        winapi::um::shellscalingapi::SetProcessDpiAwareness(2);
    }
    #[cfg(windows)]
    if std::env::args().nth(1).as_deref() == Some("--connection-status-json") {
        if common::global_init() {
            connection_status::run();
            common::global_clean();
        }
        return;
    }
    if let Some(args) = crate::core_main::core_main().as_mut() {
        ui::start(args);
    }
    common::global_clean();
}
