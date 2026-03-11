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

  static Future<dynamic> get(String url, {Map<String, String>? params}) async {
    final uri = params != null ? Uri.parse(url).replace(queryParameters: params) : Uri.parse(url);
    final response = await http.get(uri, headers: await _headers());
    if (response.statusCode == 401) throw Exception('Unauthorized');
    return jsonDecode(response.body);
  }

  static Future<dynamic> post(String url, Map<String, dynamic> body) async {
    final response = await http.post(
      Uri.parse(url),
      headers: await _headers(),
      body: jsonEncode(body),
    );
    if (response.statusCode == 401) throw Exception('Unauthorized');
    return jsonDecode(response.body);
  }

  static Future<dynamic> patch(String url, Map<String, dynamic> body) async {
    final response = await http.patch(
      Uri.parse(url),
      headers: await _headers(),
      body: jsonEncode(body),
    );
    if (response.statusCode == 401) throw Exception('Unauthorized');
    return jsonDecode(response.body);
  }

  static Future<dynamic> delete(String url) async {
    final response = await http.delete(Uri.parse(url), headers: await _headers());
    if (response.statusCode == 401) throw Exception('Unauthorized');
    return jsonDecode(response.body);
  }
}
