import 'dart:async';
import 'dart:convert';
import 'package:crypto/crypto.dart';
import 'package:flutter/services.dart';
import 'package:http/http.dart' as http;

const serviceApi = String.fromEnvironment('VYNXDESK_SERVICE_API');

abstract class ServiceDeviceIdentity {
  Future<Map<String, dynamic>> identity();
  Future<String> sign(String payload);
  Future<void> remember(String id);
}

class AndroidServiceDevice implements ServiceDeviceIdentity {
  static const _channel = MethodChannel('com.vynxdesk.client/service-license');
  @override
  Future<Map<String, dynamic>> identity() async =>
      Map<String, dynamic>.from(await _channel.invokeMethod('identity') as Map);
  @override
  Future<String> sign(String payload) async =>
      (await _channel.invokeMethod<String>('sign', payload))!;
  @override
  Future<void> remember(String id) async => _channel.invokeMethod<void>('remember', id);
}

class ServiceLicenseException implements Exception {
  final String code;
  const ServiceLicenseException(this.code);
  @override
  String toString() => code;
}

/// This is a client for server-protected inventory, not a local license gate for
/// remote desktop. The server verifies proof, expiry and revocation on each call.
class ServiceLicenseClient {
  final Uri origin;
  final ServiceDeviceIdentity device;
  final http.Client Function() clientFactory;

  ServiceLicenseClient(this.origin, this.device, {http.Client Function()? clientFactory})
      : clientFactory = clientFactory ?? http.Client.new {
    if (origin.scheme != 'https' || origin.host.isEmpty || origin.userInfo.isNotEmpty ||
        origin.hasQuery || origin.hasFragment || !['', '/'].contains(origin.path)) {
      throw ArgumentError('The managed-service origin must be a plain HTTPS origin');
    }
  }

  Future<Map<String, dynamic>> _post(String path, Map<String, dynamic> body) async {
    final client = clientFactory();
    try {
      final request = http.Request('POST', origin.resolve(path))
        ..followRedirects = false
        ..headers['Content-Type'] = 'application/json'
        ..body = jsonEncode(body);
      final response = await client.send(request).timeout(const Duration(seconds: 15));
      final bytes = <int>[];
      await response.stream.forEach((chunk) {
        if (bytes.length + chunk.length > 128 * 1024) {
          throw const ServiceLicenseException('invalid_response');
        }
        bytes.addAll(chunk);
      }).timeout(const Duration(seconds: 15));
      if (response.statusCode != 200) {
        const errors = {401: 'authorization_denied', 409: 'device_limit_reached',
          429: 'rate_limited', 503: 'service_unavailable'};
        throw ServiceLicenseException(errors[response.statusCode] ?? 'service_error');
      }
      final decoded = jsonDecode(utf8.decode(bytes));
      if (decoded is! Map<String, dynamic>) {
        throw const ServiceLicenseException('invalid_response');
      }
      return decoded;
    } on http.ClientException {
      throw const ServiceLicenseException('network_unavailable');
    } on TimeoutException {
      throw const ServiceLicenseException('network_timeout');
    } on FormatException {
      throw const ServiceLicenseException('invalid_response');
    } finally {
      client.close();
    }
  }

  Future<Map<String, dynamic>> _proof(String operation, String value) async {
    final identity = await device.identity();
    final binding = sha256.convert(utf8.encode(value)).toString();
    final response = await _post('/v1/challenges', {
      'public_key': identity['public_key'], 'operation': operation, 'binding': binding,
    });
    final nonce = response['challenge'];
    if (nonce is! String || !RegExp(r'^[A-Za-z0-9_-]{43}$').hasMatch(nonce)) {
      throw const ServiceLicenseException('invalid_response');
    }
    final payload = 'VYNXDESK/1\n$operation\n$nonce\n$binding';
    return {'challenge': nonce, 'signature': await device.sign(payload)};
  }

  static bool _activationId(dynamic value) => value is String &&
      value.length == 36 &&
      RegExp(r'^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$').hasMatch(value);

  static bool _lease(Map<String, dynamic> value, {String? activationId}) {
    final token = value['token'];
    final ttl = value['expires_in'];
    return _activationId(value['activation_id']) &&
        (activationId == null || value['activation_id'] == activationId) &&
        value['service'] == 'vynxdesk-managed-devices' &&
        token is String && token.isNotEmpty && token.length <= 4096 &&
        ttl is int && ttl >= 1 && ttl <= 300;
  }

  static bool _inventory(Map<String, dynamic> value) {
    final devices = value['devices'];
    final quota = value['max_devices'];
    final expiry = value['expires_at'];
    if (value['service'] != 'vynxdesk-managed-devices' ||
        devices is! List || quota is! int || quota < 1 || quota > 1000 ||
        devices.length > quota || expiry is! int || expiry < 1 ||
        expiry > 253402300799) {
      return false;
    }
    final identifiers = <String>{};
    for (final entry in devices) {
      if (entry is! Map<String, dynamic> || !_activationId(entry['id'])) {
        return false;
      }
      final activatedAt = entry['activated_at'];
      if (!identifiers.add(entry['id'] as String) || activatedAt is! int ||
          activatedAt < 1 || activatedAt > expiry) {
        return false;
      }
    }
    return true;
  }

  Future<void> activate(String code) async {
    if (!RegExp(r'^vxd_[A-Za-z0-9_-]{43}$').hasMatch(code)) {
      throw const ServiceLicenseException('invalid_activation_code');
    }
    final response = await _post('/v1/activate', {'code': code, ...await _proof('activate', code)});
    final id = response['activation_id'];
    if (!_lease(response)) {
      throw const ServiceLicenseException('invalid_response');
    }
    await device.remember(id as String);
  }

  Future<Map<String, dynamic>> devices() async {
    final identity = await device.identity();
    final id = identity['activation_id'];
    if (!_activationId(id)) {
      throw const ServiceLicenseException('activation_required');
    }
    final refreshed = await _post('/v1/refresh', {
      'activation_id': id, ...await _proof('refresh', id as String),
    });
    if (!_lease(refreshed, activationId: id as String)) {
      throw const ServiceLicenseException('invalid_response');
    }
    final token = refreshed['token'] as String;
    final response = await _post('/v1/managed/devices', {'token': token, ...await _proof('devices', token)});
    if (!_inventory(response)) {
      throw const ServiceLicenseException('invalid_response');
    }
    return response;
  }
}
