use crate::client::QualityStatus;
use serde::Serialize;
use std::collections::BTreeMap;

#[derive(Clone, Copy, Debug, Default, PartialEq, Eq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum SessionLifecycle {
    #[default]
    Idle,
    Connecting,
    Connected,
    Disconnected,
}

#[derive(Clone, Debug, Default, PartialEq, Eq, Serialize)]
pub struct ConnectionDiagnosticsSnapshot {
    pub lifecycle: SessionLifecycle,
    pub secure: Option<bool>,
    pub direct: Option<bool>,
    pub transport: String,
    pub speed: Option<String>,
    pub fps: BTreeMap<String, i32>,
    pub delay_ms: Option<i32>,
    pub target_bitrate_kbps: Option<i32>,
    pub codec: Option<String>,
    pub chroma: Option<String>,
}

#[derive(Clone, Debug, Default)]
pub struct SessionDiagnostics {
    snapshot: ConnectionDiagnosticsSnapshot,
}

impl SessionDiagnostics {
    pub fn snapshot(&self) -> ConnectionDiagnosticsSnapshot {
        self.snapshot.clone()
    }

    pub fn start_connecting(&mut self) {
        self.snapshot = ConnectionDiagnosticsSnapshot {
            lifecycle: SessionLifecycle::Connecting,
            ..Default::default()
        };
    }

    pub fn mark_connected(&mut self, secure: bool, direct: bool, transport: &str) {
        self.snapshot.lifecycle = SessionLifecycle::Connected;
        self.snapshot.secure = Some(secure);
        self.snapshot.direct = Some(direct);
        self.snapshot.transport = transport.to_owned();
    }

    pub fn record_quality(&mut self, status: &QualityStatus) {
        if let Some(speed) = status.speed.as_ref() {
            self.snapshot.speed = Some(speed.clone());
        }
        if !status.fps.is_empty() {
            self.snapshot.fps = status
                .fps
                .iter()
                .map(|(display, fps)| (display.to_string(), *fps))
                .collect();
        }
        if let Some(delay) = status.delay {
            self.snapshot.delay_ms = Some(delay);
        }
        if let Some(target_bitrate) = status.target_bitrate {
            self.snapshot.target_bitrate_kbps = Some(target_bitrate);
        }
        if let Some(codec) = status.codec_format.as_ref() {
            self.snapshot.codec = Some(codec.to_string());
        }
        if let Some(chroma) = status.chroma.as_ref() {
            self.snapshot.chroma = Some(chroma.clone());
        }
    }

    pub fn mark_disconnected(&mut self) {
        self.snapshot.lifecycle = SessionLifecycle::Disconnected;
    }
}

#[cfg(test)]
mod tests {
    use super::{SessionDiagnostics, SessionLifecycle};
    use crate::client::QualityStatus;
    use std::collections::HashMap;

    #[test]
    fn snapshot_tracks_a_connection_lifecycle_without_peer_identity() {
        let mut diagnostics = SessionDiagnostics::default();

        diagnostics.start_connecting();
        assert_eq!(
            diagnostics.snapshot().lifecycle,
            SessionLifecycle::Connecting
        );

        diagnostics.mark_connected(true, false, "Relay");
        let connected = diagnostics.snapshot();
        assert_eq!(connected.lifecycle, SessionLifecycle::Connected);
        assert_eq!(connected.secure, Some(true));
        assert_eq!(connected.direct, Some(false));
        assert_eq!(connected.transport, "Relay");
        assert!(!serde_json::to_string(&connected)
            .expect("diagnostics serializes")
            .contains("peer"));

        diagnostics.mark_disconnected();
        assert_eq!(
            diagnostics.snapshot().lifecycle,
            SessionLifecycle::Disconnected
        );
    }

    #[test]
    fn quality_updates_keep_the_last_known_connection_path() {
        let mut diagnostics = SessionDiagnostics::default();
        diagnostics.mark_connected(true, true, "WebRTC");
        diagnostics.record_quality(&QualityStatus {
            speed: Some("128.00kB/s".to_owned()),
            fps: HashMap::from([(0, 60)]),
            chroma: Some("4:2:0".to_owned()),
            ..Default::default()
        });
        diagnostics.record_quality(&QualityStatus {
            delay: Some(42),
            target_bitrate: Some(3200),
            ..Default::default()
        });

        let snapshot = diagnostics.snapshot();
        assert_eq!(snapshot.transport, "WebRTC");
        assert_eq!(snapshot.speed.as_deref(), Some("128.00kB/s"));
        assert_eq!(snapshot.fps.get("0"), Some(&60));
        assert_eq!(snapshot.delay_ms, Some(42));
        assert_eq!(snapshot.target_bitrate_kbps, Some(3200));
        assert_eq!(snapshot.chroma.as_deref(), Some("4:2:0"));
    }
}
