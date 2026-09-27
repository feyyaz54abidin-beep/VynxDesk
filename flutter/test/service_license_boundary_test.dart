import 'dart:async';
import 'dart:convert';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:flutter_hbb/services/service_license_client.dart';
import 'service_license_client_test.dart' show FakeDevice;

const activationId = '00000000-0000-0000-0000-000000000001';
const audience = 'vynxdesk-managed-devices';
const expires = 1800001000;

Map<String, dynamic> lease() => {'activation_id': activationId, 'token': 'TOKEN',
  'expires_in': 300, 'service': audience};
Map<String, dynamic> inventory() => {'devices': <dynamic>[], 'max_devices': 2,
  'expires_at': expires, 'service': audience, 'relay_authorization': 'not-integrated'};
Map<String, dynamic> entry([String id = activationId]) => {'id': id, 'activated_at': expires - 1000};

ServiceLicenseClient clientFor(Map<String, dynamic> response,
    {Map<String, dynamic>? tokenResponse, FakeDevice? identity}) {
  final device = identity ?? (FakeDevice()..activation = activationId);
  return ServiceLicenseClient(Uri.parse('https://service.test'), device,
    clientFactory: () => MockClient((request) async {
      final body = request.url.path == '/v1/challenges'
        ? {'challenge': 'x' * 43}
        : request.url.path == '/v1/managed/devices' ? response : (tokenResponse ?? lease());
      return http.Response(jsonEncode(body), 200);
    }));
}

Matcher invalidResponse() => throwsA(isA<ServiceLicenseException>()
  .having((error) => error.code, 'code', 'invalid_response'));

void main() {
  test('valid maximum-size 1000-device inventory is supported', () async {
    final response = inventory()..['max_devices'] = 1000;
    response['devices'] = List.generate(1000, (i) => entry(
      '00000000-0000-0000-0000-${i.toRadixString(16).padLeft(12, '0')}'));
    expect(utf8.encode(jsonEncode(response)).length, greaterThan(65536));
    final result = await clientFor(response).devices();
    expect(result['devices'], hasLength(1000));
  });

  test('out-of-range expiry never reaches DateTime in the widget', () async {
    for (final expiry in [-1, 0, 253402300800, 1 << 62]) {
      await expectLater(clientFor(inventory()..['expires_at'] = expiry).devices(), invalidResponse());
    }
  });

  test('invalid quota and device counts are rejected', () async {
    for (final quota in [-1, 0, 1001]) {
      await expectLater(clientFor(inventory()..['max_devices'] = quota).devices(), invalidResponse());
    }
    final response = inventory()..['max_devices'] = 1;
    response['devices'] = [entry(), entry('00000000-0000-0000-0000-000000000002')];
    await expectLater(clientFor(response).devices(), invalidResponse());
  });

  test('inventory entries must have canonical distinct identifiers', () async {
    for (final devices in <List<dynamic>>[
      [null], ['device'], [{}], [entry('-' * 36)], [entry('$activationId\n')], [entry(), entry()],
    ]) {
      await expectLater(clientFor(inventory()..['devices'] = devices).devices(), invalidResponse());
    }
  });

  test('activation timestamps must be positive integers before expiry', () async {
    for (final value in [null, false, -1, 0, expires + 1, '1800000000']) {
      final response = inventory()..['devices'] = [entry()..['activated_at'] = value];
      await expectLater(clientFor(response).devices(), invalidResponse());
    }
  });

  test('wrong service inventory is never presented as VYNX entitlement', () async {
    for (final service in [null, 'different-product']) {
      await expectLater(clientFor(inventory()..['service'] = service).devices(), invalidResponse());
    }
  });

  test('lease must belong to current activation and expected service', () async {
    for (final response in [lease()..['activation_id'] = '-' * 36,
      lease()..['activation_id'] = '00000000-0000-0000-0000-000000000002',
      lease()..['service'] = 'other', lease()..remove('service')]) {
      await expectLater(clientFor(inventory(), tokenResponse: response).devices(), invalidResponse());
    }
  });

  test('invalid lease lifetime is rejected', () async {
    for (final ttl in [-1, 0, 301, '300']) {
      await expectLater(clientFor(inventory(), tokenResponse: lease()..['expires_in'] = ttl).devices(), invalidResponse());
    }
  });

  test('malformed activation reply is never persisted', () async {
    final device = FakeDevice();
    await expectLater(clientFor(inventory(), tokenResponse: lease()..['activation_id'] = '-' * 36,
      identity: device).activate('vxd_${'A' * 43}'), invalidResponse());
    expect(device.activation, isNull);
  });

  test('transport errors are stable codes without endpoint or secret details', () async {
    final client = ServiceLicenseClient(Uri.parse('https://service.test'), FakeDevice(),
      clientFactory: () => MockClient((_) async => throw http.ClientException('secret-code-in-transport-error')));
    await expectLater(client.activate('vxd_${'A' * 43}'), throwsA(isA<ServiceLicenseException>()
      .having((error) => error.code, 'code', 'network_unavailable')));
  });

  test('timeout remains a controlled retryable outcome', () async {
    final client = ServiceLicenseClient(Uri.parse('https://service.test'), FakeDevice(),
      clientFactory: () => MockClient((_) async => throw TimeoutException('timeout')));
    await expectLater(client.activate('vxd_${'A' * 43}'), throwsA(isA<ServiceLicenseException>()
      .having((error) => error.code, 'code', 'network_timeout')));
  });

  test('extra server metadata does not break a valid response', () async {
    final response = inventory()..['future_metadata'] = 'ignored';
    final result = await clientFor(response).devices();
    expect(result['devices'], isEmpty);
  });
}
