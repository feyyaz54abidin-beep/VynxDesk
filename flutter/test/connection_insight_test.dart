import 'package:flutter_hbb/models/model.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  test('formats a relayed diagnostics snapshot without treating it as direct',
      () {
    final insight = ConnectionInsightData.fromJson({
      'lifecycle': 'connected',
      'secure': true,
      'direct': false,
      'transport': 'WebRTC',
    });

    expect(insight.lifecycleLabel, 'Connected');
    expect(insight.securityLabel, 'Secure');
    expect(insight.transportLabel, 'WebRTC (Relay)');
  });

  test('accepts nullable and legacy string boolean diagnostics values', () {
    final insight = ConnectionInsightData.fromJson({
      'lifecycle': 'disconnected',
      'secure': 'false',
      'direct': null,
      'transport': '',
    });

    expect(insight.lifecycleLabel, 'Disconnected');
    expect(insight.securityLabel, 'Unverified');
    expect(insight.transportLabel, '-');
  });

  test('does not duplicate the native relay transport label', () {
    final insight = ConnectionInsightData.fromJson({
      'direct': false,
      'transport': 'Relay',
    });

    expect(insight.transportLabel, 'Relay');
  });
}
