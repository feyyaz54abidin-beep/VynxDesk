// TDD surface: classifications are intentionally absent until the red run.
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
      : metrics = Map.unmodifiable(metrics), findings = List.unmodifiable(findings);
  Map<String, Object?> toJson() => {'summary': summary, 'freshness': freshness, 'metrics': metrics};
}
class ConnectionDoctor {
  ConnectionDoctor({Duration Function()? elapsed});
  void ingest(Map<String, dynamic> snapshot) {}
  DoctorReport evaluate({bool? keyboardAllowed, bool? viewOnly}) =>
      DoctorReport('waiting', 'unavailable', {}, []);
}
