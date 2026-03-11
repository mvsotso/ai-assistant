import 'dart:convert';
import 'package:http/http.dart' as http;
import 'auth_service.dart';

class ApiService {
  static Future<Map<String, String>> _headers() async {
    final token = await AuthService.getToken();
    return {
      'Authorization': 'Bearer $token',
      'Content-Type': 'application/json',
    };
  }

  static dynamic _handleResponse(http.Response response) {
    if (response.statusCode == 401) throw Exception('Unauthorized');
    // Guard against non-JSON responses (e.g. Cloudflare HTML pages)
    final ct = response.headers['content-type'] ?? '';
    if (!ct.contains('json') && response.body.trimLeft().startsWith('<')) {
      throw Exception('Server returned HTML instead of JSON (status ${response.statusCode})');
    }
    if (response.statusCode >= 400) {
      try {
        final body = jsonDecode(response.body);
        throw Exception(body['detail'] ?? 'API error ${response.statusCode}');
      } catch (e) {
        if (e is Exception) rethrow;
        throw Exception('API error ${response.statusCode}');
      }
    }
    return jsonDecode(response.body);
  }

  static Future<dynamic> get(String url, {Map<String, String>? params}) async {
    final uri = params != null ? Uri.parse(url).replace(queryParameters: params) : Uri.parse(url);
    final response = await http.get(uri, headers: await _headers());
    return _handleResponse(response);
  }

  static Future<dynamic> post(String url, Map<String, dynamic> body) async {
    final response = await http.post(
      Uri.parse(url),
      headers: await _headers(),
      body: jsonEncode(body),
    );
    return _handleResponse(response);
  }

  static Future<dynamic> patch(String url, Map<String, dynamic> body) async {
    final response = await http.patch(
      Uri.parse(url),
      headers: await _headers(),
      body: jsonEncode(body),
    );
    return _handleResponse(response);
  }

  static Future<dynamic> delete(String url) async {
    final response = await http.delete(Uri.parse(url), headers: await _headers());
    return _handleResponse(response);
  }
}
