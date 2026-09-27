import 'package:flutter/material.dart';
import '../../common.dart';
import '../../services/service_license_client.dart';

class ServiceLicensePage extends StatefulWidget {
  const ServiceLicensePage({super.key});
  @override
  State<ServiceLicensePage> createState() => _ServiceLicensePageState();
}

class _ServiceLicensePageState extends State<ServiceLicensePage> {
  final _code = TextEditingController();
  bool _busy = false;
  String? _error;
  Map<String, dynamic>? _inventory;

  Future<void> _run(bool activate) async {
    if (_busy) return;
    final code = _code.text.trim();
    if (activate) _code.clear();
    setState(() { _busy = true; _error = null; _inventory = null; });
    try {
      final client = ServiceLicenseClient(Uri.parse(serviceApi), AndroidServiceDevice());
      if (activate) await client.activate(code);
      final inventory = await client.devices();
      if (mounted) setState(() { _inventory = inventory; });
    } catch (e) {
      final error = e is ServiceLicenseException ? e.code : 'service_unavailable';
      if (mounted) setState(() { _error = error; });
    } finally {
      if (mounted) setState(() { _busy = false; });
    }
  }

  @override
  void dispose() {
    _code.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final inventory = _inventory;
    return Scaffold(
      appBar: AppBar(title: Text('VYNX — ${translate('Service subscription')}')),
      body: ListView(padding: const EdgeInsets.all(20), children: [
        Text(translate('Managed service licensing does not restrict standard remote desktop.')),
        const SizedBox(height: 20),
        TextField(controller: _code, enabled: !_busy, obscureText: true,
          autocorrect: false, enableSuggestions: false,
          decoration: InputDecoration(labelText: translate('Activation code'), hintText: 'vxd_…')),
        const SizedBox(height: 12),
        Wrap(spacing: 12, children: [
          ElevatedButton(onPressed: _busy ? null : () => _run(true), child: Text(translate('Activate subscription'))),
          OutlinedButton(onPressed: _busy ? null : () => _run(false), child: Text(translate('Refresh'))),
        ]),
        if (_busy) const Padding(padding: EdgeInsets.all(16), child: LinearProgressIndicator()),
        if (_error != null) Padding(padding: const EdgeInsets.symmetric(vertical: 16),
          child: Text('${translate('Error')}: $_error')),
        if (inventory != null) ...[
          const SizedBox(height: 24),
          Text('${translate('My devices')}: ${(inventory['devices'] as List).length} / ${inventory['max_devices']}'),
          Text('${translate('Subscription expires')}: ${DateTime.fromMillisecondsSinceEpoch((inventory['expires_at'] as int) * 1000).toLocal()}'),
          const SizedBox(height: 12),
          for (final device in inventory['devices'] as List)
            if (device is Map && device['id'] is String)
              ListTile(leading: const Icon(Icons.devices), title: Text(device['id'] as String)),
        ],
      ]),
    );
  }
}
