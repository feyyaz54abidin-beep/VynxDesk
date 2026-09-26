import 'dart:convert';
import 'package:crypto/crypto.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:flutter_hbb/services/service_license_client.dart';

class FakeDevice implements ServiceDeviceIdentity {
  String? activation;
  final signed = <String>[];
  @override
  Future<Map<String, dynamic>> identity() async =>
      {'public_key': 'PUBLIC_KEY', 'activation_id': activation};
  @override
  Future<String> sign(String payload) async {
    signed.add(payload);
    return 'SIGNATURE';
  }
  @override
  Future<void> remember(String id) async { activation = id; }
}

void main() {
  test('rejects insecure or ambiguous service URLs', () {
    for (final raw in ['http://service.test', 'https://u:p@service.test',
      'https://service.test/path', 'https://service.test?x=1', 'https://service.test/#x']) {
      expect(() => ServiceLicenseClient(Uri.parse(raw), FakeDevice()), throwsArgumentError);
    }
  });

  test('activation binds the license hash and keeps only device ID', () async {
    final device = FakeDevice();
    final nonce = 'n' * 43;
    final code = 'vxd_${'A' * 43}';
    final id = '00000000-0000-0000-0000-000000000001';
    final client = ServiceLicenseClient(Uri.parse('https://service.test'), device,
      clientFactory: () => MockClient((request) async {
        expect(request.followRedirects, isFalse);
        final data = jsonDecode(request.body) as Map<String, dynamic>;
        if (request.url.path == '/v1/challenges') {
          expect(data['operation'], 'activate');
          expect(data['binding'], sha256.convert(utf8.encode(code)).toString());
          return http.Response(jsonEncode({'challenge': nonce}), 200);
        }
        expect(data['code'], code);
        expect(data['challenge'], nonce);
        return http.Response(jsonEncode({'activation_id': id, 'token': 'SERVER-TOKEN',
          'expires_in': 300, 'service': 'vynxdesk-managed-devices'}), 200);
      }));
    await client.activate(code);
    expect(device.activation, id);
    expect(device.signed.single,
      'VYNXDESK/1\nactivate\n$nonce\n${sha256.convert(utf8.encode(code))}');
  });

  test('server denial never remembers an activation', () async {
    final device = FakeDevice();
    final client = ServiceLicenseClient(Uri.parse('https://service.test'), device,
      clientFactory: () => MockClient((request) async =>
        http.Response('{"error":"authorization_denied"}', 401)));
    await expectLater(client.activate('vxd_${'A' * 43}'), throwsA(isA<ServiceLicenseException>()));
    expect(device.activation, isNull);
  });

  test('redirect is rejected rather than forwarding an activation code', () async {
    final client = ServiceLicenseClient(Uri.parse('https://service.test'), FakeDevice(),
      clientFactory: () => MockClient((request) async =>
        http.Response('', 307, headers: {'location': 'https://other.test'})));
    await expectLater(client.activate('vxd_${'A' * 43}'), throwsA(isA<ServiceLicenseException>()));
  });

  test('invalid challenge cannot become a generic signing oracle', () async {
    final device = FakeDevice();
    final client = ServiceLicenseClient(Uri.parse('https://service.test'), device,
      clientFactory: () => MockClient((request) async =>
        http.Response('{"challenge":"bad\\nother-data"}', 200)));
    await expectLater(client.activate('vxd_${'A' * 43}'), throwsA(isA<ServiceLicenseException>()));
    expect(device.signed, isEmpty);
  });

  test('managed inventory requires refresh and a separate proof', () async {
    final device = FakeDevice()..activation = '00000000-0000-0000-0000-000000000001';
    final paths = <String>[];
    final client = ServiceLicenseClient(Uri.parse('https://service.test'), device,
      clientFactory: () => MockClient((request) async {
        paths.add(request.url.path);
        if (request.url.path == '/v1/challenges') {
          return http.Response(jsonEncode({'challenge': 'x' * 43}), 200);
        }
        if (request.url.path == '/v1/refresh') {
          return http.Response(jsonEncode({'activation_id': device.activation, 'token': 'SERVER-TOKEN',
            'expires_in': 300, 'service': 'vynxdesk-managed-devices'}), 200);
        }
        return http.Response('{"devices":[],"max_devices":2,"expires_at":1800000100,"relay_authorization":"not-integrated","service":"vynxdesk-managed-devices"}', 200);
      }));
    final result = await client.devices();
    expect(result['devices'], isEmpty);
    expect(paths, ['/v1/challenges', '/v1/refresh', '/v1/challenges', '/v1/managed/devices']);
    expect(device.signed[0], contains('\nrefresh\n'));
    expect(device.signed[1], contains('\ndevices\n'));
  });
}
