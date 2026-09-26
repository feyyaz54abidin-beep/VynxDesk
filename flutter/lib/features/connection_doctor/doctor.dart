/// Local, bounded observations; never an authorization or input-acceptance check.
class DoctorFinding {
  final String code, severity, title, detail;
  const DoctorFinding(this.code, this.severity, this.title, this.detail);
}

class DoctorReport {
  final String summary, freshness;
  final Map<String, Object?> metrics;
  final List<DoctorFinding> findings;

  DoctorReport(this.summary, this.freshness, Map<String, Object?> metrics,
      List<DoctorFinding> findings)
      : metrics = Map.unmodifiable(metrics),
        findings = List.unmodifiable(findings);

  Map<String, Object?> toJson() => {
        'schema': 1,
        'product': 'VynxDesk',
        'source': 'local_connection_observer',
        'summary': summary,
        'freshness': freshness,
        'metrics': metrics,
        'findings': [
          for (final finding in findings)
            {'code': finding.code, 'severity': finding.severity}
        ],
      };
}

class ConnectionDoctor {
  static const freshnessLimit = Duration(seconds: 15);
  static const latencyAdvisoryMs = 200;
  static const lowFrameAdvisory = 15;
  final Duration Function() _elapsed;
  Duration? _received;
  Map<String, Object?> _sample = const {};

  ConnectionDoctor({Duration Function()? elapsed})
      : _elapsed = elapsed ?? _monotonicClock();

  static Duration Function() _monotonicClock() {
    final clock = Stopwatch()..start();
    return () => clock.elapsed;
  }

  void reset() {
    _received = null;
    _sample = const {};
  }

  static bool? _boolean(Object? value) {
    if (value == true || value == 'true') return true;
    if (value == false || value == 'false') return false;
    return null;
  }

  static int? _integer(Object? value, int maximum) {
    if (value is String) {
      // Full-match semantics: a trailing newline must not pass `$` anchoring.
      if (value.isEmpty ||
          value.length > 8 ||
          value.codeUnits.any((c) => c < 48 || c > 57)) return null;
      value = int.tryParse(value);
    }
    return value is int && value >= 0 && value <= maximum ? value : null;
  }

  static String? _known(Object? value, Set<String> values) =>
      value is String && value.length <= 32 && values.contains(value)
          ? value
          : null;

  void ingest(Map<String, dynamic> snapshot) {
    final lifecycle = _known(snapshot['lifecycle'],
        const {'idle', 'connecting', 'connected', 'disconnected'});
    if (lifecycle == null) {
      reset();
      return;
    }
    int? minimumFps;
    final frames = snapshot['fps'];
    if (frames is Map && frames.length <= 64) {
      for (final entry in frames.entries) {
        if (_integer(entry.key, 63) == null) continue;
        final fps = _integer(entry.value, 1000);
        if (fps != null && (minimumFps == null || fps < minimumFps)) {
          minimumFps = fps;
        }
      }
    }
    _sample = {
      'lifecycle': lifecycle,
      if (lifecycle == 'connected') ...{
        'secure': _boolean(snapshot['secure']),
        'direct': _boolean(snapshot['direct']),
        'transport': _known(snapshot['transport'], const {
          'TCP',
          'UDP',
          'Relay',
          'WebRTC',
          'WebRTC/IPv6',
          'WebSocket',
          'IPv6',
        }),
        'latency_ms': _integer(snapshot['delay_ms'], 60000),
        'target_bitrate_kbps':
            _integer(snapshot['target_bitrate_kbps'], 1000000),
        'minimum_fps': minimumFps,
        'codec': _known(snapshot['codec'], const {
          'H264',
          'H265',
          'VP8',
          'VP9',
          'AV1',
          'H.264',
          'H.265',
        }),
        'chroma': _known(snapshot['chroma'], const {'4:2:0', '4:4:4'}),
      },
    };
    _received = _elapsed();
  }

  DoctorReport evaluate({bool? keyboardAllowed, bool? viewOnly}) {
    final received = _received;
    final lifecycle = _sample['lifecycle'];
    if (received == null || lifecycle == 'idle') {
      return DoctorReport('waiting', 'unavailable', {}, const [
        DoctorFinding('no_observation', 'info', 'Waiting for observations',
            'No current diagnostic data is available. This is not a successful connection test.'),
      ]);
    }
    if (lifecycle == 'disconnected') {
      return DoctorReport('disconnected', 'ended', {
        'lifecycle': lifecycle
      }, const [
        DoctorFinding('disconnected', 'warning', 'Session disconnected',
            'The observer reports a disconnection. The cause is not known from this report.'),
      ]);
    }
    final age = _elapsed() - received;
    if (age.isNegative || age > freshnessLimit) {
      return DoctorReport('waiting', 'stale', {
        'lifecycle': lifecycle
      }, const [
        DoctorFinding('stale_observation', 'warning', 'Observations are stale',
            'No recent diagnostic event was received. Cached measurements are hidden; this does not prove a disconnection.'),
      ]);
    }
    if (lifecycle == 'connecting') {
      return DoctorReport('connecting', 'recent', {
        'lifecycle': lifecycle
      }, const [
        DoctorFinding('connecting', 'info', 'Connection in progress',
            'Wait for the session to connect. No failure cause has been established.'),
      ]);
    }
    final findings = <DoctorFinding>[];
    if (_sample['secure'] == false) {
      findings.add(const DoctorFinding(
          'security_unverified',
          'warning',
          'Connection security is unverified',
          'Verify the intended peer and server identity before sharing sensitive data. This status alone does not establish whether traffic is encrypted.'));
    } else if (_sample['secure'] == null) {
      findings.add(const DoctorFinding(
          'security_unknown',
          'info',
          'Security status is unknown',
          'The observer did not provide a recognized security state. Do not treat an unknown value as verified.'));
    }
    if (viewOnly == true) {
      findings.add(const DoctorFinding(
          'view_only',
          'warning',
          'View-only mode is enabled',
          'This session is configured for viewing. Change control permissions only with the remote user or administrator.'));
    }
    if (keyboardAllowed == false) {
      findings.add(const DoctorFinding(
          'keyboard_denied',
          'warning',
          'Keyboard permission is disabled',
          'The current session does not permit keyboard control. Ask the remote user or administrator to review its permissions.'));
    }
    if (_sample['direct'] == false) {
      findings.add(const DoctorFinding('relayed', 'info', 'Using a relay',
          'Relay routing is normal and is not a failure by itself. Compare measured quality before changing network settings.'));
    }
    final delay = _sample['latency_ms'];
    if (delay is int && delay >= latencyAdvisoryMs) {
      findings.add(const DoctorFinding(
          'high_latency',
          'warning',
          'High reported latency',
          'The latest reported delay is at least 200 ms. Try a lower image-quality setting and compare; this is not an end-to-end input-latency measurement.'));
    }
    final frames = _sample['minimum_fps'];
    if (frames is int && frames < lowFrameAdvisory) {
      findings.add(const DoctorFinding(
          'few_frames',
          'info',
          'Few frames reported',
          'A static screen can produce few frames. Check a changing image before concluding that capture or the network has failed.'));
    }
    findings.add(const DoctorFinding(
        'limited_observation',
        'info',
        'Observation limits',
        'Recent events may contain last-known measurements. This report does not prove that an application accepted input, that every component is healthy, or that licensing is enforced.'));
    return DoctorReport(
      findings.any((f) => f.severity == 'warning') ? 'attention' : 'observing',
      'recent',
      {..._sample, 'keyboard_allowed': keyboardAllowed, 'view_only': viewOnly},
      findings,
    );
  }
}
