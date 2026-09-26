import 'dart:convert';
import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_hbb/features/connection_doctor/doctor.dart';

Map<String, dynamic> snapshot({String state = 'connected'}) => {
  'lifecycle': state, 'secure': true, 'direct': true, 'transport': 'TCP',
  'delay_ms': 30, 'target_bitrate_kbps': 3200, 'fps': {'0': 60},
  'codec': 'H264', 'chroma': '4:2:0',
};
Set<String> codes(DoctorReport report) => report.findings.map((f) => f.code).toSet();

void main() {
  late Duration now;
  late ConnectionDoctor doctor;
  setUp(() { now = Duration.zero; doctor = ConnectionDoctor(elapsed: () => now); });

  test('missing telemetry is unavailable, not a healthy session', () {
    expect(doctor.evaluate().freshness, 'unavailable');
    expect(codes(doctor.evaluate()), contains('no_observation'));
  });
  test('connected snapshot produces only an observation, not a guarantee', () {
    doctor.ingest(snapshot());
    final report = doctor.evaluate();
    expect(report.freshness, 'recent');
    expect(report.summary, 'observing');
    expect(report.metrics['latency_ms'], 30);
    expect(codes(report), contains('limited_observation'));
  });
  test('relay path is informational, not a performance failure', () {
    doctor.ingest(snapshot()..['direct'] = false..['transport'] = 'WebRTC');
    final relay = doctor.evaluate().findings.singleWhere((f) => f.code == 'relayed');
    expect(relay.severity, 'info');
    expect(doctor.evaluate().summary, 'observing');
  });
  test('unknown security is not treated as verified', () {
    doctor.ingest(snapshot()..remove('secure'));
    expect(codes(doctor.evaluate()), contains('security_unknown'));
    expect(doctor.evaluate().metrics['secure'], isNull);
  });
  test('unverified security is called unverified, not unencrypted', () {
    doctor.ingest(snapshot()..['secure'] = false);
    expect(codes(doctor.evaluate()), contains('security_unverified'));
    expect(doctor.evaluate().summary, 'attention');
  });
  test('latency advisory begins at the documented threshold', () {
    doctor.ingest(snapshot()..['delay_ms'] = 199);
    expect(codes(doctor.evaluate()), isNot(contains('high_latency')));
    doctor.ingest(snapshot()..['delay_ms'] = 200);
    expect(codes(doctor.evaluate()), contains('high_latency'));
  });
  test('low frames are advisory and never proof of network failure', () {
    doctor.ingest(snapshot()..['fps'] = {'0': 0, '1': 60});
    final item = doctor.evaluate().findings.singleWhere((f) => f.code == 'few_frames');
    expect(item.severity, 'info');
    expect(item.detail, contains('static screen'));
    expect(codes(doctor.evaluate()), isNot(contains('network_failure')));
  });
  test('freshness expires without another event', () {
    doctor.ingest(snapshot()..['delay_ms'] = 900);
    now = const Duration(seconds: 15);
    expect(doctor.evaluate().freshness, 'recent');
    now = const Duration(seconds: 16);
    final report = doctor.evaluate();
    expect(report.freshness, 'stale');
    expect(codes(report), contains('stale_observation'));
    expect(codes(report), isNot(contains('high_latency')));
    expect(report.metrics['latency_ms'], isNull);
  });
  test('disconnection never presents cached performance as current', () {
    doctor.ingest(snapshot(state: 'disconnected'));
    expect(doctor.evaluate().freshness, 'ended');
    expect(doctor.evaluate().summary, 'disconnected');
    expect(doctor.evaluate().metrics['latency_ms'], isNull);
  });
  test('reconnection resets performance and security observations', () {
    doctor.ingest(snapshot());
    doctor.ingest({'lifecycle': 'connecting'});
    expect(doctor.evaluate().summary, 'connecting');
    expect(doctor.evaluate().metrics['secure'], isNull);
    doctor.ingest({'lifecycle': 'connected'});
    expect(doctor.evaluate().metrics['latency_ms'], isNull);
    expect(codes(doctor.evaluate()), contains('security_unknown'));
  });
  test('malformed lifecycle cannot retain earlier apparently healthy state', () {
    doctor.ingest(snapshot());
    doctor.ingest({'lifecycle': ['connected'], 'delay_ms': 5});
    expect(doctor.evaluate().freshness, 'unavailable');
  });
  test('keyboard denial and view-only are distinct current observations', () {
    doctor.ingest(snapshot());
    expect(codes(doctor.evaluate(keyboardAllowed: false)), contains('keyboard_denied'));
    expect(codes(doctor.evaluate(viewOnly: true)), contains('view_only'));
    expect(codes(doctor.evaluate()), isNot(contains('keyboard_denied')));
  });
  test('permissions are not guessed from absent telemetry or stale state', () {
    expect(codes(doctor.evaluate(keyboardAllowed: false)), isNot(contains('keyboard_denied')));
    doctor.ingest(snapshot());
    now = const Duration(seconds: 20);
    expect(codes(doctor.evaluate(keyboardAllowed: false)), isNot(contains('keyboard_denied')));
  });
  test('arbitrary telemetry fields and free-form values cannot enter report', () {
    const secret = 'secret-user-192.0.2.1-password';
    doctor.ingest(snapshot()..addAll({'peer_id': secret, 'token': secret,
      'transport': secret, 'codec': secret, 'speed': secret, 'chroma': secret,
      'fps': {secret: 60}, 'delay_ms': secret}));
    final encoded = jsonEncode(doctor.evaluate().toJson());
    expect(encoded, isNot(contains(secret)));
    expect(encoded, isNot(contains('peer_id')));
    expect(encoded, isNot(contains('token')));
  });
  test('invalid numeric types and unreasonable values become unknown', () {
    for (final value in [true, -1, 1.5, double.nan, double.infinity, '42\n', '9' * 10000]) {
      doctor.ingest(snapshot()..['delay_ms'] = value..['target_bitrate_kbps'] = value);
      expect(doctor.evaluate().metrics['latency_ms'], isNull);
      expect(doctor.evaluate().metrics['target_bitrate_kbps'], isNull);
    }
  });
  test('bounded legacy integers and booleans are supported', () {
    doctor.ingest(snapshot()..['secure'] = 'true'..['direct'] = 'false'..['delay_ms'] = '70');
    expect(doctor.evaluate().metrics['secure'], true);
    expect(doctor.evaluate().metrics['latency_ms'], 70);
  });
  test('report is immutable after the next observation', () {
    doctor.ingest(snapshot());
    final report = doctor.evaluate();
    final before = jsonEncode(report.toJson());
    doctor.ingest(snapshot()..['delay_ms'] = 900);
    expect(jsonEncode(report.toJson()), before);
    expect(() => report.metrics['latency_ms'] = 5, throwsUnsupportedError);
    expect(() => report.findings.clear(), throwsUnsupportedError);
  });
  test('hostile fps map is discarded and valid display indices are bounded', () {
    doctor.ingest(snapshot()..['fps'] = {'-1': 0, 'secret': 0, '0': 60});
    expect(doctor.evaluate().metrics['minimum_fps'], 60);
    doctor.ingest(snapshot()..['fps'] = {for (int i = 0; i < 65; i++) '$i': 60});
    expect(doctor.evaluate().metrics['minimum_fps'], isNull);
  });
  test('clock discontinuity is unavailable rather than negative age', () {
    now = const Duration(seconds: 10);
    doctor.ingest(snapshot());
    now = Duration.zero;
    expect(doctor.evaluate().freshness, 'stale');
  });
}
