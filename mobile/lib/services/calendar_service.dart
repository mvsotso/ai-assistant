import 'package:flutter/foundation.dart';
import '../config/api_config.dart';
import 'api_service.dart';

class CalendarService {
  static Future<List<Map<String, dynamic>>> getEvents({String? timeMin, String? timeMax}) async {
    final params = <String, String>{};
    if (timeMin != null) params['time_min'] = timeMin;
    if (timeMax != null) params['time_max'] = timeMax;
    debugPrint('[Calendar] Fetching events: $params');
    final data = await ApiService.get(ApiConfig.calendarEvents, params: params);
    debugPrint('[Calendar] Response keys: ${data.keys.toList()}');
    final events = List<Map<String, dynamic>>.from(data['events'] ?? []);
    debugPrint('[Calendar] Got ${events.length} events');
    if (events.isNotEmpty) debugPrint('[Calendar] First event: ${events.first}');
    return events;
  }
}
