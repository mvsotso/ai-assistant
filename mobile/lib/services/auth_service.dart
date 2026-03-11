import 'dart:convert';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:google_sign_in/google_sign_in.dart';
import 'package:http/http.dart' as http;
import '../config/api_config.dart';

class AuthService {
  static const _storage = FlutterSecureStorage();
  static const _tokenKey = 'session_token';
  static const _userKey = 'user_data';

  static final GoogleSignIn _googleSignIn = GoogleSignIn(scopes: ['email', 'profile']);

  static Future<Map<String, dynamic>?> signIn() async {
    try {
      final account = await _googleSignIn.signIn();
      if (account == null) return null;

      final auth = await account.authentication;
      final idToken = auth.idToken;
      if (idToken == null) return null;

      // Verify with backend
      final response = await http.post(
        Uri.parse(ApiConfig.authVerify),
        headers: {'Content-Type': 'application/json'},
        body: jsonEncode({'credential': idToken}),
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
      return null;
    }
  }

  static Future<void> signOut() async {
    await _googleSignIn.signOut();
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
    // Verify token is still valid
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
