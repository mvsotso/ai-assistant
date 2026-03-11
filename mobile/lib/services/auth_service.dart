import 'dart:convert';
import 'package:flutter/foundation.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:google_sign_in/google_sign_in.dart';
import 'package:http/http.dart' as http;
import '../config/api_config.dart';

// Conditional import: web uses GIS JS interop, mobile uses stub
import 'gis_auth_stub.dart' if (dart.library.js_interop) 'gis_auth_web.dart';

class AuthService {
  static const _storage = FlutterSecureStorage();
  static const _tokenKey = 'session_token';
  static const _userKey = 'user_data';

  static GoogleSignIn? _googleSignIn;
  static String? _clientId;

  /// Fetch Google Client ID from backend API.
  static Future<String?> _getClientId() async {
    if (_clientId != null) return _clientId;
    try {
      debugPrint('[Auth] Fetching client ID from ${ApiConfig.authClientId}');
      final response = await http.get(Uri.parse(ApiConfig.authClientId));
      debugPrint('[Auth] Client ID response: ${response.statusCode} ct=${response.headers['content-type']}');
      if (response.statusCode == 200) {
        if (response.body.trimLeft().startsWith('<')) {
          debugPrint('[Auth] Client ID returned HTML, not JSON');
          return null;
        }
        final data = jsonDecode(response.body);
        _clientId = data['client_id'];
        return _clientId;
      }
      debugPrint('[Auth] Client ID failed: ${response.body.substring(0, 100)}');
    } catch (e) {
      debugPrint('[Auth] Client ID error: $e');
    }
    return null;
  }

  static Future<Map<String, dynamic>?> signIn() async {
    try {
      debugPrint('[Auth] Starting sign-in...');
      final clientId = await _getClientId();
      if (clientId == null) {
        debugPrint('[Auth] Failed to get client ID');
        return null;
      }
      debugPrint('[Auth] Got client ID: ${clientId.substring(0, 20)}...');

      String? credential;

      if (kIsWeb) {
        // On web: use GIS JS interop directly (avoids People API 403)
        debugPrint('[Auth] Web: requesting GIS access token...');
        credential = await requestGISAccessToken(clientId);
        debugPrint('[Auth] GIS token: ${credential != null ? "received" : "null"}');
      } else {
        // On mobile: use google_sign_in package
        _googleSignIn ??= GoogleSignIn(
          scopes: ['email', 'profile'],
          serverClientId: clientId,
        );
        final account = await _googleSignIn!.signIn();
        if (account == null) {
          debugPrint('[Auth] Mobile: user cancelled sign-in');
          return null;
        }
        final auth = await account.authentication;
        credential = auth.idToken ?? auth.accessToken;
      }

      if (credential == null) {
        debugPrint('[Auth] No credential received');
        return null;
      }
      debugPrint('[Auth] Verifying with backend...');
      final result = await _verifyWithBackend(credential);
      debugPrint('[Auth] Backend result: ${result != null ? "success" : "failed"}');
      return result;
    } catch (e) {
      debugPrint('[Auth] Sign-in error: $e');
      return null;
    }
  }

  /// Send credential (ID token or access token) to backend for verification.
  static Future<Map<String, dynamic>?> _verifyWithBackend(String credential) async {
    try {
      debugPrint('[Auth] POST ${ApiConfig.authVerify}');
      final response = await http.post(
        Uri.parse(ApiConfig.authVerify),
        headers: {'Content-Type': 'application/json'},
        body: jsonEncode({'credential': credential}),
      );
      debugPrint('[Auth] Verify response: ${response.statusCode}');

      if (response.statusCode == 200) {
        final data = jsonDecode(response.body);
        await _storage.write(key: _tokenKey, value: data['token']);
        await _storage.write(key: _userKey, value: jsonEncode({
          'email': data['email'],
          'name': data['name'],
          'picture': data['picture'],
        }));
        return data;
      }
      debugPrint('[Auth] Verify failed: ${response.body.substring(0, 200)}');
    } catch (e) {
      debugPrint('[Auth] Verify error: $e');
    }
    return null;
  }

  static Future<void> signOut() async {
    try { await _googleSignIn?.signOut(); } catch (_) {}
    await _storage.delete(key: _tokenKey);
    await _storage.delete(key: _userKey);
  }

  static Future<String?> getToken() async {
    return await _storage.read(key: _tokenKey);
  }

  static Future<Map<String, dynamic>?> getUser() async {
    final data = await _storage.read(key: _userKey);
    if (data != null) return jsonDecode(data);
    return null;
  }

  static Future<bool> isLoggedIn() async {
    final token = await getToken();
    if (token == null) return false;
    try {
      final response = await http.get(
        Uri.parse(ApiConfig.authSession),
        headers: {'Authorization': 'Bearer $token'},
      );
      // Ensure we get actual JSON, not an HTML challenge page
      if (response.statusCode != 200) return false;
      final ct = response.headers['content-type'] ?? '';
      if (!ct.contains('json')) return false;
      return true;
    } catch (_) {
      return false;
    }
  }
}
