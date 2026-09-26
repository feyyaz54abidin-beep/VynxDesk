import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_hbb/common/brand_links.dart';

void main() {
  test('all VYNX product links use the canonical website without credentials', () {
    for (final value in [VynxBrand.website, VynxBrand.product,
      VynxBrand.downloads, VynxBrand.privacy, VynxBrand.pricing,
      VynxBrand.changelog, VynxBrand.source, VynxBrand.support]) {
      final uri = Uri.parse(value);
      expect(uri.scheme, 'https');
      expect(uri.host, 'vynx.com.tr');
      expect(uri.userInfo, isEmpty);
      expect(uri.hasQuery, isFalse);
    }
  });
  test('remote desktop downloads cannot be confused with BOT or AIO downloads', () {
    expect(Uri.parse(VynxBrand.downloads).path, '/vynxdesk/');
    expect(Uri.parse(VynxBrand.privacy).path, '/vynxdesk/privacy.html');
  });
}
