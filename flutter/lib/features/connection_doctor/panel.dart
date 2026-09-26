import 'dart:async';
import 'dart:convert';
import 'dart:math' as math;
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'doctor.dart';

/// Opens in the caller's existing session-blocking dialog, never a new route.
class ConnectionDoctorButton extends StatefulWidget {
  const ConnectionDoctorButton(
      {super.key,
      required this.updates,
      required this.readReport,
      required this.translate,
      required this.present});
  final Listenable updates;
  final DoctorReport Function() readReport;
  final String Function(String) translate;
  final Future<void> Function(Widget) present;
  @override
  State<ConnectionDoctorButton> createState() => _ConnectionDoctorButtonState();
}

class _ConnectionDoctorButtonState extends State<ConnectionDoctorButton> {
  bool _opening = false;
  bool _failed = false;
  Future<void> _open() async {
    if (_opening) return;
    setState(() {
      _opening = true;
      _failed = false;
    });
    try {
      await widget.present(ConnectionDoctorPanel(
          updates: widget.updates,
          readReport: widget.readReport,
          translate: widget.translate));
    } catch (_) {
      if (mounted) setState(() => _failed = true);
    } finally {
      if (mounted) setState(() => _opening = false);
    }
  }

  @override
  Widget build(BuildContext context) => TextButton.icon(
        key: const Key('doctor-open'),
        onPressed: _opening ? null : _open,
        icon: Icon(_failed ? Icons.refresh : Icons.health_and_safety_outlined,
            size: 18),
        label: Text(widget.translate(
            _failed ? 'Retry connection doctor' : 'Connection doctor')),
      );
}

class ConnectionDoctorPanel extends StatefulWidget {
  const ConnectionDoctorPanel(
      {super.key,
      required this.updates,
      required this.readReport,
      required this.translate,
      this.copyReport});
  final Listenable updates;
  final DoctorReport Function() readReport;
  final String Function(String) translate;
  final Future<void> Function(String)? copyReport;
  @override
  State<ConnectionDoctorPanel> createState() => _ConnectionDoctorPanelState();
}

class _ConnectionDoctorPanelState extends State<ConnectionDoctorPanel> {
  late final Timer _timer;
  final ScrollController _scroll = ScrollController();
  String? _preview;
  String? _copyStatus;
  bool _copying = false;

  @override
  void initState() {
    super.initState();
    widget.updates.addListener(_refresh);
    _timer = Timer.periodic(const Duration(seconds: 1), (_) => _refresh());
  }

  @override
  void didUpdateWidget(covariant ConnectionDoctorPanel oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.updates != widget.updates) {
      oldWidget.updates.removeListener(_refresh);
      widget.updates.addListener(_refresh);
    }
  }

  void _refresh() {
    if (mounted && _preview == null) setState(() {});
  }

  void _showPreview(DoctorReport report) {
    setState(() {
      _preview = const JsonEncoder.withIndent('  ').convert(report.toJson());
      _copyStatus = null;
    });
    if (_scroll.hasClients) _scroll.jumpTo(0);
  }

  Future<void> _copy() async {
    final text = _preview;
    if (text == null || _copying) return;
    setState(() {
      _copying = true;
      _copyStatus = null;
    });
    try {
      if (widget.copyReport != null) {
        await widget.copyReport!(text);
      } else {
        await Clipboard.setData(ClipboardData(text: text));
      }
      if (mounted) setState(() => _copyStatus = 'Report copied');
    } catch (_) {
      if (mounted) {
        setState(() =>
            _copyStatus = 'Copy failed. Select the report text or try again.');
      }
    } finally {
      if (mounted) setState(() => _copying = false);
    }
  }

  @override
  void dispose() {
    _timer.cancel();
    widget.updates.removeListener(_refresh);
    _scroll.dispose();
    super.dispose();
  }

  static const _summaryLabels = {
    'waiting': 'Waiting for observations',
    'connecting': 'Connection in progress',
    'disconnected': 'Session disconnected',
    'attention': 'Review these observations',
    'observing': 'Observing the reported session',
  };
  static const _metricLabels = {
    'transport': 'Transport',
    'latency_ms': 'Reported delay',
    'minimum_fps': 'Lowest reported display FPS',
    'target_bitrate_kbps': 'Target bitrate',
    'codec': 'Codec',
    'chroma': 'Chroma',
  };
  String _metric(String name, Object value) {
    final unit = name == 'latency_ms'
        ? ' ms'
        : name == 'target_bitrate_kbps'
            ? ' kbps'
            : '';
    return '${widget.translate(_metricLabels[name]!)}: $value$unit';
  }

  @override
  Widget build(BuildContext context) {
    final t = widget.translate;
    final report = _preview == null ? widget.readReport() : null;
    final theme = Theme.of(context);
    return SizedBox(
      width: 500,
      height: math.min(520.0, MediaQuery.of(context).size.height * 0.65),
      child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
        Expanded(
            child: SingleChildScrollView(
                controller: _scroll,
                child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text('VYNX Connection Doctor',
                          style: theme.textTheme.titleLarge),
                      const SizedBox(height: 8),
                      if (_preview == null && report != null) ...[
                        Text(t(_summaryLabels[report.summary]!),
                            style: theme.textTheme.titleMedium),
                        const SizedBox(height: 8),
                        for (final metric in _metricLabels.keys)
                          if (report.metrics[metric] != null)
                            Padding(
                                padding: const EdgeInsets.only(bottom: 4),
                                child: Text(
                                    _metric(metric, report.metrics[metric]!))),
                        for (final finding in report.findings)
                          Card(
                              child: Padding(
                                  padding: const EdgeInsets.all(12),
                                  child: Column(
                                      crossAxisAlignment:
                                          CrossAxisAlignment.start,
                                      children: [
                                        Row(
                                            crossAxisAlignment:
                                                CrossAxisAlignment.start,
                                            children: [
                                              Icon(
                                                  finding.severity == 'warning'
                                                      ? Icons
                                                          .warning_amber_rounded
                                                      : Icons.info_outline,
                                                  color: finding.severity ==
                                                          'warning'
                                                      ? theme.colorScheme.error
                                                      : theme
                                                          .colorScheme.primary),
                                              const SizedBox(width: 8),
                                              Expanded(
                                                  child: Text(t(finding.title),
                                                      style: theme.textTheme
                                                          .titleSmall)),
                                            ]),
                                        const SizedBox(height: 6),
                                        Text(t(finding.detail)),
                                      ]))),
                      ] else ...[
                        Text(t('Report preview'),
                            style: theme.textTheme.titleMedium),
                        const SizedBox(height: 8),
                        Text(t(
                            'This frozen report includes only allowed status values and numeric diagnostics. No peer IDs, addresses, credentials or screen content are included. Nothing is uploaded.')),
                        const SizedBox(height: 8),
                        Text(t(
                            'Copying uses the system clipboard. Clipboard synchronization or other apps may share its contents.')),
                        const SizedBox(height: 12),
                        SelectableText(_preview!,
                            key: const Key('doctor-json'),
                            style: const TextStyle(
                                fontFamily: 'monospace', fontSize: 12)),
                      ],
                    ]))),
        if (_copyStatus != null)
          Padding(
              padding: const EdgeInsets.symmetric(vertical: 6),
              child:
                  Text(t(_copyStatus!), key: const Key('doctor-copy-status'))),
        const SizedBox(height: 8),
        Wrap(spacing: 8, runSpacing: 4, children: [
          if (_preview == null)
            OutlinedButton.icon(
                key: const Key('doctor-preview'),
                onPressed: () => _showPreview(report!),
                icon: const Icon(Icons.description_outlined),
                label: Text(t('Preview report')))
          else ...[
            TextButton(
                key: const Key('doctor-live'),
                onPressed: _copying
                    ? null
                    : () {
                        setState(() {
                          _preview = null;
                          _copyStatus = null;
                        });
                        if (_scroll.hasClients) _scroll.jumpTo(0);
                      },
                child: Text(t('Back to observations'))),
            OutlinedButton.icon(
                key: const Key('doctor-copy'),
                onPressed: _copying ? null : _copy,
                icon: const Icon(Icons.copy),
                label: Text(t('Copy report'))),
          ],
        ]),
      ]),
    );
  }
}
