import 'dart:convert';
import 'dart:async';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_hbb/features/connection_doctor/doctor.dart';
import 'package:flutter_hbb/features/connection_doctor/panel.dart';
import 'connection_doctor_test.dart' show snapshot;

class _TestUpdates extends ChangeNotifier {
  bool get isObserved => hasListeners;
}

void main() {
  late ConnectionDoctor doctor;
  late _TestUpdates updates;
  late Duration now;
  late List<String> copied;
  setUp(() {
    now = Duration.zero;
    doctor = ConnectionDoctor(elapsed: () => now)..ingest(snapshot());
    updates = _TestUpdates();
    copied = [];
  });
  tearDown(() => updates.dispose());
  Future<void> mount(WidgetTester tester,
      {Future<void> Function(String)? copy}) async {
    await tester.pumpWidget(MaterialApp(
        home: Scaffold(
            body: Center(
      child: SizedBox(
          width: 500,
          height: 520,
          child: ConnectionDoctorPanel(
            updates: updates,
            readReport: () => doctor.evaluate(),
            translate: (s) => s,
            copyReport: copy ??
                (s) async {
                  copied.add(s);
                },
          )),
    ))));
  }

  testWidgets('shows live observations without copying automatically',
      (tester) async {
    await mount(tester);
    expect(find.text('VYNX Connection Doctor'), findsOneWidget);
    expect(find.textContaining('30 ms'), findsOneWidget);
    expect(copied, isEmpty);
    doctor.ingest(snapshot()..['delay_ms'] = 300);
    updates.notifyListeners();
    await tester.pump();
    expect(find.textContaining('300 ms'), findsOneWidget);
    await tester.pumpWidget(const SizedBox());
  });
  testWidgets('ages observations even without new events', (tester) async {
    await mount(tester);
    now = const Duration(seconds: 16);
    await tester.pump(const Duration(seconds: 1));
    expect(find.text('Observations are stale'), findsOneWidget);
    expect(find.textContaining('30 ms'), findsNothing);
    await tester.pumpWidget(const SizedBox());
  });
  testWidgets('preview freezes exactly what the user explicitly copies',
      (tester) async {
    await mount(tester);
    await tester.tap(find.byKey(const Key('doctor-preview')));
    await tester.pump();
    expect(copied, isEmpty);
    final preview = tester
        .widget<SelectableText>(find.byKey(const Key('doctor-json')))
        .data!;
    doctor.ingest(snapshot()..['delay_ms'] = 500);
    updates.notifyListeners();
    await tester.pump();
    await tester.tap(find.byKey(const Key('doctor-copy')));
    await tester.pump();
    expect(copied, [preview]);
    expect(jsonDecode(copied.single)['metrics']['latency_ms'], 30);
    await tester.tap(find.byKey(const Key('doctor-live')));
    await tester.pump();
    expect(find.textContaining('500 ms'), findsOneWidget);
    await tester.pumpWidget(const SizedBox());
  });
  testWidgets('copy failures are recoverable and never show platform details',
      (tester) async {
    await mount(tester, copy: (_) async {
      throw PlatformException(code: 'private-path');
    });
    await tester.tap(find.byKey(const Key('doctor-preview')));
    await tester.pump();
    await tester.tap(find.byKey(const Key('doctor-copy')));
    await tester.pump();
    expect(find.text('Copy failed. Select the report text or try again.'),
        findsOneWidget);
    expect(find.textContaining('private-path'), findsNothing);
    expect(tester.takeException(), isNull);
    await tester.pumpWidget(const SizedBox());
  });
  testWidgets('narrow screen and large text remain scrollable', (tester) async {
    await tester.binding.setSurfaceSize(const Size(320, 480));
    addTearDown(() => tester.binding.setSurfaceSize(null));
    await tester.pumpWidget(MaterialApp(
        home: MediaQuery(
      data: const MediaQueryData(
          size: Size(320, 480), textScaler: TextScaler.linear(1.8)),
      child: Scaffold(
          body: ConnectionDoctorPanel(
              updates: updates,
              readReport: () => doctor.evaluate(),
              translate: (s) => s)),
    )));
    expect(tester.takeException(), isNull);
    await tester.ensureVisible(find.byKey(const Key('doctor-preview')));
    await tester.tap(find.byKey(const Key('doctor-preview')));
    await tester.pump();
    expect(find.byKey(const Key('doctor-json')), findsOneWidget);
    expect(tester.takeException(), isNull);
    await tester.pumpWidget(const SizedBox());
  });
  testWidgets('default copying uses clipboard only after explicit confirmation',
      (tester) async {
    final writes = <String>[];
    tester.binding.defaultBinaryMessenger
        .setMockMethodCallHandler(SystemChannels.platform, (call) async {
      if (call.method == 'Clipboard.setData') {
        writes.add(call.arguments['text'] as String);
      }
      return null;
    });
    addTearDown(() => tester.binding.defaultBinaryMessenger
        .setMockMethodCallHandler(SystemChannels.platform, null));
    await tester.pumpWidget(MaterialApp(
        home: Scaffold(
            body: ConnectionDoctorPanel(
                updates: updates,
                readReport: () => doctor.evaluate(),
                translate: (s) => s))));
    expect(writes, isEmpty);
    await tester.tap(find.byKey(const Key('doctor-preview')));
    await tester.pump();
    expect(writes, isEmpty);
    await tester.tap(find.byKey(const Key('doctor-copy')));
    await tester.pump();
    expect(writes, hasLength(1));
    expect(jsonDecode(writes.single)['product'], 'VynxDesk');
    await tester.pumpWidget(const SizedBox());
  });
  testWidgets('dialog entry prevents duplicate opens and recovers on dismissal',
      (tester) async {
    var calls = 0;
    final closed = Completer<void>();
    await tester.pumpWidget(MaterialApp(
        home: Scaffold(
            body: ConnectionDoctorButton(
      updates: updates,
      readReport: () => doctor.evaluate(),
      translate: (s) => s,
      present: (_) {
        calls++;
        return closed.future;
      },
    ))));
    await tester.tap(find.byKey(const Key('doctor-open')));
    await tester.pump();
    await tester.tap(find.byKey(const Key('doctor-open')));
    expect(calls, 1);
    closed.complete();
    await tester.pump();
    expect(
        tester
            .widget<TextButton>(find.byKey(const Key('doctor-open')))
            .onPressed,
        isNotNull);
    await tester.pumpWidget(const SizedBox());
  });
  testWidgets('pending copy completion cannot update a disposed panel',
      (tester) async {
    final copiedLater = Completer<void>();
    await mount(tester, copy: (_) => copiedLater.future);
    await tester.tap(find.byKey(const Key('doctor-preview')));
    await tester.pump();
    await tester.tap(find.byKey(const Key('doctor-copy')));
    await tester.pumpWidget(const SizedBox());
    copiedLater.complete();
    await tester.pump();
    expect(tester.takeException(), isNull);
  });
  testWidgets('panel fits inside a small scrollable alert dialog',
      (tester) async {
    await tester.binding.setSurfaceSize(const Size(320, 480));
    addTearDown(() => tester.binding.setSurfaceSize(null));
    await tester.pumpWidget(MaterialApp(
        home: Scaffold(
            body: AlertDialog(
      scrollable: true,
      content: ConnectionDoctorPanel(
          updates: updates,
          readReport: () => doctor.evaluate(),
          translate: (s) => s),
      actions: [TextButton(onPressed: () {}, child: const Text('Close'))],
    ))));
    expect(tester.takeException(), isNull);
    await tester.pumpWidget(const SizedBox());
  });
  testWidgets('disposing the panel removes timer and listener', (tester) async {
    await mount(tester);
    expect(updates.isObserved, true);
    await tester.pumpWidget(const SizedBox());
    expect(updates.isObserved, false);
    await tester.pump(const Duration(seconds: 30));
    expect(tester.takeException(), isNull);
  });
}
