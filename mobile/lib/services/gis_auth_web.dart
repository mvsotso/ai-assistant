/// Web-only: calls Google Identity Services directly via JS interop.
/// This bypasses the google_sign_in package's People API dependency.
import 'dart:async';
import 'dart:js_interop';
import 'dart:js_interop_unsafe';

Future<String?> requestGISAccessToken(String clientId) async {
  final completer = Completer<String?>();

  // Build config for GIS TokenClient
  final config = <String, dynamic>{
    'client_id': clientId,
    'scope': 'email profile',
  }.jsify() as JSObject;

  // Set callback (receives token response from Google)
  config['callback'] = ((JSAny? response) {
    if (response != null && !completer.isCompleted) {
      try {
        final obj = response as JSObject;
        final tokenAny = obj['access_token'];
        if (tokenAny != null) {
          completer.complete((tokenAny as JSString).toDart);
        } else {
          completer.complete(null);
        }
      } catch (_) {
        completer.complete(null);
      }
    }
  }).toJS;

  // Set error callback
  config['error_callback'] = ((JSAny? error) {
    if (!completer.isCompleted) completer.complete(null);
  }).toJS;

  try {
    // google.accounts.oauth2.initTokenClient(config)
    final google = globalContext['google'] as JSObject;
    final accounts = google['accounts'] as JSObject;
    final oauth2 = accounts['oauth2'] as JSObject;
    final initFn = oauth2['initTokenClient'] as JSFunction;
    final client = initFn.callAsFunction(oauth2, config)! as JSObject;

    // client.requestAccessToken()
    final reqFn = client['requestAccessToken'] as JSFunction;
    reqFn.callAsFunction(client);
  } catch (e) {
    if (!completer.isCompleted) completer.complete(null);
  }

  // Wait for callback with 60s timeout
  return completer.future.timeout(
    const Duration(seconds: 60),
    onTimeout: () => null,
  );
}
