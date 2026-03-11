import 'dart:convert';
import 'package:flutter/foundation.dart' show kIsWeb;
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
      final response = await http.get(Uri.parse(ApiConfig.authClientId));
      if (response.statusCode == 200) {
        final data = jsonDecode(response.body);
        _clientId = data['client_id'];
        return _clientId;
      }
    } catch (_) {}
    return null;
  }

  static Future<Map<String, dynamic>?> signIn() async {
    try {
      final clientId = await _getClientId();
      if (clientId == null) return null;

      String? credential;

      if (kIsWeb) {
        // On web: use GIS JS interop directly (avoids People API 403)
        credential = await requestGISAccessToken(clientId);
      } else {
        // On mobile: use google_sign_in package
        _googleSignIn ??= GoogleSignIn(
          scopes: ['email', 'profile'],
          serverClientId: clientId,
        );
        final account = await _googleSignIn!.signIn();
        if (account == null) return null;
        final auth = await account.authentication;
        credential = auth.idToken ?? auth.accessToken;
      }

      if (credential == null) return null;
      return await _verifyWithBackend(credential);
    } catch (e) {
      return null;
    }
  }

  /// Send credential (ID token or access token) to backend for verification.
  static Future<Map<String, dynamic>?> _verifyWithBackend(String credential) async {
    try {
      final response = await http.post(
        Uri.parse(ApiConfig.authVerify),
        headers: {'Content-Type': 'application/json'},
        body: jsonEncode({'credential': credential}),
      );

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
    } catch (_) {}
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
      return response.statusCode == 200;
    } catch (_) {
      return false;
    }
  }
}
