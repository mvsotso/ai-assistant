import 'dart:convert';
import 'package:flutter/foundation.dart' show kIsWeb;
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:google_sign_in/google_sign_in.dart';
import 'package:http/http.dart' as http;
import '../config/api_config.dart';

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
      // Fetch client ID from backend
      final clientId = await _getClientId();
      if (clientId == null) return null;

      // Initialize GoogleSignIn with the fetched client ID
      _googleSignIn ??= GoogleSignIn(
        scopes: ['email', 'profile'],
        clientId: kIsWeb ? clientId : null,
        serverClientId: kIsWeb ? null : clientId,
      );

      final account = await _googleSignIn!.signIn();
      if (account == null) return null;

      final auth = await account.authentication;

      // On web, signIn() returns an access token (not an ID token)
      // On mobile, it returns an ID token
      String? credential;
      if (kIsWeb) {
        credential = auth.accessToken;
      } else {
        credential = auth.idToken ?? auth.accessToken;
      }
      if (credential == null) return null;

      // Verify with backend (backend accepts both ID tokens and access tokens)
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
      return null;
    } catch (e) {
      if (kIsWeb) {
        // On web, People API 403 may throw — try to recover
        // by checking if we have an authenticated account
        try {
          final account = _googleSignIn?.currentUser;
          if (account != null) {
            final auth = await account.authentication;
            final accessToken = auth.accessToken;
            if (accessToken != null) {
              final response = await http.post(
                Uri.parse(ApiConfig.authVerify),
                headers: {'Content-Type': 'application/json'},
                body: jsonEncode({'credential': accessToken}),
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
            }
          }
        } catch (_) {}
      }
      return null;
    }
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
